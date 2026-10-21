"""An end-step discount observes both the active player and current step."""

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_life_sequences44 import cards as cards
from tests.test_rules_life_sequences44 import game
from tests.test_rules_wave30m_durations import to_phase


def setup(cards, phase="end", turn=4):
    s = game(cards, ["Closing Statement"])
    source = put(s, "Closing Statement", "hand")
    enemy = put(s, "Grizzly Bears", "battlefield", "p2")
    ours = put(s, "Llanowar Elves", "battlefield")
    to_phase(s, phase, turn=turn)
    return s, source, enemy, ours


def test_complete_canonical_statement(cards):
    assert coverage.of_card_data(cards.resolve("Closing Statement")).level == "FULL"


def test_own_end_step_discount_resolves_both_target_groups(cards):
    s, source, enemy, ours = setup(cards)
    mana(s, C=1, W=1, B=1)
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[enemy.id, ours.id], target_counts=[1, 1], sources=[])
    settle(s)
    assert enemy.zone == "p2:graveyard"
    assert ours.counters.get("+1/+1") == 1
    assert source.zone == "p1:graveyard"
    assert not s.state.players["p1"].mana
    roundtrip(s)


@pytest.mark.parametrize("phase,turn", [("main1", 4), ("main2", 4), ("end", 5)])
def test_other_steps_and_opponents_end_step_do_not_discount(cards, phase, turn):
    s, source, enemy, ours = setup(cards, phase, turn)
    from tests.test_rules_bandmate_references import wait_priority

    wait_priority(s, "p1")
    mana(s, C=1, W=1, B=1)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=source.id, targets=[enemy.id, ours.id], target_counts=[1, 1], sources=[])
    assert s.state.model_dump_json() == before
    mana(s, C=2)
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[enemy.id, ours.id], target_counts=[1, 1], sources=[])
    settle(s)
    assert enemy.zone == "p2:graveyard"
    assert ours.counters.get("+1/+1") == 1
    assert not s.state.players["p1"].mana
    roundtrip(s)


def test_optional_second_target_can_be_omitted(cards):
    s, source, enemy, ours = setup(cards)
    mana(s, C=1, W=1, B=1)
    act(s, "p1", type="cast_spell", card_id=source.id, targets=[enemy.id], target_counts=[1, 0], sources=[])
    settle(s)
    assert enemy.zone == "p2:graveyard" and not ours.counters
    roundtrip(s)


def test_true_cold_end_step_cost_and_resolution(cards, tmp_path):
    import subprocess
    import sys

    s, source, enemy, ours = setup(cards)
    saved = tmp_path / "closing49.json"
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
mana(s,C=1,W=1,B=1)
act(s,'p1',type='cast_spell',card_id=sys.argv[3],targets=[sys.argv[4],sys.argv[5]],target_counts=[1,1],sources=[])
settle(s)
assert s.state.cards[sys.argv[4]].zone=='p2:graveyard'
assert s.state.cards[sys.argv[5]].counters.get('+1/+1')==1
assert not s.state.players['p1'].mana
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(saved), str(cards.db_path), source.id, enemy.id, ours.id],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
