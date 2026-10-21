"""Fevered Visions checks the frozen step player after the completed draw."""

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_trigger_step_counts50 import cards as cards
from tests.test_rules_wave30m_durations import stops, to_phase


def setup(cards, pid='p2', turn=5, hand=3):
    s = table(cards, ['Fevered Visions', 'Sol Ring', 'Notion Thief'], ['Sol Ring'], ['Sol Ring'])
    start(s)
    stops(s, 'main1', 'end')
    source = put(s, 'Fevered Visions', 'hand')
    mana(s, C=1, U=1, R=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    to_phase(s, 'main1', turn=turn)
    held = list(s.state.zones[pid + ':hand'])
    if held:
        act(s, pid, type='move', card_ids=held, to={'player': pid, 'zone': 'library'})
    chosen = list(s.state.zones[pid + ':library'])[:hand]
    if chosen:
        act(s, pid, type='move', card_ids=chosen, to={'player': pid, 'zone': 'hand'})
    assert len(s.state.zones[pid + ':hand']) == hand
    return s, source


def test_complete_canonical_visions(cards):
    assert coverage.of_card_data(cards.resolve('Fevered Visions')).level == 'FULL'


@pytest.mark.parametrize('pid,turn,hand,damage', [('p1', 4, 5, 0), ('p2', 5, 2, 0), ('p2', 5, 3, 2), ('p3', 6, 5, 2)])
def test_draw_precedes_opponent_hand_threshold_test(cards, pid, turn, hand, damage):
    s, _ = setup(cards, pid, turn, hand)
    life = s.state.players[pid].life
    to_phase(s, 'end', turn=turn)
    settle(s)
    assert len(s.state.zones[pid + ':hand']) == hand + 1
    assert s.state.players[pid].life == life - damage
    roundtrip(s)


@pytest.mark.parametrize('when,damage', [('before', 0), ('after', 2)])
def test_ability_controller_is_frozen_when_triggering(cards, when, damage):
    s, source = setup(cards)
    if when == 'before':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    to_phase(s, 'end', turn=5)
    if when == 'after':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    life = s.state.players['p2'].life
    settle(s)
    assert len(s.state.zones['p2:hand']) == 4
    assert s.state.players['p2'].life == life - damage
    roundtrip(s)


def test_source_departure_does_not_stop_draw_or_damage(cards):
    s, source = setup(cards)
    to_phase(s, 'end', turn=5)
    life = s.state.players['p2'].life
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    settle(s)
    assert len(s.state.zones['p2:hand']) == 4
    assert s.state.players['p2'].life == life - 2
    assert source.zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('hand,damage', [(3, 0), (4, 2)])
def test_replaced_draw_checks_unchanged_step_players_hand(cards, hand, damage):
    s, _ = setup(cards, hand=hand)
    put(s, 'Notion Thief', 'battlefield')
    before = len(s.state.zones['p1:hand'])
    life = s.state.players['p2'].life
    to_phase(s, 'end', turn=5)
    settle(s)
    assert len(s.state.zones['p2:hand']) == hand
    assert len(s.state.zones['p1:hand']) == before + 1
    assert s.state.players['p2'].life == life - damage
    roundtrip(s)


def test_true_cold_original_controller_and_step_player_survive_replaced_draw(cards, tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    import app

    s, source = setup(cards, hand=4)
    put(s, 'Notion Thief', 'battlefield')
    before = len(s.state.zones['p1:hand'])
    life = s.state.players['p2'].life
    to_phase(s, 'end', turn=5)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    saved = tmp_path / 'fevered50.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
settle(s)
assert len(s.state.zones['p2:hand'])==4
assert len(s.state.zones['p1:hand'])==int(sys.argv[3])+1
assert s.state.players['p2'].life==int(sys.argv[4])-2
roundtrip(s)
"""
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), str(before), str(life)],
        cwd=Path(app.__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
