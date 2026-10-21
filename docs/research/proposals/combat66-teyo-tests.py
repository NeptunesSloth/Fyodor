"""Directional restrictions constrain declarations, never attack insertion or targets."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/combat_directions66_cards.json').read_text())
NAMES = ['Pramikon, Sky Rampart', 'Mystic Barrier', 'Teyo, Geometric Tactician']


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


def setup(cards):
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Sol Ring', 'Serra Angel', 'Lightning Bolt']
    s = table(cards, names, names, names)
    bears = {p: put(s, 'Grizzly Bears', 'battlefield', p) for p in ['p1', 'p2', 'p3']}
    start(s)
    return s, bears


def choose(s, value):
    d = s.state.rules.decision
    assert d is not None and value in [o.id for o in d.options]
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[value])
    settle(s)


def cast(s, name, targets=(), *, pid='p1', direction=None):
    source = put(s, name, 'hand', pid)
    mana(s, pid=pid, C=8, W=4, U=4, R=4, G=4, B=4)
    wait_priority(s, pid)
    act(s, pid, type='cast_spell', card_id=source.id, targets=list(targets), sources=[])
    settle(s)
    if direction is not None:
        choose(s, direction)
        assert source.choices.get('Chosen direction') == direction
    return source


def declare(s, bear, target, *, pid='p1', turn=4):
    to_phase(s, 'declare_attackers', turn=turn)
    act(s, pid, type='declare_attackers', attackers=[{'card_id': bear.id, 'target': target}])


def refuse(s, bear, target, *, pid='p1', turn=4):
    to_phase(s, 'declare_attackers', turn=turn)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, pid, type='declare_attackers', attackers=[{'card_id': bear.id, 'target': target}])
    assert s.state.model_dump_json() == before


def test_complete_canonical(cards):
    assert coverage.of_card_data(cards.resolve(NAMES[2])).level == 'FULL'


def activate_teyo(s, source, direction, *, targets=(), ability=2):
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=ability, targets=list(targets), sources=[])
    settle(s)
    if direction is not None:
        choose(s, direction)


def test_teyo_whole_native_token_draw_and_direction_expiration(cards):
    s, bears = setup(cards)
    source = cast(s, NAMES[2])
    wall = next(c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield')
    view = Plan(s.state, 'p1', s.cards, None)
    assert view.ch(wall).pt == (0, 4) and {'flying', 'defender'} <= view.ch(wall).keywords
    before = {p: len(s.state.zones[p + ':hand']) for p in ['p1', 'p2', 'p3']}
    activate_teyo(s, source, None, ability=1, targets=['p2'])
    assert all(len(s.state.zones[p + ':hand']) == before[p] + (p != 'p3') for p in before)
    to_phase(s, 'main1', turn=7)
    activate_teyo(s, source, 'left')
    assert source.counters['loyalty'] == 2
    refuse(s, bears['p2'], 'p1', pid='p2', turn=8)
    declare(s, bears['p2'], 'p3', pid='p2', turn=8)
    to_phase(s, 'main1', turn=10)
    # The turn belonging to the original ability controller begins: no direction restriction remains.
    declare(s, bears['p1'], 'p3', turn=10)
    roundtrip(s)


@pytest.mark.parametrize('direction,allowed,denied', [('left', 'p2', 'p3'), ('right', 'p3', 'p2')])
def test_teyo_direction_declaration_atomic(cards, direction, allowed, denied):
    s, bears = setup(cards)
    source = cast(s, NAMES[2])
    activate_teyo(s, source, direction)
    refuse(s, bears['p1'], denied)
    declare(s, bears['p1'], allowed)
    assert bears['p1'].attacking.id == allowed
    roundtrip(s)


@pytest.mark.parametrize('change', ['gone', 'control'])
def test_teyo_frozen_controller_expiry_after_source_change(cards, change):
    s, bears = setup(cards)
    source = cast(s, NAMES[2])
    activate_teyo(s, source, 'left')
    if change == 'control':
        act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    else:
        cast(s, 'Lightning Bolt', targets=[source.id])
        assert source.zone == 'p1:graveyard'
    refuse(s, bears['p2'], 'p1', pid='p2', turn=5)
    declare(s, bears['p2'], 'p3', pid='p2', turn=5)
    declare(s, bears['p1'], 'p3', turn=7)
    roundtrip(s)


def test_pending_direction_genuine_cold_reload(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s, bears = setup(cards)
    source = cast(s, NAMES[2])
    wait_priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, targets=[], sources=[])
    settle(s)
    assert s.state.rules.decision is not None
    saved = tmp_path / 'teyo66.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_combat_teyo66 import choose, refuse, declare
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
bear=s.state.cards[sys.argv[3]]
choose(s,'right')
refuse(s,bear,'p2')
declare(s,bear,'p3')
assert bear.attacking.id=='p3'
roundtrip(s)
"""
    backend = Path(app.__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), bears['p1'].id],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_teyo_two_players_both_directions_same_opponent(cards):
    s, bears = setup(cards)
    source = cast(s, NAMES[2])
    activate_teyo(s, source, 'right')
    act(s, 'p3', type='concede')
    declare(s, bears['p1'], 'p2')
    assert bears['p1'].attacking.id == 'p2'


def test_teyo_allows_nearest_planeswalker_but_not_other_planeswalker(cards):
    s, bears = setup(cards)
    source = cast(s, NAMES[2])
    to_phase(s, 'main1', turn=5)
    near = cast(s, NAMES[2], pid='p2')
    to_phase(s, 'main1', turn=6)
    far = cast(s, NAMES[2], pid='p3')
    to_phase(s, 'main1', turn=7)
    activate_teyo(s, source, 'left')
    refuse(s, bears['p1'], far.id, turn=7)
    declare(s, bears['p1'], near.id, turn=7)
    assert bears['p1'].attacking.id == near.id


def test_teyo_declaration_restriction_does_not_restrict_entering_attacking(cards):
    s, _ = setup(cards)
    source = cast(s, NAMES[2])
    adeline = cast(s, 'Adeline, Resplendent Cathar')
    to_phase(s, 'main1', turn=7)
    activate_teyo(s, source, 'left')
    declare(s, adeline, 'p2', turn=7)
    settle(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.attacking is not None]
    assert {c.attacking.id for c in tokens} == {'p2', 'p3'}
    roundtrip(s)


def test_teyo_printed_permission_excludes_battle_even_nearest_protector(cards):
    s, bears = setup(cards)
    source = cast(s, NAMES[2])
    activate_teyo(s, source, 'left')
    siege = put(s, 'Invasion of Mercadia // Kyren Flamewright', 'battlefield', 'p3')
    act(s, 'p3', type='counter', card_ids=[siege.id], kind='defense', delta=4)
    for _ in range(6):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    choose(s, 'p2')
    assert s.state.rules.protectors[s.state.rules.object_id(siege.id)] == 'p2'
    refuse(s, bears['p1'], siege.id)
    declare(s, bears['p1'], 'p2')
