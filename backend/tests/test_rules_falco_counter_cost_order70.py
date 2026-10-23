"""Native chosen counter resources precede same-holder casualty sacrifices."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules.cost_payment import counter_tokens
from app.rules.plan import Plan
from tests.test_rules_top_library_authorities69 import (
    act,
    answer,
    cast,
    put,
    roundtrip,
    settle,
    setup,
    stack_library,
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
        "falco_counter_cost_order70_cards.json",
    ]:
        for i, c in enumerate(json.loads((Path(__file__).parent / "fixtures" / filename).read_text())):
            base[c["name"]] = card(
                c["name"],
                set_code="fc70",
                number=str(i),
                **{k: v for k, v in c.items() if k not in {"name", "set_code"}},
            )
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def prepare(cards, creature="Grizzly Bears", kind="+1/+1"):
    s = setup(cards)
    falco = cast(s, "Falco Spara, Pactweaver")
    bear = put(s, creature, "battlefield")
    act(s, "p1", type="set_counter", card_id=bear.id, kind=kind, value=1)
    enemy = put(s, "Grizzly Bears", "battlefield", pid="p2")
    top = stack_library(s, ["Light 'Em Up", "Forest"])
    token = next(
        t for t, (_, k) in counter_tokens(Plan(s.state, "p1", cards, None), [bear.id]).items() if k == kind
    )
    return s, falco, bear, enemy, top[0], token


def announce(s, bear, enemy, top, token, *, counter=True):
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=top,
        targets=[enemy.id],
        optional_costs=[top + ":casualty"],
        cost_choices=[
            *([{"component": 0, "cards": [token]}] if counter else []),
            {"component": 1, "cards": [bear.id]},
        ],
    )


@pytest.mark.parametrize("kind", ["+1/+1", "-1/-1", "shield"])
def test_same_creature_pays_counter_then_casualty_using_native_post_removal_power(cards, kind):
    s, falco, bear, enemy, top, token = prepare(cards, kind=kind)
    oid = s.state.rules.object_id(bear.id)
    announce(s, bear, enemy, top, token)
    settle(s)
    d = s.state.rules.decision
    assert d and d.resume["step"] == "copy_target"
    paid = next(p for p in s.state.rules.payments.values() if p.card == top)
    assert paid.sacrificed == [bear.id] and paid.sacrificed_objects == [oid]
    assert s.state.rules.lki[oid].power == 2
    assert not s.state.rules.lki[oid].counters.get(kind)
    answer(s, ["keep"])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:graveyard"
    assert s.state.cards[enemy.id].zone == "p2:graveyard"
    assert s.state.cards[falco.id].counters.get("shield") == 1
    roundtrip(s)


def test_counter_removal_lowering_power_below_casualty_threshold_is_atomic(cards):
    s, falco, bear, enemy, top, token = prepare(cards, creature="Llanowar Elves")
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match="Sacrifice a creature with power 2 or greater"):
        announce(s, bear, enemy, top, token)
    assert s.state.model_dump(mode="json") == before
    assert s.state.cards[bear.id].counters["+1/+1"] == 1
    roundtrip(s)


def test_native_counter_choice_can_be_cancelled_without_any_payment(cards):
    s, falco, bear, enemy, top, token = prepare(cards)
    announce(s, bear, enemy, top, token, counter=False)
    d = s.state.rules.decision
    assert d and d.resume["step"] == "ability_cost"
    assert any(o.id == token for o in d.options)
    answer(s, [])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    assert s.state.cards[top].zone == "p1:library"
    assert s.state.cards[bear.id].counters["+1/+1"] == 1
    roundtrip(s)


def test_native_counter_choice_rejects_new_incarnation_of_same_physical_holder(cards):
    s, falco, bear, enemy, top, token = prepare(cards)
    announce(s, bear, enemy, top, token, counter=False)
    d = s.state.rules.decision
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="set_counter", card_id=bear.id, kind="+1/+1", value=1)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match="original object"):
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[token])
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


@pytest.mark.parametrize("kind", ["counter", "payment"])
def test_actual_cold_counter_choice_or_mana_confirmation_preserves_paid_resource(cards, tmp_path, kind):
    s, falco, bear, enemy, top, token = prepare(cards)
    if kind == "payment":
        act(s, "p1", type="configure", automation_options={"auto_mana_payment": False})
    announce(s, bear, enemy, top, token, counter=kind == "payment")
    d = s.state.rules.decision
    assert d
    if kind == "payment":
        assert d.resume.get("counter_first70") and len(d.resume["counter_cost_origins70"]) == 1
    else:
        assert d.resume["step"] == "ability_cost"
    p = tmp_path / "saved.json"
    p.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
bear,top,answer=sys.argv[3:6];d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=[answer]);settle(s)
d=s.state.rules.decision
assert d and d.resume['step']=='copy_target'
assert any(p.card==top and p.sacrificed==[bear] for p in s.state.rules.payments.values())
act(s,d.player,type='choose',decision_id=d.id,option_ids=['keep']);settle(s)
assert s.state.cards[bear].zone=='p1:graveyard'
assert s.state.cards[top].zone=='p1:graveyard'
roundtrip(s)
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(p),
            str(cards.db_path),
            bear.id,
            top,
            "pay" if kind == "payment" else token,
        ],
        text=True,
        capture_output=True,
        timeout=60,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("mode", ["new_object", "legacy"])
def test_payment_confirmation_rejects_new_holder_or_unknown_original_receipt(cards, mode):
    from app.game.state import GameState

    s, falco, bear, enemy, top, token = prepare(cards)
    act(s, "p1", type="configure", automation_options={"auto_mana_payment": False})
    announce(s, bear, enemy, top, token)
    d = s.state.rules.decision
    assert d and d.resume.get("counter_first70")
    if mode == "new_object":
        act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "hand"})
        act(s, "p1", type="move", card_ids=[bear.id], to={"player": "p1", "zone": "battlefield"})
        act(s, "p1", type="set_counter", card_id=bear.id, kind="+1/+1", value=1)
    else:
        old = s.state.model_dump(mode="json")
        old["rules"]["decision"]["resume"].pop("counter_cost_origins70")
        s.state = GameState.model_validate(old)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match="original counter holder|original object"):
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay"])
    assert s.state.model_dump(mode="json") == before
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    if mode == "new_object":
        roundtrip(s)


@pytest.mark.parametrize("repeat_same_sacrifice", [False, True])
def test_printed_sacrifice_precedes_counter_component_but_counter_is_paid_first_and_no_double_sacrifice(
    cards, repeat_same_sacrifice
):
    from tests.test_rules_top_library_authorities69 import NAMES, SUPPORT, gameplay

    s = gameplay.setup(cards, *NAMES, *SUPPORT, "Village Rites", "Anhelo, the Painter")
    falco = cast(s, "Falco Spara, Pactweaver")
    cast(s, "Anhelo, the Painter")
    bear = put(s, "Grizzly Bears", "battlefield")
    act(s, "p1", type="set_counter", card_id=bear.id, kind="+1/+1", value=1)
    top = stack_library(s, ["Village Rites", "Forest"])[0]
    token = next(iter(counter_tokens(Plan(s.state, "p1", cards, None), [bear.id])))
    before = s.state.model_dump(mode="json")
    payload = {
        "type": "cast_spell",
        "card_id": top,
        "optional_costs": [top + ":casualty"],
        "cost_choices": [
            {"component": 0, "cards": [bear.id]},
            {"component": 1, "cards": [token]},
            {"component": 2, "cards": [bear.id if repeat_same_sacrifice else falco.id]},
        ],
    }
    if repeat_same_sacrifice:
        with pytest.raises(ActionError, match="Sacrifice a creature with power 2 or greater"):
            act(s, "p1", **payload)
        assert s.state.model_dump(mode="json") == before
    else:
        old_hand = len(s.state.zones["p1:hand"])
        act(s, "p1", **payload)
        settle(s)
        assert s.state.cards[bear.id].zone == "p1:graveyard"
        assert s.state.cards[falco.id].zone == "p1:graveyard"
        assert len(s.state.zones["p1:hand"]) == old_hand + 4
        assert not s.state.rules.decision
    roundtrip(s)


def test_whole_falco_definition_is_complete(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve("Falco Spara, Pactweaver")).level == "FULL"


def test_automatically_selected_only_counter_on_permission_source_is_paid_once(cards):
    s = setup(cards)
    falco = cast(s, "Falco Spara, Pactweaver")
    assert s.state.cards[falco.id].counters.get("shield") == 1
    top = stack_library(s, ["Lightning Bolt", "Forest"])[0]
    act(s, "p1", type="cast_spell", card_id=top, targets=["p2"])
    settle(s)
    assert s.state.players["p2"].life == 37
    assert not s.state.cards[falco.id].counters.get("shield")
    assert not s.state.rules.decision
    roundtrip(s)


@pytest.mark.parametrize("invalid_holder", ["opponent", "noncreature"])
def test_falco_cannot_pay_from_counter_on_opponent_or_own_noncreature(cards, invalid_holder):
    s, falco, bear, enemy, top, token = prepare(cards)
    bad = enemy if invalid_holder == "opponent" else put(s, "Sol Ring", "battlefield")
    act(s, "p1", type="set_counter", card_id=bad.id, kind="charge", value=1)
    invalid = next(
        t
        for t, (_, kind) in counter_tokens(Plan(s.state, "p1", cards, None), [bad.id]).items()
        if kind == "charge"
    )
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError, match="counter"):
        announce(s, bear, enemy, top, invalid)
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


def test_ordinary_legacy_mana_confirmation_does_not_require_counter_metadata(cards):
    from app.game.state import GameState

    s = setup(cards)
    bolt = put(s, "Lightning Bolt", "hand")
    act(s, "p1", type="configure", automation_options={"auto_mana_payment": False})
    from tests.test_rules_bandmate_references import mana

    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    d = s.state.rules.decision
    assert d and "counter_first70" not in d.resume
    old = s.state.model_dump(mode="json")
    s.state = GameState.model_validate(old)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    settle(s)
    assert s.state.players["p2"].life == 37
    roundtrip(s)


def test_counter_cost_mana_confirmation_cancel_does_not_remove_counter_or_sacrifice(cards):
    s, falco, bear, enemy, top, token = prepare(cards)
    act(s, "p1", type="configure", automation_options={"auto_mana_payment": False})
    announce(s, bear, enemy, top, token)
    d = s.state.rules.decision
    assert d and d.resume.get("counter_first70")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["cancel"])
    settle(s)
    assert s.state.cards[bear.id].zone == "p1:battlefield"
    assert s.state.cards[bear.id].counters["+1/+1"] == 1
    assert s.state.cards[top].zone == "p1:library"
    roundtrip(s)


def test_genuine_cold_automatic_source_only_shield_payment(cards, tmp_path):
    s = setup(cards)
    falco = cast(s, "Falco Spara, Pactweaver")
    top = stack_library(s, ["Lightning Bolt", "Forest"])[0]
    act(s, "p1", type="configure", automation_options={"auto_mana_payment": False})
    act(s, "p1", type="cast_spell", card_id=top, targets=["p2"])
    d = s.state.rules.decision
    assert d and d.resume.get("counter_first70")
    assert d.resume["counter_cost_origins70"][0]["card"] == falco.id
    p = tmp_path / "saved.json"
    p.write_text(s.state.model_dump_json())
    code = """
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
p=Path(sys.argv[1]);repo=CardRepository(Path(sys.argv[2]),ImageStore(p.parent/'images'))
s=GameSession(GameState.model_validate_json(p.read_text()),cards=repo)
d=s.state.rules.decision
act(s,d.player,type='choose',decision_id=d.id,option_ids=['pay']);settle(s)
assert not s.state.cards[sys.argv[3]].counters.get('shield')
assert s.state.players['p2'].life==37
assert s.state.cards[sys.argv[4]].zone=='p1:graveyard'
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(p), str(cards.db_path), falco.id, top],
        text=True,
        capture_output=True,
        timeout=60,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stdout + result.stderr
