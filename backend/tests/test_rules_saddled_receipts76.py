"""Native saddle payment, designation, contributors and frozen counter cohorts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage, sba
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_declaration_requirements33 import start
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave6c_tokens_pumps import chars
from tests.test_rules_wave30m_durations import to_phase
from tests.test_rules_wave30p_combat import attack

NAMES = ['Guidelight Matrix', 'Alacrian Armory', 'Rambling Possum', 'Bounding Felidar']
DATA = json.loads((Path(__file__).parent / 'fixtures/saddled_receipts76_cards.json').read_text())


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



@pytest.mark.parametrize('name', NAMES)
def test_whole_card_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def setup_mount(cards, name):
    s = table(cards, [c['name'] for c in DATA] + ['Grizzly Bears', 'Llanowar Elves'], [], [])
    mount = put(s, name, 'battlefield')
    bear = put(s, 'Grizzly Bears', 'battlefield')
    elf = put(s, 'Llanowar Elves', 'battlefield')
    start(s)
    return s, mount, bear, elf


def saddle(s, mount, helpers):
    from tests.test_rules_wave23d_triggers import saddle_index
    act(s, 'p1', type='activate_ability', card_id=mount.id, ability=saddle_index(s, mount.name), crew=[c.id for c in helpers])
    settle(s)


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def test_felidar_actual_saddle_cost_and_other_cohort(cards):
    s, mount, bear, elf = setup_mount(cards, 'Bounding Felidar')
    saddle(s, mount, [bear])
    assert bear.tapped
    before = s.state.players['p1'].life
    to_phase(s, 'declare_attackers')
    attack(s, (mount, 'p2'))
    settle(s)
    assert s.state.players['p1'].life == before + 2
    assert bear.counters.get('+1/+1', 0) == 1 and elf.counters.get('+1/+1', 0) == 1
    assert mount.counters.get('+1/+1', 0) == 0


def test_possum_only_paid_contributors_offered(cards):
    s, mount, bear, elf = setup_mount(cards, 'Rambling Possum')
    saddle(s, mount, [elf])
    to_phase(s, 'declare_attackers')
    attack(s, (mount, 'p2'))
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    assert {o.card_id for o in d.options} == {elf.id}
    choose(s, [elf.id])
    assert elf.zone == 'p1:hand' and bear.zone == 'p1:battlefield'
    assert (sba.power(mount, chars(s, mount)), sba.toughness(mount, chars(s, mount))) == (4, 5)


def test_matrix_native_paid_activation_designates_without_contributors(cards):
    from app.rules import crew_saddle
    from app.rules.plan import Plan
    s, mount, bear, elf = setup_mount(cards, 'Rambling Possum')
    matrix = put(s, 'Guidelight Matrix', 'battlefield')
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=matrix.id, ability=1, targets=[mount.id], sources=[])
    settle(s)
    plan = Plan(s.state, 'p1', s.cards, None)
    assert crew_saddle.is_saddled(plan, mount) and matrix.tapped
    assert not bear.tapped and not elf.tapped
    assert not any(f.kind == 'saddle' for f in s.state.rules.turn_log.facts)
    to_phase(s, 'declare_attackers')
    attack(s, (mount, 'p2'))
    settle(s)
    assert s.state.rules.decision is None
    assert (sba.power(mount, chars(s, mount)), sba.toughness(mount, chars(s, mount))) == (4, 5)


def test_armory_combat_target_saddles_without_cost_and_grants_static(cards):
    from app.rules import crew_saddle
    from app.rules.plan import Plan
    s, mount, bear, elf = setup_mount(cards, 'Rambling Possum')
    put(s, 'Alacrian Armory', 'battlefield')
    to_phase(s, 'begin_combat')
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    choose(s, [mount.id])
    plan = Plan(s.state, 'p1', s.cards, None)
    assert crew_saddle.is_saddled(plan, mount)
    assert sba.toughness(bear, chars(s, bear)) == 3 and 'vigilance' in chars(s, bear).keywords
    assert not any(f.kind == 'saddle' for f in s.state.rules.turn_log.facts)


@pytest.mark.parametrize('name', ['Rambling Possum', 'Bounding Felidar'])
def test_unsaddled_attack_does_not_trigger(cards, name):
    s, mount, bear, elf = setup_mount(cards, name)
    before = s.state.players['p1'].life
    to_phase(s, 'declare_attackers')
    attack(s, (mount, 'p2'))
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life == before
    assert not bear.counters and not elf.counters
    assert sba.power(mount, chars(s, mount)) == int(cards.resolve(name)['power'])


def test_possum_optional_empty_choice_keeps_contributor(cards):
    s, mount, bear, elf = setup_mount(cards, 'Rambling Possum')
    saddle(s, mount, [elf])
    to_phase(s, 'declare_attackers')
    attack(s, (mount, 'p2'))
    settle(s)
    choose(s, [])
    assert elf.zone == 'p1:battlefield' and elf.tapped
    assert sba.power(mount, chars(s, mount)) == 4


@pytest.mark.parametrize('name,pool', [('Guidelight Matrix', {'C':2}), ('Alacrian Armory', {'C':3, 'W':1}),
                                      ('Rambling Possum', {'C':2, 'G':1}), ('Bounding Felidar', {'C':5, 'W':1})])
def test_paid_full_source_entry(cards, name, pool):
    from tests.test_rules_bandmate_references import wait_priority
    s = table(cards, NAMES + ['Grizzly Bears'], [], [])
    start(s)
    source = put(s, name, 'hand')
    before = len(s.state.zones['p1:hand'])
    wait_priority(s, 'p1')
    mana(s, **pool)
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=[], sources=[])
    settle(s)
    assert source.zone == 'p1:battlefield'
    if name == 'Guidelight Matrix':
        assert len(s.state.zones['p1:hand']) == before
    else:
        assert len(s.state.zones['p1:hand']) == before - 1


def test_felidar_prevented_counters_still_count_original_other_creatures(cards):
    s, mount, bear, elf = setup_mount(cards, 'Bounding Felidar')
    put(s, 'Solemnity', 'battlefield')
    saddle(s, mount, [bear])
    before = s.state.players['p1'].life
    to_phase(s, 'declare_attackers')
    attack(s, (mount, 'p2'))
    settle(s)
    assert not bear.counters and not elf.counters and not mount.counters
    assert s.state.players['p1'].life == before + 2


@pytest.mark.parametrize('source_name', ['Guidelight Matrix', 'Alacrian Armory'])
def test_native_vehicle_animation_other_printed_branch(cards, source_name):
    s, mount, bear, elf = setup_mount(cards, 'Rambling Possum')
    vehicle = put(s, "Smuggler's Copter", 'battlefield')
    source = put(s, source_name, 'battlefield')
    if source_name == 'Guidelight Matrix':
        mana(s, C=2)
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=2, targets=[vehicle.id], sources=[])
        settle(s)
    else:
        to_phase(s, 'begin_combat')
        settle(s)
        choose(s, [vehicle.id])
    assert {'Artifact', 'Creature'} <= chars(s, vehicle).types
    assert 'Vehicle' in chars(s, vehicle).subtypes
    assert (sba.power(vehicle, chars(s, vehicle)), sba.toughness(vehicle, chars(s, vehicle))) == ((3,3) if source_name == 'Guidelight Matrix' else (3,4))


def test_possum_original_source_destroyed_still_returns_paid_helper(cards):
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s, mount, bear, elf = setup_mount(cards, 'Rambling Possum')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    saddle(s, mount, [elf])
    to_phase(s, 'declare_attackers')
    attack(s, (mount, 'p2'))
    cast(s, 'Lightning Bolt', {'R':1}, [mount.id])
    assert mount.zone == 'p1:graveyard'
    assert {o.card_id for o in s.state.rules.decision.options} == {elf.id}
    choose(s, [elf.id])
    assert elf.zone == 'p1:hand'


def test_felidar_blinked_successor_counts_as_other_creature(cards):
    from app.rules.plan import Plan
    from tests.test_rules_trigger_upkeep_comparison75 import cast
    s, mount, bear, elf = setup_mount(cards, 'Bounding Felidar')
    act(s, 'p1', type='set_prefs', hold_priority=True)
    saddle(s, mount, [bear])
    original = Plan(s.state, 'p1', s.cards, None).oid(mount)
    before = s.state.players['p1'].life
    to_phase(s, 'declare_attackers')
    attack(s, (mount, 'p2'))
    cast(s, 'Flicker of Fate', {'C':1, 'W':1}, [mount.id])
    assert mount.zone == 'p1:battlefield'
    assert Plan(s.state, 'p1', s.cards, None).oid(mount) != original
    assert all(c.counters.get('+1/+1',0) == 1 for c in (mount,bear,elf))
    assert s.state.players['p1'].life == before + 3


@pytest.mark.parametrize('mode', ['Possum', 'Felidar', 'Armory', 'Matrix'])
def test_genuine_cold_pending_native_choice_or_stack(cards, tmp_path, mode):
    import subprocess
    import sys

    import app

    name = 'Bounding Felidar' if mode == 'Felidar' else 'Rambling Possum'
    s, mount, bear, elf = setup_mount(cards, name)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    if mode in {'Possum', 'Felidar'}:
        saddle(s, mount, [bear])
        to_phase(s, 'declare_attackers')
        attack(s, (mount, 'p2'))
        if mode == 'Possum':
            settle(s)
            assert s.state.rules.decision is not None
        else:
            assert s.state.rules.stack
    elif mode == 'Armory':
        put(s, 'Alacrian Armory', 'battlefield')
        to_phase(s, 'begin_combat')
        settle(s)
        assert s.state.rules.decision is not None
    else:
        matrix = put(s, 'Guidelight Matrix', 'battlefield')
        mana(s, C=2)
        act(s, 'p1', type='activate_ability', card_id=matrix.id, ability=1, targets=[mount.id], sources=[])
        assert s.state.rules.stack
    saved = tmp_path/'saddle.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules import crew_saddle
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_library_look import settle
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
mode,mount,bear,elf=sys.argv[3:]
if mode in {'Possum','Armory'}:
 d=s.state.rules.decision
 assert d is not None
 act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear if mode=='Possum' else mount])
settle(s)
if mode=='Possum':assert s.state.cards[bear].zone=='p1:hand'
elif mode=='Felidar':
 assert s.state.players['p1'].life==42
 assert all(s.state.cards[c].counters.get('+1/+1',0)==1 for c in (bear,elf))
else:assert crew_saddle.is_saddled(Plan(s.state,'p1',r,None),s.state.cards[mount])
assert s.state.rules.decision is None
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), mode, mount.id, bear.id, elf.id],
                            capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert result.returncode == 0, result.stdout + result.stderr


def test_armory_dual_mount_vehicle_performs_both_independent_branches(cards):
    from app.rules import crew_saddle
    from app.rules.plan import Plan
    s, mount, bear, elf = setup_mount(cards, 'Rambling Possum')
    vehicle = put(s, "Smuggler's Copter", 'battlefield')
    matrix = put(s, 'Guidelight Matrix', 'battlefield')
    put(s, 'Maskwood Nexus', 'battlefield')
    mana(s, C=2)
    act(s, 'p1', type='activate_ability', card_id=matrix.id, ability=2, targets=[vehicle.id], sources=[])
    settle(s)
    assert {'Mount', 'Vehicle'} <= chars(s, vehicle).subtypes
    put(s, 'Alacrian Armory', 'battlefield')
    to_phase(s, 'begin_combat')
    settle(s)
    choose(s, [vehicle.id])
    assert {'Artifact', 'Creature'} <= chars(s, vehicle).types
    assert crew_saddle.is_saddled(Plan(s.state, 'p1', s.cards, None), vehicle)
