"""Fear of Immobility's target is optional; the stun condition reads control as it resolves."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

NAME = 'Fear of Immobility'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_target_control50_cards.json').read_text())
NAMES = [c['name'] for c in DATA]


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards, pid='p2', tapped=False, replacement=None):
    s = table(cards, NAMES, NAMES, NAMES)
    start(s)
    target = put(s, 'Grizzly Bears', 'battlefield', pid)
    if tapped:
        act(s, pid, type='tap', card_ids=[target.id], tapped=True)
    if replacement:
        put(s, replacement, 'battlefield', pid)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = put(s, NAME, 'hand')
    mana(s, C=4, W=1)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    assert source.zone == 'p1:battlefield' and not s.state.players['p1'].mana
    d = s.state.rules.decision
    assert d is not None and d.player == 'p1' and d.min_choices == 0 and d.max_choices == 1
    return s, source, target


def announce(s, target=None):
    d = s.state.rules.decision
    assert d is not None
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[] if target is None else [target.id])


def test_complete_canonical_supported(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('pid', ['p2', 'p3'])
def test_native_opponent_target_is_tapped_and_gets_stun(cards, pid):
    s, source, target = setup(cards, pid)
    announce(s, target)
    settle(s)
    assert target.tapped and target.counters == {'stun': 1}
    roundtrip(s)


def test_native_own_target_taps_without_stun(cards):
    s, source, target = setup(cards, 'p1')
    announce(s, target)
    settle(s)
    assert target.tapped and not target.counters
    roundtrip(s)


def test_up_to_one_allows_zero_targets(cards):
    s, source, target = setup(cards)
    announce(s)
    settle(s)
    assert not target.tapped and not target.counters and not s.state.zones['stack']
    roundtrip(s)


def test_already_tapped_opponent_target_still_gets_stun(cards):
    s, source, target = setup(cards, tapped=True)
    announce(s, target)
    settle(s)
    assert target.tapped and target.counters == {'stun': 1}
    roundtrip(s)


@pytest.mark.parametrize('before,after,expected', [('p2', 'p1', 0), ('p1', 'p2', 1)])
def test_resolution_time_controller_change_determines_stun(cards, before, after, expected):
    s, source, target = setup(cards, before)
    announce(s, target)
    act(s, 'p1', type='set_controller', card_ids=[target.id], player=after)
    settle(s)
    assert target.tapped and target.counters.get('stun', 0) == expected
    roundtrip(s)


def test_native_blinked_target_successor_is_untouched(cards):
    s, source, target = setup(cards)
    announce(s, target)
    wait_priority(s, 'p1')
    flicker = put(s, 'Flicker of Fate', 'hand')
    mana(s, C=1, W=1)
    act(s, 'p1', type='cast_spell', card_id=flicker.id, targets=[target.id], sources=[])
    settle(s)
    assert target.zone == 'p2:battlefield' and not target.tapped and not target.counters
    roundtrip(s)


def test_native_stun_skips_one_untap_then_allows_next(cards):
    s, source, target = setup(cards)
    announce(s, target)
    settle(s)
    to_phase(s, 'upkeep', turn=5)
    settle(s)
    assert target.tapped and not target.counters
    to_phase(s, 'upkeep', turn=8)
    settle(s)
    assert not target.tapped
    roundtrip(s)


@pytest.mark.parametrize('replacement,n', [('Doubling Season', 2), ('Solemnity', 0)])
def test_native_counter_replacement_does_not_gate_tap(cards, replacement, n):
    s, source, target = setup(cards, replacement=replacement)
    announce(s, target)
    settle(s)
    assert target.tapped and target.counters.get('stun', 0) == n
    roundtrip(s)


@pytest.mark.parametrize('new_controller,expected', [('p2', 1), ('p1', 0)])
def test_true_cold_native_announced_target_and_current_control(cards, tmp_path, new_controller, expected):
    import subprocess
    import sys

    s, source, target = setup(cards)
    announce(s, target)
    if new_controller == 'p1':
        act(s, 'p1', type='set_controller', card_ids=[target.id], player='p1')
    saved = tmp_path / 'immobility50.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.repository import CardRepository
from app.cards.images import ImageStore
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.zones['stack']
settle(s)
target=s.state.cards[sys.argv[3]]
assert target.tapped and target.counters.get('stun',0)==int(sys.argv[4])
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), target.id, str(expected)],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
