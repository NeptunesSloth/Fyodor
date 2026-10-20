"""Production numeric activation costs, monstrosity, and native continuations."""
import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_random_native_outcomes42 import DATA
from tests.test_rules_wave30m_durations import three
from tests.test_rules_wave31d_spell_copies import hold

SUPPORT = json.loads((Path(__file__).parent / 'fixtures/random_previous_combat44_cards.json').read_text())
SUPPORT += [row for row in json.loads((Path(__file__).parent / 'fixtures/random_receipt_consumers_cards.json').read_text())
            if row['name'] == 'Mr. House, President and CEO']


@pytest.fixture()
def cards(settings):
    base = {c['name']: c for c in fixture_cards()}
    rows = [*DATA, *SUPPORT, *json.loads((Path(__file__).parent / 'fixtures/random_cost_roll44_cards.json').read_text())]
    for i, row in enumerate(rows):
        base[row['name']] = card(row['name'], set_code='rc44', number=str(i), **{k: v for k, v in row.items() if k != 'name'})
    settings.ensure_dirs()
    build_database(base.values(), settings.cards_db_path)
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()




def setup(cards):
    names = [r['name'] for r in [*DATA, *SUPPORT]] + ['Clay Golem', 'Grizzly Bears', 'Forest', 'Lightning Bolt']
    s = three(cards, names, names, names)
    hold(s)
    source = put(s, 'Clay Golem', 'battlefield')
    return s, source


def test_actual_paid_cost_roll_is_finalized_before_priority_and_survives_native_countering(cards, monkeypatch):
    from app.rules.mana_units import visible_pool
    from tests.test_rules_source_quality_protection import spell

    s, source = setup(cards)
    rolled = []
    def randint(rng, lo, hi):
        assert (lo, hi) == (1, 8)
        rolled.append(4)
        return 4
    monkeypatch.setattr('secrets.SystemRandom.randint', randint)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 6})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    ability = s.state.zones['stack'][-1]
    assert rolled == [4] and visible_pool(s.state, 'p1') == {}
    assert s.state.rules.stack[ability].x == 4
    assert s.state.rules.payments[s.state.rules.object_id(ability)].x == 4
    assert s.state.cards[source.id].counters.get('+1/+1', 0) == 0
    assert any(e.counter == 'roll_die' and e.amount == 4 and e.player == 'p1' for e in s.state.rules.events)
    spell(s, 'Stifle', {'U': 1}, target=[ability], player='p2')
    assert ability not in s.state.rules.stack
    assert s.state.cards[source.id].counters.get('+1/+1', 0) == 0
    assert rolled == [4]
    roundtrip(s)


@pytest.mark.parametrize('adjust', [False, True])
def test_committed_numeric_cost_pause_resumes_cold_without_repay_or_reroll(cards, monkeypatch, tmp_path, adjust):
    import subprocess
    import sys

    from app.rules.mana_units import visible_pool

    s, source = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: 4)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 6})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    assert s.state.rules.decision.resume['step'] == 'numeric_roll42'
    assert visible_pool(s.state, 'p1') == {}
    assert not s.state.rules.turn_log.rolled.get('p1', 0)
    ability = s.state.zones['stack'][-1]
    assert ability not in s.state.rules.stack
    path = tmp_path / 'paid-numeric.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.mana_units import visible_pool
from tests.test_rules_designations import roundtrip
import app.game.resolve as resolver
path,db,ability,adjust=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
resolver._rng_int=lambda *a: (_ for _ in ()).throw(AssertionError('paid die rerolled'))
def choose(ids):
 d=s.state.rules.decision
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':ids})
if adjust=='True':
 key=next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))
 choose([key])
 choose(['pay'])
 choose(['0'])
 choose(['plus'])
else:choose(['done'])
expected=5 if adjust=='True' else 4
assert s.state.rules.decision is None
assert visible_pool(s.state,'p1')=={}
assert s.state.rules.stack[ability].x==expected
assert s.state.rules.payments[s.state.rules.object_id(ability)].x==expected
assert s.state.rules.turn_log.rolled['p1']==1
assert len([e for e in s.state.rules.events if e.counter=='roll_die' and e.amount==expected])==1
assert s.state.players['p1'].life==(39 if adjust=='True' else 40)
roundtrip(s)
repo.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), ability, str(adjust)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def berserk_target(s, target):
    from tests.test_rules_designations import settle
    from tests.test_rules_random_consequences import answer
    settle(s)
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'trigger_target'
    answer(s, [target.id])


@pytest.mark.parametrize('result', [1, 8])
@pytest.mark.parametrize('doubled', [False, True])
def test_actual_monstrosity_uses_paid_result_native_counter_replacement_and_berserk_any_permanent(cards, monkeypatch, result, doubled):
    s, source = setup(cards)
    target = put(s, 'Forest', 'battlefield', 'p2')
    if doubled:
        put(s, 'Doubling Season', 'battlefield')
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: result)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 6})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    berserk_target(s, target)
    assert s.state.cards[source.id].counters['+1/+1'] == result * (2 if doubled else 1)
    assert s.state.rules.object_id(source.id) in s.state.rules.monstrous
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_already_monstrous_still_pays_and_rolls_without_second_counters_or_berserk(cards, monkeypatch):
    from app.rules.mana_units import visible_pool
    from tests.test_rules_designations import settle
    from tests.test_rules_player_protection import priority
    s, source = setup(cards)
    target = put(s, 'Forest', 'battlefield', 'p2')
    rolled = []
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: rolled.append(3) or 3)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 6})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    berserk_target(s, target)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 6})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    assert rolled == [3, 3] and visible_pool(s.state, 'p1') == {}
    settle(s)
    assert s.state.rules.decision is None and not s.state.zones['stack']
    assert s.state.cards[source.id].counters['+1/+1'] == 3
    roundtrip(s)


def test_unaffordable_activation_does_not_consume_entropy_or_create_stack_ability(cards, monkeypatch):
    from app.game.errors import ActionError
    s, source = setup(cards)
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda *args: (_ for _ in ()).throw(AssertionError('unpaid cost rolled')))
    with pytest.raises(ActionError):
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    assert not s.state.zones.get('stack')
    assert not s.state.rules.turn_log.rolled.get('p1', 0)
    roundtrip(s)


def test_native_mana_preview_cancel_does_not_spend_or_roll(cards, monkeypatch):
    from app.rules.mana_units import visible_pool
    from tests.test_rules_random_consequences import answer
    s, source = setup(cards)
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda *args: (_ for _ in ()).throw(AssertionError('cancelled cost rolled')))
    act(s, 'p1', type='set_prefs', payment='self')
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0)
    d = s.state.rules.decision
    assert d is not None and any(o.id == 'cancel' for o in d.options)
    answer(s, ['cancel'])
    assert visible_pool(s.state, 'p1') == {}
    assert not s.state.zones.get('stack')
    assert not s.state.rules.turn_log.rolled.get('p1', 0)
    roundtrip(s)


def test_multiple_pending_cost_results_and_native_copy_do_not_repay_or_reroll(cards, monkeypatch):
    from tests.test_rules_designations import settle
    from tests.test_rules_player_protection import priority
    from tests.test_rules_random_consequences import answer
    from tests.test_rules_source_quality_protection import spell
    s, source = setup(cards)
    target = put(s, 'Forest', 'battlefield', 'p2')
    outcomes = iter([2, 7])
    rolled = []
    def randint(rng, lo, hi):
        value = next(outcomes)
        rolled.append(value)
        return value
    monkeypatch.setattr('secrets.SystemRandom.randint', randint)
    for expected in [2, 7]:
        priority(s, 'p1')
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 6})
        act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
        ability = s.state.zones['stack'][-1]
        assert s.state.rules.stack[ability].x == expected
    spell(s, 'Return the Favor', {'C': 1, 'R': 2}, target=[ability], player='p2', modes=[0])
    d = s.state.rules.decision
    assert d is not None and d.resume['step'] == 'trigger_target' and d.player == 'p1'
    assert s.state.cards[source.id].counters['+1/+1'] == 7
    assert rolled == [2, 7]
    answer(s, [target.id])
    settle(s)
    assert s.state.cards[source.id].counters['+1/+1'] == 7
    assert rolled == [2, 7]
    assert s.state.rules.decision is None
    roundtrip(s)


@pytest.mark.parametrize('response', ['Flicker of Fate', 'Beast Within'])
def test_source_new_or_missing_incarnation_does_not_receive_paid_monstrosity_or_berserk(cards, monkeypatch, response):
    from tests.test_rules_source_quality_protection import spell
    s, source = setup(cards)
    rolled = []
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: rolled.append(8) or 8)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 6})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    original = s.state.rules.object_id(source.id)
    spell(s, response, {'C': 1, 'W': 1} if response == 'Flicker of Fate' else {'C': 2, 'G': 1}, target=[source.id], player='p2')
    assert s.state.rules.object_id(source.id) != original
    assert s.state.cards[source.id].counters.get('+1/+1', 0) == 0
    assert s.state.rules.object_id(source.id) not in s.state.rules.monstrous
    assert s.state.rules.decision is None and not s.state.zones.get('stack')
    assert rolled == [8]
    roundtrip(s)


def test_extra_ignored_cost_die_uses_one_final_kept_result_and_one_native_event(cards, monkeypatch):
    s, source = setup(cards)
    put(s, 'Pixie Guide', 'battlefield')
    values = iter([1, 8])
    rolled = []
    def randint(rng, lo, hi):
        value = next(values)
        rolled.append(value)
        return value
    monkeypatch.setattr('secrets.SystemRandom.randint', randint)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 6})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    ability = s.state.zones['stack'][-1]
    assert rolled == [1, 8]
    assert s.state.rules.stack[ability].x == 8
    assert s.state.rules.payments[s.state.rules.object_id(ability)].x == 8
    assert s.state.rules.turn_log.rolled['p1'] == 1
    assert [e.amount for e in s.state.rules.events if e.counter == 'roll_die'] == [8]
    roundtrip(s)


@pytest.mark.parametrize('natural,direction,final', [(1, 'minus', 0), (8, 'plus', 9)])
def test_modified_cost_result_is_not_clamped_to_die_faces_and_zero_still_becomes_monstrous(cards, monkeypatch, natural, direction, final):
    s, source = setup(cards)
    target = put(s, 'Forest', 'battlefield', 'p2')
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: natural)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 6})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[], x_value=77)
    key = next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))
    for ids in [[key], ['pay'], ['0'], [direction]]:
        d = s.state.rules.decision
        assert all(o.id != 'cancel' for o in d.options)
        act(s, d.player, type='choose', decision_id=d.id, option_ids=ids)
    ability = s.state.zones['stack'][-1]
    assert s.state.rules.stack[ability].x == final
    assert s.state.rules.payments[s.state.rules.object_id(ability)].x == final
    assert not s.state.rules.payments[s.state.rules.object_id(ability)].activation_cost_has_x
    berserk_target(s, target)
    assert s.state.cards[source.id].counters.get('+1/+1', 0) == final
    assert s.state.rules.object_id(source.id) in s.state.rules.monstrous
    assert s.state.cards[target.id].zone == 'p2:graveyard'
    roundtrip(s)


def test_actual_cost_roll_watchers_stack_above_fully_announced_ability_before_any_monstrosity(cards, monkeypatch):
    s, source = setup(cards)
    house = put(s, 'Mr. House, President and CEO', 'battlefield')
    monkeypatch.setattr('secrets.SystemRandom.randint', lambda rng, lo, hi: 7)
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 6})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    stack = list(s.state.zones['stack'])
    assert len(stack) == 2
    assert s.state.rules.stack[stack[0]].source_card == source.id
    assert s.state.rules.stack[stack[1]].source_card == house.id
    assert s.state.rules.stack[stack[0]].x == 7
    assert s.state.cards[source.id].counters.get('+1/+1', 0) == 0
    for _ in range(8):
        if stack[1] not in s.state.zones.get('stack', []):
            break
        act(s, s.state.rules.priority, type='pass_priority')
    assert stack[1] not in s.state.zones['stack'] and stack[0] in s.state.zones['stack']
    assert s.state.cards[source.id].counters.get('+1/+1', 0) == 0
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == 'p1:battlefield']
    assert sorted(c.name for c in tokens) == ['Robot', 'Treasure']
    roundtrip(s)


def test_whole_printed_canonical_gate(cards):
    from app.rules import coverage
    result = coverage.of_card_data(cards.resolve('Clay Golem'))
    assert result.level == 'FULL', result
