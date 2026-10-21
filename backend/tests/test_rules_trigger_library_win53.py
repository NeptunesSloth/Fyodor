"""Battle of Wits uses exact native library thresholds and original trigger controller."""
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

NAME = 'Battle of Wits'
DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_library_win53_cards.json').read_text())
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


def cast(s, name, pool, targets=(), *, pid='p1', resolve=True):
    wait_priority(s, pid)
    c = put(s, name, 'hand', pid)
    mana(s, pid=pid, **pool)
    act(s, pid, type='cast_spell', card_id=c.id, sources=[], targets=list(targets))
    if resolve:
        settle(s)
    return c




def setup(cards, count=200, blocked=False):
    s = table(cards, NAMES + ['Island'] * 230, NAMES, NAMES)
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    source = cast(s, NAME, {'C': 3, 'U': 2})
    for name in ['Inspiration', 'Boomerang', 'Flicker of Fate']:
        put(s, name, 'hand')
    if blocked:
        cast(s, 'Abyssal Persecutor', {'C': 2, 'B': 2})
    library = s.state.zones['p1:library']
    assert len(library) > count
    act(s, 'p1', type='move', card_ids=list(library[count:]), to={'player': 'p1', 'zone': 'exile'})
    assert len(s.state.zones['p1:library']) == count
    return s, source


def pending(cards, count=200, blocked=False):
    s, source = setup(cards, count, blocked)
    to_phase(s, 'upkeep', turn=7)
    return s, source


def test_actual_whole_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == 'FULL'


@pytest.mark.parametrize('count', [199, 200, 201])
def test_native_exact_threshold_and_winner(cards, count):
    s, source = pending(cards, count)
    assert bool(s.state.zones['stack']) == (count >= 200)
    settle(s)
    assert s.state.rules.winner == ('p1' if count >= 200 else None)
    assert source.zone == 'p1:battlefield'
    roundtrip(s)


def test_native_resolution_rechecks_library_after_real_draw_spell(cards):
    s, source = pending(cards, 201)
    assert s.state.zones['stack']
    cast(s, 'Inspiration', {'C': 3, 'U': 1}, ['p1'])
    assert len(s.state.zones['p1:library']) == 199
    assert s.state.rules.winner is None and source.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('mode', ['bounce', 'blink', 'control'])
def test_native_original_trigger_controller_and_source_incarnation(cards, mode):
    s, source = pending(cards)
    old = s.state.rules.object_id(source.id)
    if mode == 'control':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
        settle(s)
        assert source.zone == 'p2:battlefield'
    elif mode == 'bounce':
        cast(s, 'Boomerang', {'U': 2}, [source.id])
        assert source.zone == 'p1:hand'
    else:
        cast(s, 'Flicker of Fate', {'C': 1, 'W': 1}, [source.id])
        assert s.state.rules.object_id(source.id) != old
    assert len(s.state.zones['p1:library']) == 200 and s.state.rules.winner == 'p1'
    roundtrip(s)


def test_native_cannot_win_static_prevents_actual_win(cards):
    s, source = pending(cards, blocked=True)
    settle(s)
    assert s.state.rules.winner is None and source.zone == 'p1:battlefield'
    assert not s.state.rules.lost
    roundtrip(s)


@pytest.mark.parametrize('mode', ['win', 'recheck'])
def test_true_cold_native_library_condition_and_win(cards, tmp_path, mode):
    import subprocess
    import sys

    s, source = pending(cards)
    saved = tmp_path / 'library53.json'
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
from tests.test_rules_trigger_library_win53 import cast
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
assert s.state.zones['stack']
if sys.argv[3]=='recheck':
    cast(s,'Inspiration',{'C':3,'U':1},['p1'])
    assert len(s.state.zones['p1:library'])==198 and s.state.rules.winner is None
else:
    settle(s)
    assert s.state.rules.winner=='p1'
roundtrip(s)
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), mode],
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_reaching_threshold_after_upkeep_does_not_retroactively_trigger(cards):
    s, source = setup(cards, 199)
    reclaim = put(s, 'Reclaim', 'hand')
    island = put(s, 'Island', 'graveyard')
    # Both ordinary setup moves came out of the library; restore a concrete
    # 199-card library before the upkeep using ordinary owned card movement.
    needed = 199 - len(s.state.zones['p1:library'])
    removed = [c for c in s.state.cards.values() if c.zone == 'p1:exile'][:needed]
    act(s, 'p1', type='move', card_ids=[c.id for c in removed], to={'player': 'p1', 'zone': 'library'})
    assert len(s.state.zones['p1:library']) == 199
    to_phase(s, 'upkeep', turn=7)
    assert not s.state.zones['stack']
    cast(s, 'Reclaim', {'G': 1}, [island.id])
    assert reclaim.zone == 'p1:graveyard' and len(s.state.zones['p1:library']) == 200
    assert s.state.rules.winner is None and source.zone == 'p1:battlefield'
    roundtrip(s)
