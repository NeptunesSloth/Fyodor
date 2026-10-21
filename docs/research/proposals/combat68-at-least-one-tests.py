"""Conditional declaration requirements preserve origin, legality and native optimization."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave30m_durations import to_phase

DATA = json.loads((Path(__file__).parent / 'fixtures/combat_at_least_one68_cards.json').read_text())
NAMES = ['Seeker of Slaanesh', 'Trove of Temptation']


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
    names = NAMES + ['Grizzly Bears', 'Sol Ring', 'Serra Angel', 'Silent Arbiter', 'Shiny Impetus', 'Ghostly Prison', 'Teyo, Geometric Tactician', 'Invasion of Mercadia // Kyren Flamewright']
    s = table(cards, names, names, names)
    bears = {p: [put(s, n, 'battlefield', p) for n in ['Grizzly Bears', 'Serra Angel']] for p in ['p1', 'p2', 'p3']}
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
def test_canonical_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_seeker_native_haste_and_opponent_only_requirement(cards):
    s, bears = setup(cards)
    source = cast(s, NAMES[0])
    declare(s, source, 'p2')
    assert source.attacking.id == 'p2'
    to_phase(s, 'declare_attackers', turn=5)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_attackers', attackers=[])
    assert s.state.model_dump_json() == before
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bears['p2'][1].id, 'target': 'p3'}])
    assert bears['p2'][0].attacking is None
    roundtrip(s)


def test_trove_native_treasure_and_controller_destination(cards):
    s, bears = setup(cards)
    cast(s, NAMES[1])
    to_phase(s, 'declare_attackers', turn=5)
    assert any(c.is_token and c.name == 'Treasure' and c.zone == 'p1:battlefield' for c in s.state.cards.values())
    before = s.state.model_dump_json()
    for attackers in [[], [{'card_id': bears['p2'][0].id, 'target': 'p3'}]]:
        with pytest.raises(ActionError):
            act(s, 'p2', type='declare_attackers', attackers=attackers)
        assert s.state.model_dump_json() == before
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bears['p2'][0].id, 'target': 'p1'}])
    assert bears['p2'][1].attacking is None
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_no_eligible_creatures_does_not_force_attack(cards, name):
    s, bears = setup(cards)
    cast(s, name)
    to_phase(s, 'main1', turn=5)
    act(s, 'p2', type='tap', card_ids=[c.id for c in bears['p2']], tapped=True)
    to_phase(s, 'main2', turn=5)
    assert all(c.attacking is None for c in bears['p2'])
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_requirement_does_not_force_unpaid_attack_cost(cards, name):
    s, bears = setup(cards)
    cast(s, name)
    cast(s, 'Ghostly Prison')
    to_phase(s, 'declare_attackers', turn=5)
    before = s.state.model_dump_json()
    if name == NAMES[0]:
        with pytest.raises(ActionError):
            act(s, 'p2', type='declare_attackers', attackers=[])
        assert s.state.model_dump_json() == before
        act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bears['p2'][0].id, 'target': 'p3'}])
    else:
        act(s, 'p2', type='declare_attackers', attackers=[])
    roundtrip(s)


@pytest.mark.parametrize('goad,destination', [(False, 'p1'), (True, 'p1'), (True, 'p3')])
def test_trove_multiplicity_competes_under_one_attacker_cap(cards, goad, destination):
    s, bears = setup(cards)
    own_walker = cast(s, 'Teyo, Geometric Tactician')
    other_walker = put(s, 'Teyo, Geometric Tactician', 'battlefield', 'p3')
    act(s, 'p3', type='counter', card_ids=[other_walker.id], kind='loyalty', delta=3)
    first = cast(s, NAMES[1])
    second = put(s, NAMES[1], 'battlefield', 'p3')
    act(s, 'p3', type='set_controller', card_ids=[second.id], player='p1')
    third = put(s, NAMES[1], 'battlefield', 'p2')
    act(s, 'p2', type='set_controller', card_ids=[third.id], player='p3')
    cast(s, 'Silent Arbiter')
    if goad:
        cast(s, 'Shiny Impetus', targets=[bears['p2'][0].id])
    from app.rules import combat_at_least_one68
    from app.rules.plan import Plan

    groups = combat_at_least_one68.groups(Plan(s.state, 'p1', s.cards, None), {c.id for c in bears['p2']})
    assert {places: n for n, places in groups} == {frozenset({'p1', own_walker.id}): 2, frozenset({'p3', other_walker.id}): 1}
    to_phase(s, 'declare_attackers', turn=4)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[])
    assert s.state.model_dump_json() == before
    declare(s, bears['p1'][0], 'p3')
    to_phase(s, 'declare_attackers', turn=5)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bears['p2'][1 if goad else 0].id, 'target': 'p1' if goad else 'p3'}])
    assert s.state.model_dump_json() == before
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bears['p2'][0].id, 'target': destination}])
    assert first.zone == second.zone == 'p1:battlefield'
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_planeswalker_and_battle_destinations_match_printed_requirement(cards, name):
    s, bears = setup(cards)
    walker = cast(s, 'Teyo, Geometric Tactician')
    cast(s, name)
    siege = put(s, 'Invasion of Mercadia // Kyren Flamewright', 'battlefield', 'p3')
    act(s, 'p3', type='counter', card_ids=[siege.id], kind='defense', delta=4)
    for _ in range(6):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    choose(s, 'p1')
    to_phase(s, 'declare_attackers', turn=5)
    before = s.state.model_dump_json()
    if name == NAMES[1]:
        with pytest.raises(ActionError):
            act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bears['p2'][0].id, 'target': siege.id}])
        assert s.state.model_dump_json() == before
        destination = walker.id
    else:
        destination = siege.id
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bears['p2'][0].id, 'target': destination}])
    assert bears['p2'][0].attacking.id == destination
    roundtrip(s)


def test_trove_requirement_genuine_cold_reload(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s, bears = setup(cards)
    cast(s, NAMES[1])
    to_phase(s, 'declare_attackers', turn=5)
    saved = tmp_path / 'one68.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_combat_at_least_one68 import refuse, declare
from tests.test_rules_designations import roundtrip
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
bear=s.state.cards[sys.argv[3]]
refuse(s,bear,'p3',pid='p2',turn=5)
declare(s,bear,'p1',pid='p2',turn=5)
assert bear.attacking.id=='p1'
roundtrip(s)
"""
    backend = Path(app.__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), bears['p2'][0].id],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=180, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_two_distinct_trove_groups_need_two_destinations_without_cap(cards):
    s, bears = setup(cards)
    cast(s, NAMES[1])
    put(s, NAMES[1], 'battlefield', 'p3')
    declare(s, bears['p1'][0], 'p3')
    to_phase(s, 'declare_attackers', turn=5)
    before = s.state.model_dump_json()
    for attackers in [[], [{'card_id': bears['p2'][0].id, 'target': 'p1'}],
                      [{'card_id': c.id, 'target': 'p1'} for c in bears['p2']]]:
        with pytest.raises(ActionError):
            act(s, 'p2', type='declare_attackers', attackers=attackers)
        assert s.state.model_dump_json() == before
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': c.id, 'target': target}
        for c, target in zip(bears['p2'], ['p1', 'p3'], strict=True)])
    roundtrip(s)
