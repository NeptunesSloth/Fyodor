"""Bogardan Phoenix follows its death incarnation and checks counters as it died."""

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditional_prevention import cast
from tests.test_rules_designations import roundtrip, settle
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game
from tests.test_rules_mistmoon46 import kill_pending


def setup(cards):
    s = game(cards, ["Bogardan Phoenix", "Murder", "Cloudshift", "Solemnity"])
    phoenix = cast(s, "Bogardan Phoenix")
    return s, phoenix


def test_complete_canonical_phoenix(cards):
    assert coverage.of_card_data(cards.resolve("Bogardan Phoenix")).level == "FULL"


def test_first_death_returns_with_counter_second_death_exiles(cards):
    s, phoenix = setup(cards)
    old = s.state.rules.object_id(phoenix.id)
    cast(s, "Murder", [phoenix.id], pid="p2")
    assert phoenix.zone == "p1:battlefield" and phoenix.counters == {"death": 1}
    assert s.state.rules.object_id(phoenix.id) != old
    assert "flying" in Plan(s.state, "p1", cards, None).ch(phoenix).keywords
    cast(s, "Murder", [phoenix.id], pid="p2")
    assert phoenix.zone == "p1:exile"
    roundtrip(s)


def test_preexisting_death_counter_is_checked_in_dying_snapshot(cards):
    s, phoenix = setup(cards)
    act(s, "p1", type="counter", card_ids=[phoenix.id], kind="death", delta=2)
    kill_pending(s, phoenix)
    assert phoenix.counters == {}
    settle(s)
    assert phoenix.zone == "p1:exile"
    roundtrip(s)


def test_removed_death_counter_allows_return_again(cards):
    s, phoenix = setup(cards)
    cast(s, "Murder", [phoenix.id], pid="p2")
    act(s, "p1", type="counter", card_ids=[phoenix.id], kind="death", delta=-1)
    cast(s, "Murder", [phoenix.id], pid="p2")
    assert phoenix.zone == "p1:battlefield" and phoenix.counters == {"death": 1}
    roundtrip(s)


def test_borrowed_source_returns_under_dying_controllers_control(cards):
    s, phoenix = setup(cards)
    act(s, "p1", type="set_controller", card_ids=[phoenix.id], player="p2")
    cast(s, "Murder", [phoenix.id], pid="p2")
    assert phoenix.zone == "p2:battlefield" and phoenix.owner == "p1" and phoenix.counters == {"death": 1}
    roundtrip(s)


def test_solemnity_prevents_counter_and_allows_repeated_return(cards):
    s, phoenix = setup(cards)
    cast(s, "Solemnity")
    for _ in range(2):
        cast(s, "Murder", [phoenix.id], pid="p2")
        assert phoenix.zone == "p1:battlefield" and not phoenix.counters
    roundtrip(s)


@pytest.mark.parametrize("had_counter", [False, True])
def test_dying_source_replaced_by_new_battlefield_incarnation_is_not_returned_or_counted(cards, had_counter):
    s, phoenix = setup(cards)
    if had_counter:
        act(s, "p1", type="counter", card_ids=[phoenix.id], kind="death", delta=1)
    kill_pending(s, phoenix)
    act(s, "p1", type="move", card_ids=[phoenix.id], to={"zone": "battlefield"})
    oid = s.state.rules.object_id(phoenix.id)
    settle(s)
    assert phoenix.zone == "p1:battlefield" and not phoenix.counters
    assert s.state.rules.object_id(phoenix.id) == oid
    roundtrip(s)


def test_blinked_phoenix_loses_old_death_counter_and_can_return(cards):
    s, phoenix = setup(cards)
    cast(s, "Murder", [phoenix.id], pid="p2")
    cast(s, "Cloudshift", [phoenix.id])
    assert not phoenix.counters
    cast(s, "Murder", [phoenix.id], pid="p2")
    assert phoenix.zone == "p1:battlefield" and phoenix.counters == {"death": 1}
    roundtrip(s)


@pytest.mark.parametrize("had_counter", [False, True])
def test_actual_death_snapshot_survives_true_cold_process(cards, tmp_path, had_counter):
    import subprocess
    import sys

    s, phoenix = setup(cards)
    if had_counter:
        cast(s, "Murder", [phoenix.id], pid="p2")
    kill_pending(s, phoenix)
    path = tmp_path / "phoenix47.json"
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
p=s.state.cards[sys.argv[3]]
if sys.argv[4]=='True':
    assert p.zone=='p1:exile'
else:
    assert p.zone=='p1:battlefield' and p.counters=={'death':1}
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(path), str(cards.db_path), phoenix.id, str(had_counter)],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
