"""Actual death outcomes preserve original object and target legality."""

import pytest

from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import cast, choose
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game


def test_actual_haunted_angel_exiles_then_each_other_player_creates_native_token(cards):
    s = game(cards, ["Haunted Angel", "Murder"])
    source = cast(s, "Haunted Angel")
    cast(s, "Murder", [source.id], pid="p2")
    angels = [c for c in s.state.cards.values() if c.is_token and c.name == "Angel"]
    assert source.zone == "p1:exile"
    assert sorted(c.controller for c in angels) == ["p2", "p3"]
    plan = Plan(s.state, "p1", cards, None)
    assert all(
        plan.ch(c).pt == (3, 3) and plan.ch(c).colors == {"B"} and "flying" in plan.ch(c).keywords
        for c in angels
    )
    roundtrip(s)


def test_actual_cyclopean_giant_land_change_is_permanent_and_source_exiled(cards):
    s = game(cards, ["Cyclopean Giant", "Murder"])
    source = cast(s, "Cyclopean Giant")
    target = put(s, "Forest", "battlefield", "p2")
    cast(s, "Murder", [source.id], pid="p2")
    assert s.state.rules.decision and source.zone == "p1:graveyard"
    choose(s, [target.id])
    ch = Plan(s.state, "p1", cards, None).ch(target)
    assert "Swamp" in ch.subtypes and "Forest" not in ch.subtypes
    assert source.zone == "p1:exile"
    roundtrip(s)


@pytest.mark.parametrize("name", ["Haunted Angel", "Cyclopean Giant"])
def test_exact_full_canonical_death_cards(cards, name):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_haunted_borrowed_source_exiles_owners_gy_but_other_players_follow_controller(cards):
    s = game(cards, ["Haunted Angel", "Murder"])
    source = cast(s, "Haunted Angel")
    act(s, "p1", type="set_controller", card_ids=[source.id], player="p2")
    cast(s, "Murder", [source.id], pid="p2")
    assert source.zone == "p1:exile"
    assert sorted(c.controller for c in s.state.cards.values() if c.is_token and c.name == "Angel") == [
        "p1",
        "p3",
    ]
    roundtrip(s)


def test_haunted_each_creating_players_native_multiplier_is_independent(cards):
    s = game(cards, ["Haunted Angel", "Murder", "Anointed Procession"])
    put(s, "Anointed Procession", "battlefield", "p2")
    source = cast(s, "Haunted Angel")
    cast(s, "Murder", [source.id], pid="p2")
    assert source.zone == "p1:exile"
    assert sorted(c.controller for c in s.state.cards.values() if c.is_token and c.name == "Angel") == [
        "p2",
        "p2",
        "p3",
    ]
    roundtrip(s)


def test_cyclopean_no_legal_target_does_not_exile_source(cards):
    s = game(cards, ["Cyclopean Giant", "Murder"])
    source = cast(s, "Cyclopean Giant")
    cast(s, "Murder", [source.id], pid="p2")
    assert source.zone == "p1:graveyard" and not s.state.rules.decision
    roundtrip(s)


def test_cyclopean_official_illegal_target_fizzles_exile_too(cards):
    s = game(cards, ["Cyclopean Giant", "Murder", "Boomerang"])
    source = cast(s, "Cyclopean Giant")
    target = put(s, "Forest", "battlefield", "p2")
    cast(s, "Murder", [source.id], pid="p2")
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[target.id])
    cast(s, "Boomerang", [target.id], pid="p2")
    assert target.zone == "p2:hand" and source.zone == "p1:graveyard"
    roundtrip(s)


def test_cyclopean_copy_in_gy_is_exiled_even_after_its_printed_identity_returns(cards):
    s = game(cards, ["Cyclopean Giant", "Murder", "Clone"])
    original = cast(s, "Cyclopean Giant")
    target = put(s, "Forest", "battlefield", "p2")
    copy = cast(s, "Clone")
    d = s.state.rules.decision
    assert d
    option = next(o.id for o in d.options if o.card_id == original.id or o.id == original.id)
    choose(s, [option])
    assert Plan(s.state, "p1", cards, None).ch(copy).name == "Cyclopean Giant"
    cast(s, "Murder", [copy.id], pid="p2")
    assert Plan(s.state, "p1", cards, None).ch(copy).name == "Clone"
    choose(s, [target.id])
    assert copy.zone == "p1:exile" and original.zone == "p1:battlefield"
    roundtrip(s)


@pytest.mark.parametrize("name", ["Haunted Angel", "Cyclopean Giant"])
def test_native_death_followup_genuine_fresh_process(cards, tmp_path, name):
    import subprocess
    import sys

    s = game(cards, [name, "Murder"])
    source = cast(s, name)
    target = put(s, "Forest", "battlefield", "p2") if name == "Cyclopean Giant" else None
    for pid in ("p1", "p2"):
        act(s, pid, type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    if name == "Cyclopean Giant":
        cast(s, "Murder", [source.id], pid="p2")
        assert s.state.rules.decision
    else:
        cast(s, "Murder", [source.id], pid="p2", resolve=False)
        for _ in range(12):
            if source.zone == "p1:graveyard":
                break
            act(s, s.state.rules.priority, type="pass_priority")
        assert source.zone == "p1:graveyard"
    saved = tmp_path / "death46.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
from tests.test_rules_conditional_prevention import choose
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
if sys.argv[4]!='none':
 choose(s,[sys.argv[4]])
 assert 'Swamp' in Plan(s.state,'p1',repo,None).ch(s.state.cards[sys.argv[4]]).subtypes
else:
 settle(s)
 assert sorted(c.controller for c in s.state.cards.values() if c.is_token and c.name=='Angel')==['p2','p3']
assert s.state.cards[sys.argv[3]].zone=='p1:exile'
roundtrip(s)
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(saved),
            str(cards.db_path),
            source.id,
            target.id if target else "none",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
