"""Mistmoon Griffin reads the controller's actual graveyard order after exiling itself."""

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import cast, choose
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game


def setup(cards):
    s = game(
        cards, ["Mistmoon Griffin", "Murder", "Wrath of God", "Boomerang", "Cloudshift", "Grafdigger's Cage"]
    )
    griffin = cast(s, "Mistmoon Griffin")
    return s, griffin


def test_complete_canonical_griffin(cards):
    assert coverage.of_card_data(cards.resolve("Mistmoon Griffin")).level == "FULL"


def test_returns_top_creature_skipping_newer_noncreature_card_without_target_prompt(cards):
    s, griffin = setup(cards)
    lower = put(s, "Grizzly Bears", "graveyard")
    upper = put(s, "Llanowar Elves", "graveyard")
    put(s, "Forest", "graveyard")
    cast(s, "Murder", [griffin.id], pid="p2")
    assert griffin.zone == "p1:exile" and upper.zone == "p1:battlefield" and lower.zone == "p1:graveyard"
    assert not s.state.rules.decision
    roundtrip(s)


def test_no_other_creature_only_exiles_griffin(cards):
    s, griffin = setup(cards)
    cast(s, "Murder", [griffin.id], pid="p2")
    assert griffin.zone == "p1:exile" and not s.state.rules.decision
    roundtrip(s)


def kill_pending(s, griffin):
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    act(s, "p2", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    cast(s, "Murder", [griffin.id], pid="p2", resolve=False)
    for _ in range(12):
        if griffin.zone.endswith(":graveyard"):
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("Griffin did not die")


def test_source_already_gone_still_returns_top_and_does_not_exile_successor(cards):
    s, griffin = setup(cards)
    bear = put(s, "Grizzly Bears", "graveyard")
    kill_pending(s, griffin)
    act(s, "p1", type="move", card_ids=[griffin.id], to={"zone": "battlefield"})
    settle(s)
    assert griffin.zone == "p1:battlefield" and bear.zone == "p1:battlefield"
    roundtrip(s)


def test_borrowed_griffin_exiles_owners_card_but_reads_death_controllers_graveyard(cards):
    s, griffin = setup(cards)
    mine = put(s, "Grizzly Bears", "graveyard")
    theirs = put(s, "Llanowar Elves", "graveyard", "p2")
    act(s, "p1", type="set_controller", card_ids=[griffin.id], player="p2")
    cast(s, "Murder", [griffin.id], pid="p2")
    assert griffin.zone == "p1:exile" and theirs.zone == "p2:battlefield" and mine.zone == "p1:graveyard"
    roundtrip(s)


@pytest.mark.parametrize("top_name", ["Grizzly Bears", "Llanowar Elves"])
def test_simultaneous_wrath_deaths_honor_actual_owners_order(cards, top_name):
    s, griffin = setup(cards)
    bear = put(s, "Grizzly Bears", "battlefield")
    elf = put(s, "Llanowar Elves", "battlefield")
    act(s, "p1", type="set_prefs", hold_priority=True, auto_resolve_own_triggers="off")
    cast(s, "Wrath of God", resolve=False)
    for _ in range(16):
        d = s.state.rules.decision
        if d and (d.resume or {}).get("step") in {"graveyard_order", "death46_graveyard_order"}:
            break
        assert d is None
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d and d.kind == "order"
    top = bear if top_name == bear.name else elf
    ids = [top.id, *[c.id for c in [bear, elf, griffin] if c.id != top.id]]
    choose(s, ids)
    settle(s)
    assert top.zone == "p1:battlefield" and griffin.zone == "p1:exile"
    roundtrip(s)


def test_cage_prevents_return_without_substituting_lower_creature(cards):
    s, griffin = setup(cards)
    lower = put(s, "Grizzly Bears", "graveyard")
    upper = put(s, "Llanowar Elves", "graveyard")
    cast(s, "Grafdigger's Cage")
    cast(s, "Murder", [griffin.id], pid="p2")
    assert griffin.zone == "p1:exile" and upper.zone == lower.zone == "p1:graveyard"
    roundtrip(s)


def test_true_cold_saved_death_keeps_order_and_original_exile_identity(cards, tmp_path):
    import subprocess
    import sys

    s, griffin = setup(cards)
    bear = put(s, "Grizzly Bears", "graveyard")
    elf = put(s, "Llanowar Elves", "graveyard")
    kill_pending(s, griffin)
    path = tmp_path / "mistmoon46.json"
    path.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:exile'
assert s.state.cards[sys.argv[4]].zone=='p1:battlefield'
assert s.state.cards[sys.argv[5]].zone=='p1:graveyard'
roundtrip(s)
"""
    p = subprocess.run(
        [sys.executable, "-c", code, str(path), str(cards.db_path), griffin.id, elf.id, bear.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert p.returncode == 0, p.stdout + p.stderr
