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
    names = [c['name'] for c in DATA] + ['Grizzly Bears', 'Sol Ring', 'Serra Angel']
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


@pytest.mark.parametrize('name', NAMES)
def test_complete_canonicals(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', NAMES[:2])
@pytest.mark.parametrize('direction,allowed,denied', [('left', 'p2', 'p3'), ('right', 'p3', 'p2')])
def test_native_choice_and_own_attack_direction(cards, name, direction, allowed, denied):
    s, bears = setup(cards)
    cast(s, name, direction=direction)
    refuse(s, bears['p1'], denied)
    declare(s, bears['p1'], allowed)
    assert bears['p1'].attacking.id == allowed
    roundtrip(s)


def test_restriction_applies_to_opponents_and_survives_source_control_change(cards):
    s, bears = setup(cards)
    source = cast(s, NAMES[0], direction='left')
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p3')
    refuse(s, bears['p2'], 'p1', pid='p2', turn=5)
    declare(s, bears['p2'], 'p3', pid='p2', turn=5)
    roundtrip(s)


def test_contradictory_barriers_forbid_all_attacks_until_seat_leaves(cards):
    s, bears = setup(cards)
    cast(s, NAMES[0], direction='left')
    cast(s, NAMES[1], direction='right')
    refuse(s, bears['p1'], 'p2')
    refuse(s, bears['p1'], 'p3')
    act(s, 'p3', type='concede')
    declare(s, bears['p1'], 'p2')
    roundtrip(s)


def test_mystic_own_upkeep_rechooses_and_does_not_rechoose_opponents_upkeep(cards):
    s, bears = setup(cards)
    source = cast(s, NAMES[1], direction='left')
    to_phase(s, 'main1', turn=5)
    assert s.state.rules.decision is None and source.choices['Chosen direction'] == 'left'
    to_phase(s, 'upkeep', turn=7)
    settle(s)
    choose(s, 'right')
    assert source.choices['Chosen direction'] == 'right'
    refuse(s, bears['p1'], 'p2', turn=7)
    declare(s, bears['p1'], 'p3', turn=7)
    roundtrip(s)


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
