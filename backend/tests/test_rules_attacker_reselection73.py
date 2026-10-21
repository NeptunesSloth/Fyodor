"""Native paid flash entry changes current destinations without declaring a new attack."""
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
from tests.test_rules_wave30p_combat import attack

NAMES = ['Portal Mage', 'Misleading Signpost', 'Windshaper Planetar', 'Portal Manipulator']
DATA = json.loads((Path(__file__).parent / 'fixtures/attacker_reselection73_cards.json').read_text())


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


def choose(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    settle(s)


def setup(cards, attacker_name='Grizzly Bears'):
    names = [c['name'] for c in DATA]
    s = table(cards, names, names, names)
    a = put(s, attacker_name, 'battlefield')
    b = put(s, 'Llanowar Elves', 'battlefield')
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    to_phase(s, 'declare_attackers', turn=7)
    attack(s, (a, 'p2'), (b, 'p2'))
    settle(s)
    return s, a, b


def cast(s, name):
    wait_priority(s, 'p1')
    source = put(s, name, 'hand')
    mana(s, C=4, U=2, W=2)
    act(s, 'p1', type='cast_spell', card_id=source.id, sources=[])
    settle(s)
    return source


@pytest.mark.parametrize('name', NAMES)
def test_canonical_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


@pytest.mark.parametrize('name', NAMES[:2])
def test_native_targeted_reselection_and_original_attack_history(cards, name):
    s, a, b = setup(cards)
    keys = ('attackers', 'attack_counts', 'declared', 'attacked_who')
    before = {key: s.state.rules.turn_log.model_dump(mode='json')[key] for key in keys}
    cast(s, name)
    choose(s, [a.id])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'attacker_reselect73'
    assert 'p1' not in {o.id for o in d.options}
    choose(s, ['p3'])
    assert a.attacking.id == 'p3' and b.attacking.id == 'p2'
    assert {key: s.state.rules.turn_log.model_dump(mode='json')[key] for key in keys} == before
    roundtrip(s)


def test_native_each_attacker_independent_optional_choice(cards):
    s, a, b = setup(cards)
    cast(s, 'Windshaper Planetar')
    choose(s, ['p3'])
    choose(s, ['decline'])
    assert a.attacking.id == 'p3' and b.attacking.id == 'p2'
    roundtrip(s)


def test_native_forced_player_and_attacker_groups(cards):
    s, a, b = setup(cards)
    cast(s, 'Portal Manipulator')
    choose(s, ['p3'])
    choose(s, [a.id, b.id])
    assert a.attacking.id == b.attacking.id == 'p3'
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('name', NAMES)
def test_entry_outside_declare_attackers_has_no_trigger(cards, name):
    s, a, b = setup(cards)
    to_phase(s, 'main2', turn=7)
    cast(s, name)
    assert s.state.rules.decision is None
    assert not any(e.name == name for e in s.state.rules.stack.values())


@pytest.mark.parametrize('name', NAMES[:2])
def test_own_planeswalker_excluded_enemy_walker_selectable(cards, name):
    s, a, _ = setup(cards)
    own = put(s, 'Jace Beleren', 'battlefield')
    enemy = put(s, 'Jace Beleren', 'battlefield', 'p3')
    for walker in [own, enemy]:
        act(s, walker.controller, type='set_counter', card_id=walker.id, kind='loyalty', value=3)
    cast(s, name)
    choose(s, [a.id])
    d = s.state.rules.decision
    assert d is not None
    options = {o.id for o in d.options}
    assert own.id not in options and enemy.id in options
    choose(s, [enemy.id])
    assert a.attacking.kind == 'card' and a.attacking.id == enemy.id


@pytest.mark.parametrize('name', NAMES[:2])
def test_reselection_ignores_propaganda_attack_payment(cards, name):
    s, a, _ = setup(cards)
    put(s, 'Propaganda', 'battlefield', 'p3')
    cast(s, name)
    choose(s, [a.id])
    choose(s, ['p3'])
    assert a.attacking.id == 'p3' and s.state.rules.decision is None


@pytest.mark.parametrize('name', NAMES)
def test_true_cold_continuation_without_test_adapters(cards, tmp_path, name):
    import subprocess
    import sys

    import app

    s, a, b = setup(cards)
    cast(s, name)
    if name in NAMES[:2]:
        choose(s, [a.id])
    elif name == 'Portal Manipulator':
        choose(s, ['p3'])
    saved = tmp_path / 'reselection.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
mode,a,b=sys.argv[3:]
answers=([a,b],) if mode=='Portal Manipulator' else (['p3'],['decline']) if mode=='Windshaper Planetar' else (['p3'],)
for ids in answers:
 d=s.state.rules.decision
 assert d is not None
 act(s,d.player,type='choose',decision_id=d.id,option_ids=ids)
 settle(s)
assert s.state.cards[a].attacking.id=='p3'
assert s.state.cards[b].attacking.id==('p3' if mode=='Portal Manipulator' else 'p2')
assert s.state.rules.decision is None
roundtrip(s)
'''
    p = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), name, a.id, b.id],
                       capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert p.returncode == 0, p.stdout + p.stderr


def test_reselection_does_not_emit_actual_captain_attack_trigger(cards):
    from tests.test_rules_wave6c_tokens_pumps import chars

    s, a, b = setup(cards, 'Honored Crop-Captain')
    assert chars(s, b).pt == (2, 1)
    cast(s, 'Portal Mage')
    choose(s, [a.id])
    choose(s, ['p3'])
    assert a.attacking.id == 'p3'
    assert chars(s, b).pt == (2, 1)
    assert s.state.rules.decision is None and not s.state.rules.stack
    roundtrip(s)


def test_forced_relative_target_group_excludes_chosen_players_creatures(cards):
    s, a, b = setup(cards)
    cast(s, 'Portal Manipulator')
    choose(s, ['p1'])
    d = s.state.rules.decision
    if d is not None:
        assert a.id not in {o.id for o in d.options} and b.id not in {o.id for o in d.options}
        choose(s, [])
    assert a.attacking.id == b.attacking.id == 'p2'
    roundtrip(s)


def test_forced_group_rechecks_target_after_native_control_change(cards):
    s, a, b = setup(cards)
    cast(s, 'Portal Manipulator')
    choose(s, ['p3'])
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[a.id, b.id])
    wait_priority(s, 'p3')
    assert coverage.of_card_data(cards.resolve('Dominate')).level == 'FULL'
    response = put(s, 'Dominate', 'hand', 'p3')
    mana(s, pid='p3', C=3, U=3)
    wait_priority(s, 'p3')
    act(s, 'p3', type='cast_spell', card_id=response.id, targets=[a.id], x_value=2, sources=[])
    settle(s)
    a = s.state.cards[a.id]
    assert a.controller == 'p3' and not a.is_attacking
    assert b.attacking.id == 'p3'
    roundtrip(s)


@pytest.mark.parametrize('invalidated', ['attacker', 'destination'])
def test_cold_oid_invalidation_rejects_successor_objects(cards, tmp_path, invalidated):
    import subprocess
    import sys

    import app

    s, a, _ = setup(cards)
    walker = put(s, 'Jace Beleren', 'battlefield', 'p3') if invalidated == 'destination' else None
    if walker is not None:
        act(s, 'p3', type='set_counter', card_id=walker.id, kind='loyalty', value=3)
    cast(s, 'Portal Mage')
    choose(s, [a.id])
    old = a if invalidated == 'attacker' else walker
    pid = old.controller
    for zone in ['exile', 'battlefield']:
        act(s, pid, type='move', card_ids=[old.id], to={'player': pid, 'zone': zone})
    if walker is not None:
        act(s, 'p3', type='set_counter', card_id=walker.id, kind='loyalty', value=3)
    saved = tmp_path / 'oid.json'
    saved.write_text(s.state.model_dump_json())
    destination = walker.id if walker else 'p3'
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_library_look import settle
from tests.test_rules_designations import roundtrip
r=CardRepository(Path(sys.argv[2]),ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=r)
d=s.state.rules.decision
assert d is not None
act(s,d.player,type='choose',decision_id=d.id,option_ids=[sys.argv[4]])
settle(s)
a=s.state.cards[sys.argv[3]]
assert not a.is_attacking if sys.argv[5]=='attacker' else a.attacking.id=='p2'
assert s.state.rules.decision is None
roundtrip(s)
'''
    p = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), a.id, destination, invalidated],
                       capture_output=True, text=True, timeout=90, cwd=Path(app.__file__).resolve().parents[1])
    assert p.returncode == 0, p.stdout + p.stderr


def test_reselection_invalidates_original_defending_player_target(cards):
    names = [c['name'] for c in DATA]
    s = table(cards, names, names, names)
    binder = put(s, 'Fiend Binder', 'battlefield')
    victim = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    start(s)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    to_phase(s, 'declare_attackers', turn=7)
    attack(s, (binder, 'p2'))
    settle(s)
    d = s.state.rules.decision
    assert d is not None
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[victim.id])
    cast(s, 'Portal Mage')
    choose(s, [binder.id])
    choose(s, ['p3'])
    assert binder.attacking.id == 'p3' and not victim.tapped
    assert not s.state.rules.stack and s.state.rules.decision is None
    roundtrip(s)


def test_actual_copied_forced_ability_rebinds_new_player_targets(cards):
    s, a, b = setup(cards)
    source = cast(s, 'Portal Manipulator')
    choose(s, ['p3'])
    d = s.state.rules.decision
    assert d is not None
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[a.id, b.id])
    original = next(sid for sid, entry in s.state.rules.stack.items() if entry.source_card == source.id)
    wait_priority(s, 'p2')
    favor = put(s, 'Return the Favor', 'hand', 'p2')
    mana(s, pid='p2', C=1, R=2)
    wait_priority(s, 'p2')
    act(s, 'p2', type='cast_spell', card_id=favor.id, modes=[0], targets=[original], sources=[])
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'copy_target'
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['p1'])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'copy_target' and d.resume['picks'] == []
    act(s, 'p2', type='choose', decision_id=d.id, option_ids=['p2'])
    for _ in range(3):
        d = s.state.rules.decision
        if d is None:
            break
        assert d.resume['step'] == 'copy_target'
        assert 'keep' in {o.id for o in d.options}
        act(s, 'p2', type='choose', decision_id=d.id, option_ids=['keep'])
    assert s.state.rules.decision is None
    copy = next(e for sid, e in s.state.rules.stack.items() if e.source_card == source.id and sid != original)
    assert copy.controller == 'p2' and copy.groups[0][0].id == 'p2'
    wait_priority(s, 'p3')
    stifle = put(s, 'Stifle', 'hand', 'p3')
    mana(s, pid='p3', U=1)
    wait_priority(s, 'p3')
    act(s, 'p3', type='cast_spell', card_id=stifle.id, targets=[original], sources=[])
    settle(s)
    assert a.attacking.id == b.attacking.id == 'p2'
    assert original not in s.state.rules.stack
    roundtrip(s)
