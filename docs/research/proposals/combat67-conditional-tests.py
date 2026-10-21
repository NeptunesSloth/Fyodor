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

DATA = json.loads((Path(__file__).parent / 'fixtures/combat_conditional_requirements67_cards.json').read_text())
NAMES = ["War's Toll", "Viashino Bey"]


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
    names = NAMES + ['Grizzly Bears', 'Sol Ring', 'Serra Angel', 'Silent Arbiter', 'Shiny Impetus']
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


def test_wars_toll_all_or_none_opponents_only(cards):
    s, bears = setup(cards)
    cast(s, NAMES[0])
    # Its controller may attack with only one creature.
    declare(s, bears['p1'][0], 'p2')
    to_phase(s, 'declare_attackers', turn=5)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bears['p2'][0].id, 'target': 'p1'}])
    assert s.state.model_dump_json() == before
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p1'} for c in bears['p2']])
    assert all(c.attacking is not None for c in bears['p2'])
    roundtrip(s)


def test_viashino_does_not_force_own_condition_but_all_follow_when_it_attacks(cards):
    s, bears = setup(cards)
    source = cast(s, NAMES[1])
    # Other creatures may attack without forcing Bey to attack.
    declare(s, bears['p1'][0], 'p2')
    to_phase(s, 'declare_attackers', turn=7)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    assert s.state.model_dump_json() == before
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p2'} for c in [source, *bears['p1']]])
    roundtrip(s)


def test_wars_toll_one_attacker_cap_has_legal_initiator(cards):
    s, bears = setup(cards)
    cast(s, NAMES[0])
    cast(s, 'Silent Arbiter')
    to_phase(s, 'declare_attackers', turn=5)
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bears['p2'][0].id, 'target': 'p1'}])
    assert bears['p2'][0].attacking.id == 'p1'
    roundtrip(s)


def test_wars_toll_native_opponent_land_mana_taps_all_only_that_player(cards):
    s, _ = setup(cards)
    source = cast(s, NAMES[0])
    first = put(s, 'Forest', 'battlefield', 'p2')
    other = put(s, 'Sol Ring', 'battlefield', 'p2')
    own = put(s, 'Forest', 'battlefield', 'p1')
    # A second distinct basic land is already in the table's twenty-Forest pile.
    land = next(c for c in s.state.cards.values() if c.name == 'Forest' and c.owner == 'p2' and c.id != first.id)
    act(s, 'p2', type='move', card_ids=[land.id], to={'player': 'p2', 'zone': 'battlefield'})
    wait_priority(s, 'p2')
    act(s, 'p2', type='activate_ability', card_id=first.id, ability=0)
    settle(s)
    assert first.tapped and land.tapped and not own.tapped and not other.tapped
    assert source.zone == 'p1:battlefield'
    roundtrip(s)


def test_wars_toll_no_attack_does_not_force_condition(cards):
    s, _ = setup(cards)
    cast(s, NAMES[0])
    to_phase(s, 'declare_attackers', turn=5)
    act(s, 'p2', type='declare_attackers', attackers=[])
    roundtrip(s)


def conditional_counts(s, target):
    from app.rules import attack_requirements
    return {r: n for r, n in attack_requirements.counts(Plan(s.state, 'p1', s.cards, None).ch(target)).items()
            if r.startswith('conditional_attack67:')}


def test_viashino_source_interpolates_physical_card_id(cards):
    s, bears = setup(cards)
    source = cast(s, NAMES[1])
    assert conditional_counts(s, bears['p1'][0]) == {'conditional_attack67:' + source.id + ':source': 1}
    assert source.id != s.state.rules.object_id(source.id)


def test_two_sources_count_independently_and_follow_current_controller(cards):
    s, bears = setup(cards)
    first = cast(s, NAMES[0])
    to_phase(s, 'main1', turn=6)
    second = cast(s, NAMES[0], pid='p3')
    counts = conditional_counts(s, bears['p2'][0])
    assert counts == {'conditional_attack67:' + c.id + ':any': 1 for c in [first, second]}
    act(s, 'p3', type='set_controller', card_ids=[second.id], player='p2')
    assert conditional_counts(s, bears['p2'][0]) == {'conditional_attack67:' + first.id + ':any': 1}
    assert conditional_counts(s, bears['p1'][0]) == {'conditional_attack67:' + second.id + ':any': 1}
    to_phase(s, 'declare_attackers', turn=8)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bears['p2'][0].id, 'target': 'p1'}])
    assert s.state.model_dump_json() == before
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p1'} for c in bears['p2']])
    roundtrip(s)


def test_external_goad_forces_initiation_then_conditional_others_attack(cards):
    s, bears = setup(cards)
    cast(s, NAMES[0])
    cast(s, 'Shiny Impetus', targets=[bears['p2'][0].id])
    to_phase(s, 'declare_attackers', turn=5)
    before = s.state.model_dump_json()
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_attackers', attackers=[])
    assert s.state.model_dump_json() == before
    with pytest.raises(ActionError):
        act(s, 'p2', type='declare_attackers', attackers=[{'card_id': bears['p2'][0].id, 'target': 'p3'}])
    assert s.state.model_dump_json() == before
    act(s, 'p2', type='declare_attackers', attackers=[{'card_id': c.id, 'target': 'p3'} for c in bears['p2']])
    roundtrip(s)


def test_viashino_conditional_requirement_genuine_cold_reload(cards, tmp_path):
    import os
    import subprocess
    import sys

    import app

    s, bears = setup(cards)
    source = cast(s, NAMES[1])
    to_phase(s, 'main1', turn=7)
    saved = tmp_path / 'teyo66.json'
    saved.write_text(s.state.model_dump_json())
    code = r"""
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_combat_conditional_requirements67 import refuse, to_phase
from tests.test_rules_designations import roundtrip
from tests.game_helpers import act
repo=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
source=s.state.cards[sys.argv[3]]
refuse(s,source,'p2',turn=7)
to_phase(s,'declare_attackers',turn=7)
ids=[source.id,*sys.argv[4:]]
act(s,'p1',type='declare_attackers',attackers=[{'card_id':x,'target':'p2'} for x in ids])
assert source.attacking.id=='p2'
roundtrip(s)
"""
    backend = Path(app.__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id, *[x.id for x in bears['p1']]],
                            cwd=backend, env={**os.environ, 'PYTHONPATH': str(backend)},
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
