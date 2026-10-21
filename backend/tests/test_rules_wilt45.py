"""Catalog-discovered conditional reduction and complete Wilt exile rider."""

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_conditional_prevention import cast
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game


def prepare(cards, departures=0, owner="p1", tough=False):
    s = game(cards, ["Wilt in the Heat", "Hover Barrier", "Murder"])
    source = put(s, "Wilt in the Heat", "hand")
    target = put(s, "Hover Barrier" if tough else "Grizzly Bears", "battlefield", "p2")
    moved = [c.id for c in s.state.cards.values() if c.zone == owner + ":library"][:departures]
    if moved:
        act(s, owner, type="move", card_ids=moved, to={"player": owner, "zone": "graveyard"})
        act(s, owner, type="move", card_ids=moved, to={"player": owner, "zone": "exile"})
    mana(s, W=1, R=1)
    return s, source, target


@pytest.mark.parametrize("departures", [1, 3])
def test_actual_wilt_discount_uses_one_or_more_not_current_gy_count(cards, departures):
    s, source, target = prepare(cards, departures)
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[target.id], sources=[])
    settle(s)
    assert target.zone == "p2:exile" and source.zone == "p1:graveyard"
    assert s.state.players["p1"].mana == {}
    roundtrip(s)


@pytest.mark.parametrize("departures,owner", [(0, "p1"), (1, "p2")])
def test_actual_wilt_does_not_discount_no_own_departures(cards, departures, owner):
    s, source, target = prepare(cards, departures, owner)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, targets=[target.id], sources=[])
    assert source.zone == "p1:hand" and target.zone == "p2:battlefield" and target.damage == 0
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[target.id], sources=[])
    settle(s)
    assert target.zone == "p2:exile"
    roundtrip(s)


def test_wilt_surviving_creature_exiled_on_later_same_turn_death(cards):
    s, source, target = prepare(cards, 1, tough=True)
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[target.id], sources=[])
    settle(s)
    assert target.zone == "p2:battlefield" and target.damage == 5
    cast(s, "Murder", [target.id], pid="p2")
    assert target.zone == "p2:exile"
    roundtrip(s)


def test_wilt_full_actual_canonical(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve("Wilt in the Heat")).level == "FULL"


def test_wilt_true_cold_history_discount_before_cast(cards, tmp_path):
    import subprocess
    import sys

    s, source, target = prepare(cards, 1)
    saved = tmp_path / "wilt.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_designations import settle,roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
act(s,'p1',type='cast_spell',card_id=sys.argv[3],targets=[sys.argv[4]],sources=[])
settle(s)
assert s.state.cards[sys.argv[3]].zone=='p1:graveyard'
assert s.state.cards[sys.argv[4]].zone=='p2:exile'
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id, target.id],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
