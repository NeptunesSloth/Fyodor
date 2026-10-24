import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules.cost_payment import counter_tokens
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import roundtrip
from tests.test_rules_pooled_casting_authorities71 import (
    NAMES,
    SUPPORT,
    Plan,
    ability,
    act,
    cast,
    gameplay,
    mana,
    put,
    settle,
    to_phase,
)


@pytest.fixture()
def cards(settings):
    from tests.fixtures.cards import card, fixture_cards

    base = {c["name"]: c for c in fixture_cards()}
    for filename in [
        "exile_outcomes42_cards.json",
        "exile_cast_outcomes45_cards.json",
        "fight_exile_receipts65_cards.json",
        "top_library_authorities69_cards.json",
        "pooled_casting_authorities71_cards.json",
        "wave47c_cards.json",
    ]:
        for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / filename).read_text())):
            base[c["name"]] = card(
                c["name"],
                set_code="pc71",
                number=str(i),
                **{k: v for k, v in c.items() if k not in {"name", "set_code"}},
            )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    return gameplay.setup(cards, *NAMES, *SUPPORT, "Hierophant Bio-Titan")


@pytest.mark.parametrize("split", [False, True])
def test_dawnhand_may_remove_three_counters_then_sacrifice_same_permission_source(cards, split):
    s = setup(cards)
    source = cast(s, "Dawnhand Dissident")
    coram = cast(s, "Coram, the Undertaker")
    target = put(s, "Demon of Catastrophes", "graveyard")
    to_phase(s, "main1", turn=4)
    settle(s)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability(s, source, "{T}, Blight 2"),
        targets=[target.id],
        cost_choices=[{"component": 1, "cards": [coram.id]}],
    )
    settle(s)
    act(s, "p1", type="set_counter", card_id=source.id, kind="charge", value=1 if split else 3)
    if split:
        act(s, "p1", type="set_counter", card_id=coram.id, kind="charge", value=2)
    tokens = [
        token
        for token, (_, kind) in counter_tokens(
            Plan(s.state, "p1", cards, None), [source.id, coram.id]
        ).items()
        if kind == "charge"
    ]
    assert len(tokens) == 3
    mana(s, C=2, B=2)
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=target.id,
        cost_choices=[{"component": 0, "cards": [source.id]}, {"component": 1, "cards": tokens}],
    )
    settle(s)
    assert s.state.cards[target.id].zone == "p1:battlefield"
    assert s.state.cards[source.id].zone == "p1:graveyard"
    assert not s.state.cards[source.id].counters.get("charge")
    if split:
        assert not s.state.cards[coram.id].counters.get("charge")
    roundtrip(s)


def test_automatic_counter_holder_is_pinned_before_later_sacrifice_question(cards):
    s = setup(cards)
    source = cast(s, "Dawnhand Dissident")
    holder = cast(s, "Coram, the Undertaker")
    target = put(s, "Demon of Catastrophes", "graveyard")
    to_phase(s, "main1", turn=4)
    settle(s)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability(s, source, "{T}, Blight 2"),
        targets=[target.id],
        cost_choices=[{"component": 1, "cards": [holder.id]}],
    )
    settle(s)
    act(s, "p1", type="set_counter", card_id=holder.id, kind="-1/-1", value=0)
    act(s, "p1", type="set_counter", card_id=holder.id, kind="charge", value=3)
    mana(s, C=2, B=2)
    act(s, "p1", type="cast_spell", card_id=target.id)
    decision = s.state.rules.decision
    assert decision and decision.resume["step"] == "ability_cost"
    receipt = decision.resume["counter_choice72"]
    assert receipt["originals"][0]["card"] == holder.id
    old_oid = receipt["originals"][0]["object_id"]
    act(s, "p1", type="move", card_ids=[holder.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="move", card_ids=[holder.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="set_counter", card_id=holder.id, kind="charge", value=3)
    assert s.state.rules.object_id(holder.id) != old_oid
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match="original object"):
        answer(s, [source.id])
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


@pytest.mark.parametrize("mode", ["valid", "reincarnated", "missing_originals"])
def test_actual_cold_automatic_counter_choice72_keeps_original_objects(cards, tmp_path, mode):
    import os
    import subprocess
    import sys

    s = setup(cards)
    source = cast(s, "Dawnhand Dissident")
    holder = cast(s, "Coram, the Undertaker")
    target = put(s, "Demon of Catastrophes", "graveyard")
    to_phase(s, "main1", turn=4)
    settle(s)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability(s, source, "{T}, Blight 2"),
        targets=[target.id],
        cost_choices=[{"component": 1, "cards": [holder.id]}],
    )
    settle(s)
    act(s, "p1", type="set_counter", card_id=holder.id, kind="-1/-1", value=0)
    act(s, "p1", type="set_counter", card_id=holder.id, kind="charge", value=3)
    mana(s, C=2, B=2)
    act(s, "p1", type="cast_spell", card_id=target.id)
    saved = tmp_path / "saved.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_controller_tutors import answer
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
mode,source,holder,target=sys.argv[3:7]
receipt=s.state.rules.decision.resume['counter_choice72']
assert receipt['originals'][0]['card']==holder
if mode=='reincarnated':
 act(s,'p1',type='move',card_ids=[holder],to={'player':'p1','zone':'hand'})
 act(s,'p1',type='move',card_ids=[holder],to={'player':'p1','zone':'battlefield'})
 act(s,'p1',type='set_counter',card_id=holder,kind='charge',value=3)
elif mode=='missing_originals':
 receipt.pop('originals')
before=s.state.model_dump(mode='json')
if mode=='valid':
 answer(s,[source]);settle(s)
 assert s.state.cards[target].zone=='p1:battlefield'
 assert s.state.cards[source].zone=='p1:graveyard'
 assert not s.state.cards[holder].counters.get('charge')
 roundtrip(s)
else:
 try:act(s,'p1',type='choose',decision_id=s.state.rules.decision.id,option_ids=[source])
 except ActionError:pass
 else:raise AssertionError('Unknown or reincarnated counter holder was accepted')
 assert s.state.model_dump(mode='json')==before
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), mode, source.id, holder.id, target.id],
        capture_output=True,
        text=True,
        timeout=120,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_canonical_dawnhand_only_after_native_counter_order_foundation(cards):
    from app.rules.coverage import of_card_data

    result = of_card_data(cards.resolve("Dawnhand Dissident"))
    assert result.level == "FULL", result


@pytest.mark.parametrize("name,owner", [("Sol Ring", "p1"), ("Grizzly Bears", "p2")])
def test_dawnhand_actual_exile_does_not_authorize_noncreature_or_foreign_owned_card(cards, name, owner):
    s = setup(cards)
    source = cast(s, "Dawnhand Dissident")
    payer = cast(s, "Coram, the Undertaker")
    target = put(s, name, "graveyard", pid=owner)
    to_phase(s, "main1", turn=4)
    settle(s)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability(s, source, "{T}, Blight 2"),
        targets=[target.id],
        cost_choices=[{"component": 1, "cards": [payer.id]}],
    )
    settle(s)
    assert s.state.cards[target.id].zone == owner + ":exile"
    act(s, "p1", type="set_counter", card_id=source.id, kind="charge", value=3)
    mana(s, C=10, G=10)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=target.id)
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


@pytest.mark.parametrize("duplicate", [False, True])
def test_actual_hierophant_printed_counter_reduction_and_dawnhand_cost_use_distinct_counters_on_same_holder(
    cards,
    duplicate,
):
    s = setup(cards)
    source = cast(s, "Dawnhand Dissident")
    payer = cast(s, "Coram, the Undertaker")
    target = put(s, "Hierophant Bio-Titan", "graveyard")
    to_phase(s, "main1", turn=4)
    settle(s)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability(s, source, "{T}, Blight 2"),
        targets=[target.id],
        cost_choices=[{"component": 1, "cards": [payer.id]}],
    )
    settle(s)
    act(s, "p1", type="set_counter", card_id=source.id, kind="+1/+1", value=4)
    tokens = list(counter_tokens(Plan(s.state, "p1", cards, None), [source.id]))
    mana(s, C=8, G=2)
    if duplicate:
        before = s.state.model_dump(mode="json")
        with pytest.raises(ActionError):
            act(
                s,
                "p1",
                type="cast_spell",
                card_id=target.id,
                optional_costs=[target.id + ":reduce"],
                cost_choices=[{"component": 0, "cards": tokens[:3]}, {"component": 1, "cards": [tokens[0]]}],
            )
        assert s.state.model_dump(mode="json") == before
        return
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=target.id,
        optional_costs=[target.id + ":reduce"],
        cost_choices=[{"component": 0, "cards": tokens[:3]}, {"component": 1, "cards": tokens[3:]}],
    )
    settle(s)
    assert s.state.cards[target.id].zone == "p1:battlefield"
    assert not s.state.cards[source.id].counters.get("+1/+1")
    roundtrip(s)


def test_falco_actual_hierophant_also_shares_holder_but_never_counter_tokens(cards):
    from tests.test_rules_refused_look import stack_library

    s = setup(cards)
    source = cast(s, "Falco Spara, Pactweaver")
    target = stack_library(s, ["Hierophant Bio-Titan", "Forest"])[0]
    act(s, "p1", type="set_counter", card_id=source.id, kind="shield", value=0)
    act(s, "p1", type="set_counter", card_id=source.id, kind="+1/+1", value=4)
    tokens = list(counter_tokens(Plan(s.state, "p1", cards, None), [source.id]))
    act(s, "p1", type="clear_mana")
    mana(s, C=4, G=2)
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=target,
        optional_costs=[target + ":reduce"],
        cost_choices=[{"component": 0, "cards": tokens[:1]}, {"component": 1, "cards": tokens[1:]}],
    )
    settle(s)
    assert s.state.cards[target].zone == "p1:battlefield"
    assert not s.state.cards[source.id].counters.get("+1/+1")
    roundtrip(s)


def test_dawnhand_native_blight_one_surveil_executes_actual_first_ability(cards):
    from tests.test_rules_refused_look import stack_library

    s = setup(cards)
    source = cast(s, "Dawnhand Dissident")
    payer = cast(s, "Coram, the Undertaker")
    to_phase(s, "main1", turn=4)
    settle(s)
    top = stack_library(s, ["Lightning Bolt", "Forest"])
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability(s, source, "{T}, Blight 1"),
        cost_choices=[{"component": 1, "cards": [payer.id]}],
    )
    settle(s)
    d = s.state.rules.decision
    assert d and "surveil" in d.prompt.lower()
    assert s.state.cards[payer.id].counters.get("-1/-1") == 1
    answer(s, [top[0]])
    settle(s)
    assert s.state.cards[top[0]].zone == "p1:graveyard"
    roundtrip(s)


def test_dawnhand_native_link_survives_control_change_and_new_controller_uses_only_owned_card(cards):
    from tests.test_rules_bandmate_references import wait_priority

    s = setup(cards)
    source = cast(s, "Dawnhand Dissident")
    payer = cast(s, "Coram, the Undertaker")
    target = put(s, "Grizzly Bears", "graveyard", pid="p2")
    to_phase(s, "main1", turn=4)
    settle(s)
    act(
        s,
        "p1",
        type="activate_ability",
        card_id=source.id,
        ability=ability(s, source, "{T}, Blight 2"),
        targets=[target.id],
        cost_choices=[{"component": 1, "cards": [payer.id]}],
    )
    settle(s)
    original = s.state.rules.object_id(source.id)
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    act(s, "p2", type="set_counter", card_id=source.id, kind="charge", value=3)
    to_phase(s, "main1", turn=5)
    settle(s)
    wait_priority(s, "p2")
    mana(s, pid="p2", C=1, G=1)
    assert s.state.turn.active_player == "p2"
    assert s.state.rules.object_id(source.id) == original
    act(s, "p2", type="cast_spell", card_id=target.id)
    settle(s)
    assert s.state.cards[target.id].zone == "p2:battlefield"
    assert not s.state.cards[source.id].counters.get("charge")
    roundtrip(s)
