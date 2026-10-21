"""Production whole-card gameplay for wave42 native random/entry outcomes."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import priority
from tests.test_rules_random_consequences import answer, faces
from tests.test_rules_source_quality_protection import spell
from tests.test_rules_wave30m_durations import three, to_phase
from tests.test_rules_wave31d_spell_copies import hold

DATA = json.loads((Path(__file__).parent / 'fixtures/random_native_outcomes42_cards.json').read_text())


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(DATA):
        base[c['name']] = card(c['name'], set_code='r42', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def setup(cards):
    names = [c['name'] for c in DATA] + ['Sol Ring', 'Lightning Bolt', 'Grizzly Bears', 'Forest']
    s = three(cards, names, names, names)
    hold(s)
    return s


@pytest.mark.parametrize('x', [0, 1, 9])
def test_reap_actual_x_without_replacement_and_resolving_source_exile(cards, monkeypatch, x):
    import secrets
    s = setup(cards)
    gy = [put(s, n, 'graveyard') for n in ['Forest', 'Lightning Bolt', 'Grizzly Bears']]
    sampled = []
    def sample(rng, pool, n):
        sampled.append((tuple(pool), n))
        return list(pool)[:n]
    monkeypatch.setattr(secrets.SystemRandom, 'sample', sample)
    source = spell(s, 'Reap the Past', {'R': 1, 'G': 1, 'C': x}, x_value=x)
    assert len([c for c in gy if s.state.cards[c.id].zone == 'p1:hand']) == min(x, 3)
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert not s.state.rules.turn_log.rolled
    assert len(sampled) == (1 if 0 < x < 3 else 0)
    assert all(source.id not in pool and n == min(x, 3) for pool, n in sampled)
    roundtrip(s)


@pytest.mark.parametrize('result,zone', [(1, 'library'), (9, 'library'), (10, 'hand'), (19, 'hand'), (20, 'battlefield')])
def test_troll_actual_graveyard_activation_each_native_table_boundary(cards, monkeypatch, result, zone):
    s = setup(cards)
    source = put(s, 'Loathsome Troll', 'graveyard')
    faces(monkeypatch, [result])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'G': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    settle(s)
    actual = next(c for c in s.state.cards.values() if c.name == source.name and c.owner == 'p1' and c.zone == 'p1:' + zone)
    if zone == 'library':
        assert s.state.zones['p1:library'][0] == actual.id
    if zone == 'battlefield':
        assert actual.tapped
    roundtrip(s)


@pytest.mark.parametrize('pick', ['0', '1'])
def test_grave_endeavor_native_selected_entry_counters_and_other_result_life(cards, monkeypatch, pick):
    s = setup(cards)
    target = put(s, 'Grizzly Bears', 'graveyard')
    faces(monkeypatch, [2, 8])
    spell(s, 'Grave Endeavor', {'C': 5, 'B': 2})
    assert s.state.rules.decision.resume['step'] == 'roll_choose'
    answer(s, [pick])
    selected, other = (2, 8) if pick == '0' else (8, 2)
    assert s.state.cards[target.id].zone == 'p1:battlefield'
    assert s.state.cards[target.id].counters['+1/+1'] == selected
    assert s.state.players['p1'].life == 40 + other
    assert s.state.players['p2'].life == s.state.players['p3'].life == 40 - other
    roundtrip(s)


@pytest.mark.parametrize('name', ['Reap the Past', 'Grave Endeavor', 'Loathsome Troll'])
def test_whole_printed_canonical_candidate_gate(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_reap_freezes_selected_commander_subset_before_native903_choice(cards, monkeypatch):
    import secrets
    s = setup(cards)
    commander = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.commander_key)
    act(s, 'p1', type='move', card_ids=[commander.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, s.state.rules.priority, type='pass_priority')
    if s.state.rules.decision is not None:
        answer(s, ['no'])
    to_phase(s, 'main1', turn=4)
    put(s, 'Forest', 'graveyard')
    calls = []
    def sample(rng, pool, n):
        calls.append(tuple(pool))
        assert commander.id in pool
        return [commander.id]
    monkeypatch.setattr(secrets.SystemRandom, 'sample', sample)
    spell(s, 'Reap the Past', {'R': 1, 'G': 1, 'C': 1}, x_value=1)
    assert len(calls) == 1
    assert s.state.rules.decision.resume['step'] == 'commander_first'
    answer(s, ['no'])
    assert len(calls) == 1
    assert s.state.cards[commander.id].zone == 'p1:hand'
    roundtrip(s)


@pytest.mark.parametrize('phase', ['roll', 'entry'])
def test_grave_native_roll_or_actual_entry_choice_resumes_in_fresh_process(cards, monkeypatch, tmp_path, phase):
    import subprocess
    import sys
    s = setup(cards)
    target = put(s, 'True-Name Nemesis', 'graveyard')
    put(s, 'Grizzly Bears', 'graveyard')
    faces(monkeypatch, [2, 8])
    spell(s, 'Grave Endeavor', {'C': 5, 'B': 2})
    if phase == 'entry':
        answer(s, ['0'])
        answer(s, [target.id])
    path = tmp_path / (phase + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.game.session import GameSession
from app.game.state import GameState
path, db, target, phase = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
importlib.import_module('app.game.resolve')._rng_int = lambda *args: (_ for _ in ()).throw(AssertionError('saved dice rolled again'))
def choose(ids):
 d = s.state.rules.decision
 assert d is not None
 s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':ids})
if phase == 'roll':
 assert s.state.rules.decision.resume['step'] == 'roll_choose'
 choose(['0'])
 choose([target])
choose(['p2'])
assert s.state.cards[target].zone == 'p1:battlefield'
assert s.state.cards[target].counters['+1/+1'] == 2
assert s.state.players['p1'].life == 48
assert s.state.players['p2'].life == s.state.players['p3'].life == 32
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), target.id, phase], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('zone,owner', [('battlefield', 'p1'), ('hand', 'p1'), ('graveyard', 'p2')])
def test_troll_refuses_wrong_source_zone_or_owner_before_payment_and_entropy(cards, monkeypatch, zone, owner):
    s = setup(cards)
    source = put(s, 'Loathsome Troll', zone, owner)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'G': 1})
    monkeypatch.setattr('app.game.resolve._rng_int', lambda *a: pytest.fail('Illegal activation must not roll'))
    before = s.state.model_dump()
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    assert s.state.model_dump() == before
    roundtrip(s)


def test_troll_ability_rolls_but_never_returns_new_graveyard_incarnation(cards, monkeypatch):
    s = setup(cards)
    source = put(s, 'Loathsome Troll', 'graveyard')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'G': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[source.id], to={'player': 'p1', 'zone': 'graveyard'})
    faces(monkeypatch, [20])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


@pytest.mark.parametrize('kind', ['empty', 'doubles', 'extra', 'cage', 'double_counters', 'humility'])
def test_grave_native_empty_doubles_extra_die_and_entry_replacements(cards, monkeypatch, kind):
    s = setup(cards)
    support = {'extra': 'Pixie Guide', 'cage': "Grafdigger's Cage", 'double_counters': 'Doubling Season', 'humility': 'Humility'}
    if kind in support:
        put(s, support[kind], 'battlefield')
    target = put(s, 'Grizzly Bears', 'graveyard') if kind != 'empty' else None
    faces(monkeypatch, [4, 4] if kind == 'doubles' else [2, 8, 9] if kind == 'extra' else [2, 8])
    spell(s, 'Grave Endeavor', {'C': 5, 'B': 2})
    if kind != 'doubles':
        answer(s, ['0'])
    selected, other = (4, 4) if kind == 'doubles' else (8, 9) if kind == 'extra' else (2, 8)
    if target:
        assert s.state.cards[target.id].zone == ('p1:graveyard' if kind == 'cage' else 'p1:battlefield')
        if kind != 'cage':
            assert s.state.cards[target.id].counters['+1/+1'] == selected * (2 if kind == 'double_counters' else 1)
    assert s.state.players['p1'].life == 40 + other
    assert s.state.players['p2'].life == s.state.players['p3'].life == 40 - other
    assert s.state.rules.turn_log.rolled['p1'] == 2
    roundtrip(s)


@pytest.mark.parametrize('kind', ['troll', 'reap_no', 'reap_yes'])
def test_paid_source_or_selected_random_packet_resumes_without_candidate_runtime_bootstrap(cards, monkeypatch, tmp_path, kind):
    import secrets
    import subprocess
    import sys
    s = setup(cards)
    expected = []
    if kind == 'troll':
        source = put(s, 'Loathsome Troll', 'graveyard')
        priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'G': 1})
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
        expected = [source.id]
    else:
        commander = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.commander_key)
        act(s, 'p1', type='move', card_ids=[commander.id], to={'player': 'p1', 'zone': 'graveyard'})
        act(s, s.state.rules.priority, type='pass_priority')
        answer(s, ['no'])
        to_phase(s, 'main1', turn=4)
        other = put(s, 'Forest', 'graveyard')
        monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda rng, pool, n: [commander.id])
        source = spell(s, 'Reap the Past', {'R': 1, 'G': 1, 'C': 1}, x_value=1)
        assert s.state.rules.decision.resume['step'] == 'commander_first'
        expected = [commander.id, other.id, source.id]
    path = tmp_path / (kind + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib, json, secrets, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, db, kind, expected = sys.argv[1:]
expected = json.loads(expected)
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
secrets.SystemRandom.sample = lambda *args: (_ for _ in ()).throw(AssertionError('selected packet resampled'))
importlib.import_module('app.game.resolve')._rng_int = lambda rng, lo, hi: 20 if kind == 'troll' else (_ for _ in ()).throw(AssertionError('Reap is not a die'))
if kind != 'troll':
 d = s.state.rules.decision
 s.perform(d.player, {'type':'choose','decision_id':d.id,'option_ids':['yes' if kind == 'reap_yes' else 'no']})
for _ in range(40):
 if not s.state.zones.get('stack'):break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority, {'type':'pass_priority'})
if kind == 'troll':
 assert s.state.cards[expected[0]].zone == 'p1:battlefield' and s.state.cards[expected[0]].tapped
 assert s.state.rules.turn_log.rolled['p1'] == 1
else:
 assert s.state.cards[expected[0]].zone == 'p1:' + ('command' if kind == 'reap_yes' else 'hand')
 assert s.state.cards[expected[1]].zone == 'p1:graveyard' and s.state.cards[expected[2]].zone == 'p1:exile'
assert s.history.rebuild() == s.state
assert GameState.model_validate_json(s.state.model_dump_json()) == s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), kind, json.dumps(expected)], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('kind', ['reap', 'troll'])
def test_actual_lithoform_copies_keep_x_or_original_gy_identity_and_do_not_pay_again(cards, monkeypatch, kind):
    import secrets
    s = setup(cards)
    engine = put(s, 'Lithoform Engine', 'battlefield')
    if kind == 'reap':
        targets = [put(s, name, 'graveyard') for name in ['Forest', 'Lightning Bolt']]
        monkeypatch.setattr(secrets.SystemRandom, 'sample', lambda rng, pool, n: list(pool)[:n])
        source = spell(s, 'Reap the Past', {'R': 1, 'G': 1, 'C': 1}, x_value=1, finish=False)
        stack_id = source.id
        cost, ability = 3, 1
    else:
        source = put(s, 'Loathsome Troll', 'graveyard')
        priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'G': 1})
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
        stack_id = s.state.zones['stack'][-1]
        cost, ability = 2, 0
        faces(monkeypatch, [20, 1])
    act(s, 'p1', type='add_mana', player='p1', mana={'C': cost})
    act(s, 'p1', type='activate_ability', card_id=engine.id, ability=ability, targets=[stack_id], sources=[])
    settle(s)
    # The native copy asks whether to keep the original targetless program only
    # if needed; these programs have no new target announcement.
    assert s.state.rules.decision is None
    if kind == 'reap':
        assert all(s.state.cards[c.id].zone == 'p1:hand' for c in targets)
        assert s.state.cards[source.id].zone == 'p1:exile'
    else:
        assert s.state.cards[source.id].zone == 'p1:battlefield' and s.state.cards[source.id].tapped
        assert s.state.rules.turn_log.rolled['p1'] == 2
    roundtrip(s)
