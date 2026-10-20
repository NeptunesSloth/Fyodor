"""Production native Captain Rex Nebula whole-card proofs."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import random_vehicle_crash45 as leaf
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_random_consequences import answer
from tests.test_rules_random_native_outcomes42 import DATA
from tests.test_rules_wave30m_durations import stops, three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

NAME = 'Captain Rex Nebula'
ROWS = json.loads((Path(__file__).parent / 'fixtures/random_vehicle_crash45_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, row in enumerate([*DATA, *ROWS]):
        base[row['name']] = card(row['name'], set_code='vc45', number=str(i), **{k: v for k, v in row.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [r['name'] for r in [*DATA, *ROWS]] + ['Grizzly Bears', 'Lightning Bolt', 'Sol Ring', 'Forest']
    s = three(cards, names, names, names)
    hold(s)
    stops(s, 'begin_combat', 'declare_attackers', 'declare_blockers')
    rex = put(s, NAME, 'battlefield')
    return s, rex


def derived(s, source):
    return Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[source.id])


def animate(s, target):
    to_phase(s, 'begin_combat', turn=1)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'trigger_target'
    answer(s, [target.id])


def crew(s, source, pilot):
    index = next((a.index for a in derived(s, source).abilities if a.text.lower().rstrip('.') == 'crew 2'), None)
    assert index is not None, [(a.index, a.text[:65], a.kind) for a in derived(s, source).abilities]
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=index, crew=[pilot.id], sources=[])
    settle(s)


def test_primary_replaces_types_subtypes_preserves_legendary_and_old_ability_then_native_crew(cards):
    s, rex = setup(cards)
    pilot = put(s, 'Grizzly Bears', 'battlefield')
    original = derived(s, rex)
    animate(s, rex)
    ch = derived(s, rex)
    assert ch.types == {'Artifact'} and ch.subtypes == {'Vehicle'}
    assert 'Legendary' in ch.supertypes
    assert any(a.text == leaf._PRIMARY for a in ch.abilities)
    assert ch.mana_value == original.mana_value == 3
    crew(s, rex, pilot)
    ch = derived(s, rex)
    assert ch.types == {'Artifact', 'Creature'} and ch.subtypes == {'Vehicle'}
    assert ch.pt == (3, 3)
    assert s.state.cards[pilot.id].tapped
    roundtrip(s)


def test_actual_combat_crash_announces_target_before_roll_sacrifices_then_deals_result(cards, monkeypatch):
    s, rex = setup(cards)
    pilot = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    rolled = []
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: rolled.append(3) or 3)
    animate(s, rex)
    crew(s, rex, pilot)
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': rex.id, 'target': 'p2'}])
    to_phase(s, 'combat_damage', turn=1)
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'trigger_target'
    assert not rolled
    answer(s, ['p3'])
    assert rolled == [3]
    assert s.state.players['p2'].life == 37 and s.state.players['p3'].life == 37
    assert s.state.cards[rex.id].zone == 'p1:graveyard'
    assert not s.state.zones.get('stack')
    roundtrip(s)


def ready(s, rex):
    pilot = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    animate(s, rex)
    crew(s, rex, pilot)


def combat_target(s, rex):
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': rex.id, 'target': 'p2'}])
    to_phase(s, 'combat_damage', turn=1)
    settle(s)
    assert s.state.rules.decision.resume['step'] == 'trigger_target'


@pytest.mark.parametrize('result', [1, 2, 3, 4, 5, 6])
def test_each_natural_crash_result_checks_equality_and_preserves_failed_match(cards, monkeypatch, result):
    s, rex = setup(cards)
    ready(s, rex)
    rolled = []
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: rolled.append(result) or result)
    combat_target(s, rex)
    assert not rolled
    answer(s, ['p3'])
    assert rolled == [result]
    assert s.state.cards[rex.id].zone == ('p1:graveyard' if result == 3 else 'p1:battlefield')
    assert s.state.players['p3'].life == (37 if result == 3 else 40)
    roundtrip(s)


def test_animation_ends_at_cleanup_including_granted_crew_crash_and_frozen_base_stats(cards):
    s, rex = setup(cards)
    ready(s, rex)
    assert derived(s, rex).pt == (3, 3)
    to_phase(s, 'main1', turn=2)
    ch = derived(s, rex)
    assert ch.types == {'Creature'} and ch.subtypes == {'Human', 'Pilot', 'Employee'}
    assert ch.pt == (2, 2)
    assert len(ch.abilities) == 1 and ch.abilities[0].text == leaf._PRIMARY
    roundtrip(s)


def test_primary_target_options_exclude_lands_and_other_controllers_permanents(cards):
    from app.game.errors import ActionError
    s, rex = setup(cards)
    own_land = put(s, 'Forest', 'battlefield')
    foreign = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'begin_combat', turn=1)
    settle(s)
    d = s.state.rules.decision
    assert own_land.id not in {o.id for o in d.options} and foreign.id not in {o.id for o in d.options}
    for target in [own_land.id, foreign.id]:
        with pytest.raises(ActionError):
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target])
    answer(s, [rex.id])
    assert derived(s, rex).types == {'Artifact'}
    roundtrip(s)


def test_opponent_fog_prevents_entire_damage_instance_and_never_rolls(cards, monkeypatch):
    from tests.test_rules_source_quality_protection import spell
    s, rex = setup(cards)
    ready(s, rex)
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda *args: (_ for _ in ()).throw(AssertionError('prevented damage rolled')))
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': rex.id, 'target': 'p2'}])
    spell(s, 'Fog', {'G': 1}, player='p2')
    to_phase(s, 'combat_damage', turn=1)
    settle(s)
    assert s.state.rules.decision is None and s.state.players['p2'].life == 40
    assert s.state.cards[rex.id].zone == 'p1:battlefield'
    assert not s.state.rules.turn_log.rolled.get('p1', 0)
    roundtrip(s)


def test_all_targets_illegal_counters_crash_before_roll_or_sacrifice(cards, monkeypatch):
    from tests.test_rules_effects import token
    from tests.test_rules_source_quality_protection import spell
    s, rex = setup(cards)
    target = token(s, 'p2', 'Crash target', pt='4/4')
    ready(s, rex)
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda *args: (_ for _ in ()).throw(AssertionError('illegal trigger rolled')))
    combat_target(s, rex)
    d = s.state.rules.decision
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[target.id])
    spell(s, 'Flicker of Fate', {'C': 1, 'W': 1}, target=[target.id], player='p2')
    assert s.state.cards[rex.id].zone == 'p1:battlefield'
    assert not s.state.rules.turn_log.rolled.get('p1', 0)
    assert not s.state.zones.get('stack')
    roundtrip(s)


@pytest.mark.parametrize('copies,final', [(1, 0), (2, -1)])
def test_actual_modified_zero_matches_zero_mv_but_negative_result_does_not(cards, monkeypatch, copies, final):
    from tests.test_rules_source_quality_protection import spell
    s, rex = setup(cards)
    ballista = spell(s, 'Walking Ballista', {'C': 4}, x_value=2)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    if copies == 2:
        second = put(s, 'Night Shift of the Living Dead', 'battlefield', 'p2')
        act(s, 'p2', type='set_controller', card_ids=[second.id], player='p1')
    animate(s, ballista)
    assert derived(s, ballista).types == {'Artifact'} and derived(s, ballista).mana_value == 0
    rolled = []
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: rolled.append(1) or 1)
    index = next(a.index for a in derived(s, ballista).abilities if a.text.startswith('Remove a +1/+1 counter'))
    act(s, 'p1', type='activate_ability', card_id=ballista.id, ability=index, targets=['p2'], sources=[])
    settle(s)
    assert s.state.rules.decision.resume['step'] == 'trigger_target' and not rolled
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    settle(s)
    for _ in range(copies):
        key = next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))
        for ids in [[key], ['pay'], ['0'], ['minus']]:
            d = s.state.rules.decision
            act(s, 'p1', type='choose', decision_id=d.id, option_ids=ids)
    assert rolled == [1]
    assert [e.amount for e in s.state.rules.events if e.counter == 'roll_die'] == [final]
    assert s.state.cards[ballista.id].zone == ('p1:graveyard' if final == 0 else 'p1:battlefield')
    assert s.state.players['p2'].life == 39 and s.state.players['p3'].life == 40
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_noncombat_multiple_recipient_damage_is_one_actual_instance_one_target_and_roll(cards, monkeypatch):
    from tests.test_rules_source_quality_protection import spell
    s, rex = setup(cards)
    put(s, 'Grizzly Bears', 'battlefield', 'p2')
    put(s, 'Grizzly Bears', 'battlefield', 'p3')
    ready(s, rex)
    to_phase(s, 'main2', turn=1)
    rolled = []
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: rolled.append(3) or 3)
    spell(s, "Chandra's Ignition", {'C': 3, 'R': 2}, target=[rex.id])
    assert s.state.rules.decision.resume['step'] == 'trigger_target' and not rolled
    assert s.state.players['p2'].life == s.state.players['p3'].life == 37
    assert s.state.cards[rex.id].zone == 'p1:battlefield'
    answer(s, ['p3'])
    assert rolled == [3]
    assert s.state.players['p3'].life == 34
    assert s.state.cards[rex.id].zone == 'p1:graveyard'
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_native_sacrifice_is_not_prevented_by_retained_indestructible(cards, monkeypatch):
    s, rex = setup(cards)
    source = put(s, 'Darksteel Ingot', 'battlefield')
    pilot = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Fervor', 'battlefield')
    animate(s, source)
    crew(s, source, pilot)
    assert 'indestructible' in derived(s, source).keywords
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: 3)
    combat_target(s, source)
    answer(s, ['p3'])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.players['p3'].life == 37
    roundtrip(s)


def copied_commander_crash(s, rex, monkeypatch, *, before_roll=False):
    from tests.test_rules_source_quality_protection import spell
    act(s, 'p1', type='set_commander', card_id=rex.id)
    put(s, 'March of the Machines', 'battlefield')
    weapon = put(s, 'Legacy Weapon', 'battlefield', 'p2')
    pilot = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    animate(s, rex)
    crew(s, rex, pilot)
    to_phase(s, 'main2', turn=1)
    spell(s, 'Polymorphous Rush', {'C': 2, 'U': 1}, target=[rex.id], target_counts=[1])
    assert s.state.rules.decision is not None
    answer(s, [weapon.id])
    ch = derived(s, rex)
    assert ch.mana_value == 7 and ch.pt == (3, 3)
    assert ch.name == 'Legacy Weapon' and s.state.cards[rex.id].commander_key
    put(s, 'Rest in Peace', 'battlefield')
    settle(s)
    rolled = []
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: rolled.append(6) or 6)
    spell(s, "Chandra's Ignition", {'C': 3, 'R': 2}, target=[rex.id])
    d = s.state.rules.decision
    assert d.resume['step'] == 'trigger_target' and not rolled
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    if before_roll:
        return rolled
    settle(s)
    key = next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))
    for ids in [[key], ['pay'], ['0'], ['plus']]:
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=ids)
    assert rolled == [6]
    assert s.state.rules.decision.resume['step'] == 'zone_replace_order'
    assert s.state.players['p3'].life == 37
    return rolled


@pytest.mark.parametrize('choice', ['yes', 'no'])
def test_native616_then903_terminal_movement_precedes_damage_and_current_mv_differs_from_frozen_power(cards, monkeypatch, choice):
    s, rex = setup(cards)
    rolled = copied_commander_crash(s, rex, monkeypatch)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['library:shuffle'])
    assert s.state.rules.decision.resume['step'] == 'commander_instead'
    assert s.state.players['p3'].life == 37
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[choice])
    settle(s)
    assert s.state.cards[rex.id].zone == ('p1:command' if choice == 'yes' else 'p1:library')
    assert s.state.players['p3'].life == 30
    assert rolled == [6]
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_original_trigger_cannot_sacrifice_stolen_vehicle_but_damage_and_new_controller_trigger_still_happen(cards, monkeypatch):
    from tests.test_rules_source_quality_protection import spell
    s, rex = setup(cards)
    ready(s, rex)
    values = iter([3, 1])
    rolled = []
    def randint(rng, lo, hi):
        value = next(values)
        rolled.append(value)
        return value
    monkeypatch.setattr('secrets.SystemRandom.randint', randint)
    combat_target(s, rex)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    spell(s, 'Act of Aggression', {'C': 3, 'R': 2}, target=[rex.id], player='p2', life_symbols=[])
    assert s.state.cards[rex.id].controller == 'p2' and s.state.cards[rex.id].zone == 'p2:battlefield'
    assert s.state.players['p3'].life == 37 and rolled == [3]
    d = s.state.rules.decision
    assert d.resume['step'] == 'trigger_target' and d.player == 'p2'
    answer(s, ['p1'])
    assert rolled == [3, 1] and s.state.players['p1'].life == 40
    assert s.state.cards[rex.id].zone == 'p2:battlefield'
    assert s.state.rules.turn_log.rolled['p1'] == s.state.rules.turn_log.rolled['p2'] == 1
    roundtrip(s)


def test_copied_crash_rolls_for_copy_controller_independently_before_original(cards, monkeypatch):
    from tests.test_rules_source_quality_protection import spell
    s, rex = setup(cards)
    ready(s, rex)
    values = iter([1, 3])
    rolled = []
    def randint(rng, lo, hi):
        value = next(values)
        rolled.append(value)
        return value
    monkeypatch.setattr('secrets.SystemRandom.randint', randint)
    combat_target(s, rex)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    trigger = s.state.zones['stack'][-1]
    spell(s, 'Return the Favor', {'C': 1, 'R': 2}, target=[trigger], player='p2', modes=[0])
    if s.state.rules.decision is not None:
        assert any(o.id == 'keep' for o in s.state.rules.decision.options)
        answer(s, ['keep'])
    settle(s)
    assert rolled == [1, 3]
    assert s.state.rules.turn_log.rolled['p1'] == s.state.rules.turn_log.rolled['p2'] == 1
    assert s.state.cards[rex.id].zone == 'p1:graveyard'
    assert s.state.players['p3'].life == 37
    roundtrip(s)


@pytest.mark.parametrize('stage', ['616', '903'])
@pytest.mark.parametrize('choice', ['yes', 'no'])
def test_real_terminal_continuation_survives_fresh_process_between_both_native_choices(cards, monkeypatch, tmp_path, stage, choice):
    import subprocess
    import sys
    s, rex = setup(cards)
    copied_commander_crash(s, rex, monkeypatch)
    if stage == '903':
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['library:shuffle'])
        assert s.state.rules.decision.resume['step'] == 'commander_instead'
    path = tmp_path / (stage + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import roundtrip,settle
import app.game.resolve as resolver
path,db,key,stage,choice=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
resolver._rng_int=lambda *args:(_ for _ in ()).throw(AssertionError('terminal choice rerolled'))
def choose(ids):
 d=s.state.rules.decision
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':ids})
assert s.state.players['p3'].life==37 and s.state.players['p1'].life==39
if stage=='616':
 assert s.state.rules.decision.resume['step']=='zone_replace_order'
 choose(['library:shuffle'])
assert s.state.rules.decision.resume['step']=='commander_instead'
assert s.state.players['p3'].life==37
choose([choice])
settle(s)
commander=next(c for c in s.state.cards.values() if c.commander_key==key)
assert commander.zone==('p1:command' if choice=='yes' else 'p1:library')
assert s.state.players['p3'].life==30 and s.state.players['p1'].life==39
assert len([e for e in s.state.rules.events if e.counter=='roll_die' and e.amount==7])==1
assert s.state.rules.turn_log.rolled['p1']==1
assert s.state.rules.decision is None and not s.state.zones.get('stack')
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), s.state.cards[rex.id].commander_key, stage, choice], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('missing', ['original_oid', 'original_lki'])
@pytest.mark.parametrize('cold', [False, True])
def test_older_pending_trigger_never_reads_new_incarnation_as_missing_original_value(cards, monkeypatch, tmp_path, missing, cold):
    from app.game.session import GameSession
    from app.game.state import GameState
    from tests.test_rules_source_quality_protection import spell
    s, rex = setup(cards)
    ready(s, rex)
    combat_target(s, rex)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    trigger = s.state.zones['stack'][-1]
    original = s.state.rules.object_id(rex.id)
    spell(s, 'Flicker of Fate', {'C': 1, 'W': 1}, target=[rex.id], player='p2', finish=False)
    for _ in range(20):
        if s.state.rules.object_id(rex.id) != original:
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert s.state.rules.object_id(rex.id) != original
    data = s.state.model_dump(mode='json')
    if missing == 'original_oid':
        data['rules']['stack'][trigger].pop('source_object')
    else:
        data['rules']['lki'].pop(original)
    s = GameSession(GameState.model_validate(data), cards=cards)
    rolled = []
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: rolled.append(3) or 3)
    settle(s)
    d = s.state.rules.decision
    assert d.kind == 'manual_resolution' and 'final die result is 3' in d.prompt
    assert rolled == [3] and s.state.players['p3'].life == 40
    assert derived(s, rex).types == {'Creature'}
    if cold:
        import subprocess
        import sys
        path = tmp_path / (missing + '.json')
        path.write_text(s.state.model_dump_json())
        code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import roundtrip,settle
import app.game.resolve as resolver
path,db,cid=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
resolver._rng_int=lambda *args:(_ for _ in ()).throw(AssertionError('manual Done rerolled'))
d=s.state.rules.decision
assert d.kind=='manual_resolution'
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['done']})
settle(s)
assert s.state.cards[cid].zone=='p1:battlefield'
assert s.state.players['p3'].life==40 and s.state.rules.turn_log.rolled['p1']==1
assert not s.state.zones.get('stack') and not s.state.rules.stack
assert s.state.rules.decision is None
roundtrip(s)
repo.close()
'''
        result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), rex.id], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return
    answer(s, ['done'])
    assert not s.state.zones.get('stack') and not s.state.rules.stack
    assert s.state.cards[rex.id].zone == 'p1:battlefield' and s.state.players['p3'].life == 40
    assert rolled == [3]
    roundtrip(s)


@pytest.mark.parametrize('stage', ['before_target', 'announced_target'])
def test_fresh_process_target_announcement_and_first_raw_roll_follow_native_timing(cards, monkeypatch, tmp_path, stage):
    import subprocess
    import sys
    s, rex = setup(cards)
    ready(s, rex)
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda *args: (_ for _ in ()).throw(AssertionError('rolled before target or resolution')))
    combat_target(s, rex)
    if stage == 'announced_target':
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
        assert s.state.rules.decision is None
    path = tmp_path / (stage + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import roundtrip,settle
import app.game.resolve as resolver
path,db,cid,stage=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
raw=[]
def roll(*args):
 assert args[-2:]==(1,6)
 raw.append(3)
 return 3
resolver._rng_int=roll
assert not s.state.rules.turn_log.rolled.get('p1',0)
if stage=='before_target':
 d=s.state.rules.decision
 assert d.player=='p1' and d.resume['step']=='trigger_target'
 s.perform('p1',{'type':'choose','decision_id':d.id,'option_ids':['p3']})
assert raw==[]
settle(s)
assert raw==[3] and s.state.rules.turn_log.rolled['p1']==1
assert s.state.players['p2'].life==37 and s.state.players['p3'].life==37
assert s.state.cards[cid].zone=='p1:graveyard'
assert not s.state.zones.get('stack') and s.state.rules.decision is None
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), rex.id, stage], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('blocker_pt,source_died', [('1/1', False), ('2/2', True)])
def test_two_blockers_are_one_combat_instance_even_when_vehicle_dies_before_trigger(cards, monkeypatch, blocker_pt, source_died):
    from tests.test_rules_effects import token
    s, rex = setup(cards)
    first = token(s, 'p2', 'First blocker', pt=blocker_pt)
    second = token(s, 'p2', 'Second blocker', pt=blocker_pt)
    ready(s, rex)
    source_oid = s.state.rules.object_id(rex.id)
    rolled = []
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: rolled.append(3) or 3)
    to_phase(s, 'declare_attackers', turn=1)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': rex.id, 'target': 'p2'}])
    to_phase(s, 'declare_blockers', turn=1)
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': first.id, 'attacker_id': rex.id}, {'blocker_id': second.id, 'attacker_id': rex.id}])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.resume['step'] == 'block_split':
            break
        act(s, s.state.rules.priority, type='pass_priority')
    d = s.state.rules.decision
    assert d.kind == 'divide' and d.resume['step'] == 'block_split'
    act(s, d.player, type='choose', decision_id=d.id, amounts=[2, 1])
    settle(s)
    assert s.state.rules.decision.resume['step'] == 'trigger_target'
    assert (s.state.cards[rex.id].zone == 'p1:graveyard') == source_died
    damage = [e for e in s.state.rules.events if e.kind == 'damage' and e.source == source_oid and e.combat]
    assert sorted(e.amount for e in damage) == [1, 2]
    assert len({e.batch for e in damage}) == 1 and not rolled
    answer(s, ['p3'])
    assert rolled == [3] and s.state.players['p3'].life == 37
    assert s.state.players['p2'].life == 40 and not s.state.zones.get('stack')
    roundtrip(s)


def test_separate_real_damage_instructions_create_separate_crashes_not_one_resolution_group(cards, monkeypatch):
    from tests.test_rules_source_quality_protection import spell
    s, rex = setup(cards)
    ballista = spell(s, 'Walking Ballista', {'C': 6}, x_value=3)
    animate(s, ballista)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    rolled = []
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: rolled.append(1) or 1)
    index = next(a.index for a in derived(s, ballista).abilities if a.text.startswith('Remove a +1/+1 counter'))
    for _ in range(2):
        act(s, 'p1', type='activate_ability', card_id=ballista.id, ability=index, targets=['p2'], sources=[])
    settle(s)
    assert s.state.rules.decision.resume['step'] == 'trigger_target' and not rolled
    first_event = next(t.event for t in s.state.rules.pending_triggers if t.id == s.state.rules.decision.resume['trigger'])
    assert first_event.kind == 'deal_damage' and first_event.amount == 1
    answer(s, ['p3'])
    assert rolled == [1] and s.state.rules.decision.resume['step'] == 'trigger_target'
    second_event = next(t.event for t in s.state.rules.pending_triggers if t.id == s.state.rules.decision.resume['trigger'])
    assert second_event.kind == 'deal_damage' and second_event.amount == 1
    assert first_event.batch != second_event.batch
    answer(s, ['p3'])
    assert rolled == [1, 1] and not s.state.zones.get('stack')
    assert s.state.players['p2'].life == 38 and s.state.players['p3'].life == 40
    assert s.state.cards[ballista.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_primary_source_leaving_does_not_end_the_independent_target_vehicle_grant(cards):
    from tests.test_rules_source_quality_protection import spell
    s, rex = setup(cards)
    target = put(s, 'Sol Ring', 'battlefield')
    to_phase(s, 'begin_combat', turn=1)
    settle(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[target.id])
    spell(s, 'Beast Within', {'C': 2, 'G': 1}, target=[rex.id], player='p2')
    assert s.state.cards[rex.id].zone == 'p1:graveyard'
    assert derived(s, target).types == {'Artifact'} and derived(s, target).subtypes == {'Vehicle'}
    beast = next(c for c in s.state.cards.values() if c.is_token and c.name == 'Beast' and c.controller == 'p1')
    crew(s, target, beast)
    assert derived(s, target).pt == (1, 1)
    assert any(a.text == leaf._CRASH for a in derived(s, target).abilities)
    roundtrip(s)


def test_primary_target_blink_counters_grant_instead_of_animating_new_incarnation(cards):
    from tests.test_rules_source_quality_protection import spell
    s, rex = setup(cards)
    to_phase(s, 'begin_combat', turn=1)
    settle(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[rex.id])
    original = s.state.rules.object_id(rex.id)
    spell(s, 'Flicker of Fate', {'C': 1, 'W': 1}, target=[rex.id], player='p2')
    assert s.state.rules.object_id(rex.id) != original
    assert derived(s, rex).types == {'Creature'} and len(derived(s, rex).abilities) == 1
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_native_artifact_activation_ban_suppresses_granted_crew_without_tapping_pilot(cards):
    from app.game.errors import ActionError
    s, rex = setup(cards)
    pilot = put(s, 'Grizzly Bears', 'battlefield')
    put(s, 'Stony Silence', 'battlefield')
    animate(s, rex)
    index = next(a.index for a in derived(s, rex).abilities if a.text.lower().rstrip('.') == 'crew 2')
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=rex.id, ability=index, crew=[pilot.id], sources=[])
    assert not s.state.cards[pilot.id].tapped and derived(s, rex).types == {'Artifact'}
    roundtrip(s)


def test_whole_printed_canonical_gate(cards):
    from app.rules import coverage
    result = coverage.of_card_data(cards.resolve(NAME))
    assert result.level == 'FULL', result


def test_kept_modifier_pause_resumes_cold_before_zero_match_sacrifice_and_zero_damage(cards, monkeypatch, tmp_path):
    import subprocess
    import sys

    from tests.test_rules_source_quality_protection import spell
    s, rex = setup(cards)
    ballista = spell(s, 'Walking Ballista', {'C': 4}, x_value=2)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    animate(s, ballista)
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: 1)
    index = next(a.index for a in derived(s, ballista).abilities if a.text.startswith('Remove a +1/+1 counter'))
    act(s, 'p1', type='activate_ability', card_id=ballista.id, ability=index, targets=['p2'], sources=[])
    settle(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['p3'])
    settle(s)
    assert s.state.rules.decision.resume['step'] == 'numeric_roll42'
    assert not s.state.rules.turn_log.rolled.get('p1', 0)
    path = tmp_path / 'raw-before-zero.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from tests.test_rules_designations import roundtrip,settle
import app.game.resolve as resolver
path,db,cid=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
resolver._rng_int=lambda *args:(_ for _ in ()).throw(AssertionError('raw value rerolled'))
key=next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))
for ids in [[key],['pay'],['0'],['minus']]:
 d=s.state.rules.decision
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':ids})
settle(s)
assert s.state.cards[cid].zone=='p1:graveyard'
assert s.state.players['p2'].life==39 and s.state.players['p3'].life==40
assert s.state.players['p1'].life==39
assert s.state.rules.turn_log.rolled['p1']==1
assert len([e for e in s.state.rules.events if e.counter=='roll_die' and e.amount==0])==1
assert not s.state.zones.get('stack') and s.state.rules.decision is None
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), ballista.id], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_extra_ignored_die_uses_kept_result_for_equality_and_only_one_roll_event(cards, monkeypatch):
    s, rex = setup(cards)
    put(s, 'Pixie Guide', 'battlefield')
    ready(s, rex)
    values = iter([1, 3])
    raw = []
    def randint(rng, lo, hi):
        value = next(values)
        raw.append(value)
        return value
    monkeypatch.setattr('secrets.SystemRandom.randint', randint)
    combat_target(s, rex)
    answer(s, ['p3'])
    assert raw == [1, 3]
    assert s.state.rules.turn_log.rolled['p1'] == 1
    assert s.state.cards[rex.id].zone == 'p1:graveyard' and s.state.players['p3'].life == 37
    roundtrip(s)


def test_real_blink_reads_copied_original_lki_mv_instead_of_new_incarnations_different_mv(cards, monkeypatch):
    from tests.test_rules_source_quality_protection import spell
    s, rex = setup(cards)
    rolled = copied_commander_crash(s, rex, monkeypatch, before_roll=True)
    original = s.state.rules.object_id(rex.id)
    spell(s, 'Flicker of Fate', {'C': 1, 'W': 1}, target=[rex.id], player='p2')
    assert s.state.rules.object_id(rex.id) != original
    assert derived(s, rex).mana_value == 3 and derived(s, rex).pt == (2, 2)
    assert original in s.state.rules.lki and rolled == [6]
    key = next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))
    for ids in [[key], ['pay'], ['0'], ['plus']]:
        d = s.state.rules.decision
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=ids)
    settle(s)
    assert s.state.cards[rex.id].zone == 'p1:battlefield'
    assert s.state.players['p3'].life == 30
    assert rolled == [6] and not s.state.zones.get('stack')
    roundtrip(s)
