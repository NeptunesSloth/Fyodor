"""Counter-removal events retain quantity, remover, source object and exile timing."""
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
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_remaining_talents import pay
from tests.test_rules_shared_damage_choices import table
from tests.test_rules_wave7b_activation import ability_index

NAMES = ['Chandra, Fire Artisan', 'Protean Hydra', 'Watcher of Hours', 'Riftmarked Knight', 'Veiling Oddity']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    for i, c in enumerate(json.loads((Path(__file__).parent / 'fixtures/counter_removal_trigger_cards.json').read_text())):
        base[c['name']] = card(c['name'], set_code='crt', number=str(i), **{k: v for k, v in c.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def game(cards):
    return table(cards, [*NAMES, 'Vampire Hexmage', 'Timecrafting', 'Doubling Season', 'Shock', 'Grizzly Bears', 'Fury Charm', 'Shivan Sand-Mage', 'Timebender'],
                 ['Vampire Hexmage', 'Timecrafting', 'Shock', 'Stifle'], ['Grizzly Bears'])


def cast(s, name, *, targets=(), x=None, modes=None, player='p1'):
    from tests.test_rules_bandmate_references import wait_priority
    c = put(s, name, 'hand', pid=player)
    pay(s, player, name)
    if x:
        act(s, player, type='add_mana', player=player, mana={'C': x})
    wait_priority(s, player)
    act(s, player, type='cast_spell', card_id=c.id, targets=list(targets), sources=[],
        **({'x_value': x} if x is not None else {}), **({'modes': modes} if modes is not None else {}))
    return c


def answer_targets(s, target):
    for _ in range(40):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            return
        ids = {o.id for o in d.options}
        assert target in ids, (d.kind, d.prompt, ids)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[target])
    raise AssertionError('target selection did not finish')


@pytest.mark.parametrize('name', NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'


def test_chandra_damage_removes_two_loyalty_but_triggers_once_for_two_damage(cards):
    s = game(cards)
    chandra = cast(s, 'Chandra, Fire Artisan')
    settle(s)
    cast(s, 'Shock', targets=[chandra.id], player='p2')
    answer_targets(s, 'p2')
    assert s.state.cards[chandra.id].counters['loyalty'] == 2
    assert s.state.players['p2'].life == 38
    roundtrip(s)


def test_chandra_paid_loyalty_cost_triggers_even_when_cost_kills_source(cards):
    s = game(cards)
    chandra = cast(s, 'Chandra, Fire Artisan')
    settle(s)
    act(s, 'p1', type='set_counter', card_id=chandra.id, kind='loyalty', value=7)
    act(s, 'p1', type='activate_ability', card_id=chandra.id, ability=ability_index(s, chandra, 'Exile the top seven'))
    assert s.state.cards[chandra.id].zone == 'p1:graveyard'
    answer_targets(s, 'p2')
    assert s.state.players['p2'].life == 33
    roundtrip(s)


def test_hydra_two_removed_counters_create_two_distinct_delayed_triggers(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    hydra = cast(s, 'Protean Hydra', x=5)
    settle(s)
    cast(s, 'Shock', targets=[hydra.id], player='p2')
    settle(s)
    assert s.state.cards[hydra.id].damage == 0
    assert s.state.cards[hydra.id].counters['+1/+1'] == 3
    assert len(s.state.rules.delayed) == 2
    roundtrip(s)
    to_phase(s, 'end')
    settle(s)
    assert s.state.cards[hydra.id].counters['+1/+1'] == 7
    roundtrip(s)


def suspended(s, name):
    c = put(s, name, 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'U': 1, 'W': 2})
    act(s, 'p1', type='activate_ability', card_id=c.id, ability=ability_index(s, c, 'Suspend'), sources=[])
    assert s.state.cards[c.id].zone == 'p1:exile'
    return c


def test_watcher_each_removed_counter_gets_its_own_surveil(cards):
    s = game(cards)
    watcher = suspended(s, 'Watcher of Hours')
    cast(s, 'Timecrafting', targets=[watcher.id], x=2, modes=[0])
    settle(s)
    decisions = 0
    for _ in range(20):
        d = s.state.rules.decision
        if d is None:
            break
        assert 'surveil' in d.prompt.lower(), (d.kind, d.prompt)
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        decisions += 1
        settle(s)
    assert decisions == 2
    assert s.state.cards[watcher.id].counters['time'] == 4
    roundtrip(s)


def test_watcher_ignores_time_counters_removed_by_opponent(cards):
    s = game(cards)
    watcher = suspended(s, 'Watcher of Hours')
    cast(s, 'Timecrafting', targets=[watcher.id], x=2, modes=[0], player='p2')
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[watcher.id].counters['time'] == 4
    roundtrip(s)


@pytest.mark.parametrize('name', ['Riftmarked Knight', 'Veiling Oddity'])
def test_last_counter_exile_trigger_still_resolves_when_suspend_cast_is_declined(cards, name):
    from app.rules.plan import Plan
    s = game(cards)
    creature = put(s, 'Grizzly Bears', 'battlefield')
    source = suspended(s, name)
    act(s, 'p1', type='set_counter', card_id=source.id, kind='time', value=1)
    cast(s, 'Timecrafting', targets=[source.id], x=1, modes=[0])
    for _ in range(30):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        assert (d.resume or {}).get('step') == 'suspend_cast', (d.kind, d.prompt)
        roundtrip(s)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=['no'])
    assert s.state.cards[source.id].zone == 'p1:exile'
    assert s.state.cards[source.id].counters.get('time', 0) == 0
    p = Plan(s.state, 'p1', s.cards, None)
    if name == 'Riftmarked Knight':
        tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield']
        assert len(tokens) == 1
        ch = p.ch(tokens[0])
        assert ch.pt == (2, 2) and ch.colors == frozenset({'B'})
        assert {'flanking', 'haste', 'protection'} <= ch.keywords
        assert 'white' in tokens[0].token.text.lower()
    else:
        assert 'cant_be_blocked' in p.ch(s.state.cards[creature.id]).imposed
    roundtrip(s)


def test_timecrafting_addition_targets_permanent_branch_but_not_unsuspended_exile(cards):
    from app.game.errors import ActionError
    s = game(cards)
    watcher = put(s, 'Watcher of Hours', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=watcher.id, kind='time', value=1)
    spell = cast(s, 'Timecrafting', targets=[watcher.id], x=2, modes=[1])
    settle(s)
    assert s.state.cards[watcher.id].counters['time'] == 3
    act(s, 'p1', type='move', card_ids=[watcher.id], to={'player': 'p1', 'zone': 'exile'})
    act(s, 'p1', type='move', card_ids=[spell.id], to={'player': 'p1', 'zone': 'hand'})
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1})
    with pytest.raises(ActionError):
        act(s, 'p1', type='cast_spell', card_id=spell.id, targets=[watcher.id], x_value=1, modes=[0], sources=[])
    roundtrip(s)


def test_watcher_upkeep_removes_one_counter_and_triggers_once(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    watcher = suspended(s, 'Watcher of Hours')
    to_phase(s, 'upkeep', turn=4)
    settle(s)
    d = s.state.rules.decision
    assert d and 'surveil' in d.prompt.lower()
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[watcher.id].counters['time'] == 5
    roundtrip(s)


def test_removing_zero_does_not_trigger_watcher(cards):
    s = game(cards)
    watcher = suspended(s, 'Watcher of Hours')
    cast(s, 'Timecrafting', targets=[watcher.id], x=0, modes=[0])
    settle(s)
    assert s.state.rules.decision is None
    assert s.state.cards[watcher.id].counters['time'] == 6
    roundtrip(s)


def test_hydra_delayed_counters_use_actual_replacement_and_do_not_affect_new_object(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    hydra = cast(s, 'Protean Hydra', x=5)
    settle(s)
    cast(s, 'Shock', targets=[hydra.id], player='p2')
    settle(s)
    put(s, 'Doubling Season', 'battlefield')
    to_phase(s, 'end')
    settle(s)
    assert s.state.cards[hydra.id].counters['+1/+1'] == 11  # three remain; two separate events put four each.
    roundtrip(s)


def test_hydra_lethal_removal_still_creates_each_trigger_but_no_old_object_is_returned(cards):
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    hydra = cast(s, 'Protean Hydra', x=2)
    settle(s)
    cast(s, 'Shock', targets=[hydra.id], player='p2')
    settle(s)
    assert s.state.cards[hydra.id].zone == 'p1:graveyard'
    assert len(s.state.rules.delayed) == 2
    # A new copy of the same physical card must not receive the old object's delayed counters.
    cast(s, 'Protean Hydra', x=3)
    settle(s)
    to_phase(s, 'end')
    settle(s)
    assert s.state.cards[hydra.id].counters['+1/+1'] == 3
    roundtrip(s)


def test_veiling_oddity_restriction_includes_later_creatures_and_expires(cards):
    from app.rules.plan import Plan
    from tests.test_rules_wave30m_durations import to_phase
    s = game(cards)
    source = suspended(s, 'Veiling Oddity')
    act(s, 'p1', type='set_counter', card_id=source.id, kind='time', value=1)
    cast(s, 'Timecrafting', targets=[source.id], x=1, modes=[0])
    settle(s)
    d = s.state.rules.decision
    assert d and (d.resume or {}).get('step') == 'suspend_cast'
    act(s, d.player, type='choose', decision_id=d.id, option_ids=['yes'])
    settle(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    later = put(s, 'Grizzly Bears', 'battlefield')
    assert 'cant_be_blocked' in Plan(s.state, 'p1', s.cards, None).ch(later).imposed
    roundtrip(s)
    to_phase(s, 'main1', turn=2)
    assert 'cant_be_blocked' not in Plan(s.state, 'p1', s.cards, None).ch(s.state.cards[later.id]).imposed
    roundtrip(s)


def test_watcher_surveil_resumes_in_fresh_process(cards, tmp_path):
    import subprocess
    import sys
    s = game(cards)
    source = suspended(s, 'Watcher of Hours')
    cast(s, 'Timecrafting', targets=[source.id], x=1, modes=[0])
    settle(s)
    assert s.state.rules.decision and 'surveil' in s.state.rules.decision.prompt.lower()
    saved = tmp_path / 'watcher.json'
    saved.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
state_path, database, target = sys.argv[1:]
repo = CardRepository(Path(database), ImageStore(Path(database).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(state_path).read_text()), cards=repo)
d = s.state.rules.decision
assert 'surveil' in d.prompt.lower()
s.perform(d.player, {'type':'choose', 'decision_id':d.id, 'option_ids':[]})
assert s.state.cards[target].counters['time'] == 5
assert s.history.rebuild().model_dump(mode='json') == s.state.model_dump(mode='json')
assert GameState.model_validate_json(s.state.model_dump_json()).model_dump(mode='json') == s.state.model_dump(mode='json')
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(saved), str(cards.db_path), source.id],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr



def test_fury_charm_real_multi_removal_collateral(cards):
    assert coverage.of_card_data(cards.resolve('Fury Charm')).level == 'FULL'
    assert coverage.of_card_data(cards.resolve('Timecrafting')).level == 'FULL'
    s = game(cards)
    watcher = suspended(s, 'Watcher of Hours')
    cast(s, 'Fury Charm', targets=[watcher.id], modes=[2])
    count = 0
    for _ in range(10):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        assert 'surveil' in d.prompt.lower()
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        count += 1
    assert count == 2
    assert s.state.cards[watcher.id].counters['time'] == 4
    roundtrip(s)



@pytest.mark.parametrize('name', ['Shivan Sand-Mage', 'Timebender'])
@pytest.mark.parametrize('mode', [0, 1])
def test_real_modal_time_counter_creature_collaterals(cards, name, mode):
    assert coverage.of_card_data(cards.resolve(name)).level == 'FULL'
    s = game(cards)
    watcher = suspended(s, 'Watcher of Hours')
    if name == 'Timebender':
        source = put(s, name, 'hand')
        act(s, 'p1', type='add_mana', player='p1', mana={'C':3})
        act(s, 'p1', type='cast_spell', card_id=source.id, face_down=True, sources=[])
        settle(s)
        act(s, 'p1', type='add_mana', player='p1', mana={'U':1})
        act(s, 'p1', type='turn_face_up', card_id=source.id, sources=[])
    else:
        source = cast(s, name)
    settle(s)
    d = s.state.rules.decision
    assert d and len(d.options) == 2, (d.kind if d else None, d.prompt if d else None)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[d.options[mode].id])
    settle(s)
    d = s.state.rules.decision
    assert d and watcher.id in {o.id for o in d.options}
    roundtrip(s)
    act(s, d.player, type='choose', decision_id=d.id, option_ids=[watcher.id])
    count = 0
    for _ in range(10):
        settle(s)
        d = s.state.rules.decision
        if d is None:
            break
        assert 'surveil' in d.prompt.lower(), (d.kind, d.prompt)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=[])
        count += 1
    assert count == (2 if mode == 0 else 0)
    assert s.state.cards[watcher.id].counters['time'] == (4 if mode == 0 else 8)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)
