"""Player-relative resolution tests versus genuine intervening conditions."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import stops, to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/trigger_step_damage50_cards.json').read_text())


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


def setup(cards, name):
    names = [c['name'] for c in DATA] + ['Sol Ring', 'Swamp', 'Grizzly Bears']
    s = table(cards, names, names, names)
    start(s)
    stops(s, 'main1', 'upkeep')
    source = put(s, name, 'hand')
    mana(s, C=4, B=1)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    return s, source


def hand(s, pid, n):
    held = list(s.state.zones[pid + ':hand'])
    if held:
        act(s, pid, type='move', card_ids=held, to={'player': pid, 'zone': 'library'})
    chosen = list(s.state.zones[pid + ':library'])[:n]
    if chosen:
        act(s, pid, type='move', card_ids=chosen, to={'player': pid, 'zone': 'hand'})
    assert len(s.state.zones[pid + ':hand']) == n


@pytest.mark.parametrize('name', ['Skullcage', 'Urborg Stalker'])
def test_canonical_complete(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('n,damage', [(0, 2), (2, 2), (3, 0), (4, 0), (5, 2)])
def test_skullcage_resolution_hand_sizes(cards, n, damage):
    s, _ = setup(cards, 'Skullcage')
    to_phase(s, 'main1', turn=5)
    hand(s, 'p2', n)
    life = s.state.players['p2'].life
    to_phase(s, 'upkeep', turn=8)
    settle(s)
    assert s.state.players['p2'].life == life - damage
    roundtrip(s)


@pytest.mark.parametrize('before,after,damage', [(3, 5, 2), (5, 3, 0)])
def test_skullcage_triggers_even_when_initial_hand_exempt(cards, before, after, damage):
    s, source = setup(cards, 'Skullcage')
    to_phase(s, 'main1', turn=5)
    hand(s, 'p2', before)
    to_phase(s, 'upkeep', turn=8)
    hand(s, 'p2', after)
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    life = s.state.players['p2'].life
    settle(s)
    assert s.state.players['p2'].life == life - damage


def test_skullcage_own_turn_never_triggers(cards):
    s, _ = setup(cards, 'Skullcage')
    life = s.state.players['p1'].life
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    assert s.state.players['p1'].life == life


@pytest.mark.parametrize('pid,turn', [('p1', 7), ('p2', 8), ('p3', 9)])
def test_stalker_each_player_checks_only_their_permanents(cards, pid, turn):
    s, _ = setup(cards, 'Urborg Stalker')
    to_phase(s, 'main1', turn=6)
    put(s, 'Sol Ring', 'battlefield', pid)
    life = s.state.players[pid].life
    to_phase(s, 'upkeep', turn=turn)
    settle(s)
    assert s.state.players[pid].life == life - 1
    roundtrip(s)


@pytest.mark.parametrize('qualifies', [False, True])
def test_stalker_intervening_condition_checked_twice(cards, qualifies):
    s, _ = setup(cards, 'Urborg Stalker')
    to_phase(s, 'main1', turn=6)
    put(s, 'Swamp', 'battlefield', 'p2')
    put(s, 'Urborg Stalker', 'battlefield', 'p2')
    ring = put(s, 'Sol Ring', 'battlefield', 'p2') if qualifies else None
    to_phase(s, 'upkeep', turn=8)
    if ring:
        act(s, 'p2', type='move', card_ids=[ring.id], to={'player': 'p2', 'zone': 'graveyard'})
    else:
        put(s, 'Sol Ring', 'battlefield', 'p2')
    life = s.state.players['p2'].life
    settle(s)
    assert s.state.players['p2'].life == life


@pytest.mark.parametrize('name,damage', [('Skullcage', 2), ('Urborg Stalker', 1)])
def test_pending_step_player_and_controller_survive_cold_source_departure(cards, tmp_path, name, damage):
    import os
    import subprocess
    import sys

    import app

    s, source = setup(cards, name)
    to_phase(s, 'main1', turn=6)
    hand(s, 'p2', 2)
    put(s, 'Sol Ring', 'battlefield', 'p2')
    to_phase(s, 'upkeep', turn=8)
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    life = s.state.players['p2'].life
    saved = tmp_path / 'step-damage.json'
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
assert s.state.players['p2'].life==int(sys.argv[3])-int(sys.argv[4])
roundtrip(s)
"""
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
    result = subprocess.run(
        [sys.executable, '-c', code, str(saved), str(cards.db_path), str(life), str(damage)],
        cwd=Path(app.__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
