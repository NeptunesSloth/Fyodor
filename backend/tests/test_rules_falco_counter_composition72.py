"""Native chosen counter resources precede same-holder casualty sacrifices."""

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules.cost_payment import counter_tokens
from app.rules.plan import Plan
from tests.test_rules_bandmate_references import mana
from tests.test_rules_top_library_authorities69 import (
    NAMES,
    SUPPORT,
    act,
    cast,
    gameplay,
    put,
    roundtrip,
    settle,
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
        "wave47c_cards.json",
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


def setup(cards):
    return gameplay.setup(cards, *NAMES, *SUPPORT, "Hierophant Bio-Titan")


@pytest.mark.parametrize("n", [0, 3])
def test_falco_actual_hierophant_also_shares_holder_but_never_counter_tokens(cards, n):
    from tests.test_rules_refused_look import stack_library

    s = setup(cards)
    source = cast(s, "Falco Spara, Pactweaver")
    target = stack_library(s, ["Hierophant Bio-Titan", "Forest"])[0]
    act(s, "p1", type="set_counter", card_id=source.id, kind="shield", value=0)
    act(s, "p1", type="set_counter", card_id=source.id, kind="+1/+1", value=4)
    tokens = list(counter_tokens(Plan(s.state, "p1", cards, None), [source.id]))
    act(s, "p1", type="clear_mana")
    mana(s, C=10 - 2 * n, G=2)
    act(
        s,
        "p1",
        type="cast_spell",
        card_id=target,
        optional_costs=[target + ":reduce"],
        cost_choices=[{"component": 0, "cards": tokens[:1]}, {"component": 1, "cards": tokens[1 : 1 + n]}],
    )
    settle(s)
    assert s.state.cards[target].zone == "p1:battlefield"
    assert s.state.cards[source.id].counters.get("+1/+1", 0) == 3 - n
    roundtrip(s)


def test_same_original_counter_cannot_pay_falco_and_hierophant_reduction(cards):
    from tests.test_rules_refused_look import stack_library

    s = setup(cards)
    source = cast(s, "Falco Spara, Pactweaver")
    target = stack_library(s, ["Hierophant Bio-Titan", "Forest"])[0]
    act(s, "p1", type="set_counter", card_id=source.id, kind="shield", value=0)
    act(s, "p1", type="set_counter", card_id=source.id, kind="+1/+1", value=4)
    tokens = list(counter_tokens(Plan(s.state, "p1", cards, None), [source.id]))
    act(s, "p1", type="clear_mana")
    mana(s, C=4, G=2)
    before = s.state.model_dump(mode="json")
    with pytest.raises(ActionError):
        act(
            s,
            "p1",
            type="cast_spell",
            card_id=target,
            optional_costs=[target + ":reduce"],
            cost_choices=[{"component": 0, "cards": tokens[:1]}, {"component": 1, "cards": tokens[:3]}],
        )
    assert s.state.model_dump(mode="json") == before
    roundtrip(s)


@pytest.mark.parametrize("mode", ["valid", "reincarnated", "missing_originals"])
def test_actual_cold_falco_hierophant_choice_keeps_original_counter_holder(cards, tmp_path, mode):
    import os
    import subprocess
    import sys

    from tests.test_rules_refused_look import stack_library

    s = setup(cards)
    source = cast(s, "Falco Spara, Pactweaver")
    holder = put(s, "Grizzly Bears", "battlefield")
    target = stack_library(s, ["Hierophant Bio-Titan", "Forest"])[0]
    act(s, "p1", type="set_counter", card_id=source.id, kind="shield", value=0)
    act(s, "p1", type="set_counter", card_id=holder.id, kind="+1/+1", value=4)
    act(s, "p1", type="clear_mana")
    mana(s, C=4, G=2)
    act(s, "p1", type="cast_spell", card_id=target, optional_costs=[target + ":reduce"])
    decision = s.state.rules.decision
    assert decision and decision.resume["step"] == "ability_cost" and decision.resume["component"] == 1
    assert decision.resume["counter_choice72"]["originals"][0]["card"] == holder.id
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
d=s.state.rules.decision
options=[o.id for o in d.options]
assert len(options)==3,options
if mode=='reincarnated':
 act(s,'p1',type='move',card_ids=[holder],to={'player':'p1','zone':'hand'})
 act(s,'p1',type='move',card_ids=[holder],to={'player':'p1','zone':'battlefield'})
 act(s,'p1',type='set_counter',card_id=holder,kind='+1/+1',value=4)
elif mode=='missing_originals':
 d.resume['counter_choice72'].pop('originals')
before=s.state.model_dump(mode='json')
if mode=='valid':
 answer(s,options);settle(s)
 assert s.state.cards[target].zone=='p1:battlefield'
 assert not s.state.cards[holder].counters.get('+1/+1')
 roundtrip(s)
else:
 try:act(s,'p1',type='choose',decision_id=d.id,option_ids=options)
 except ActionError:pass
 else:raise AssertionError('Unknown or reincarnated counter holder accepted')
 assert s.state.model_dump(mode='json')==before
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), mode, source.id, holder.id, target],
        capture_output=True,
        text=True,
        timeout=120,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stdout + result.stderr
