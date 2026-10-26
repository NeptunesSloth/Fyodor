"""Production numeric-finalization prerequisites; no whole-card admission count."""
import pytest

from app.rules import effects
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import priority
from tests.test_rules_random_consequences import answer, faces
from tests.test_rules_random_native_outcomes42 import cards as cards
from tests.test_rules_random_native_outcomes42 import setup
from tests.test_rules_source_quality_protection import spell


def activate_troll(s):
    source = put(s, 'Loathsome Troll', 'graveyard')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 3, 'G': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    settle(s)
    return source


def uncounted(s):
    assert not s.state.rules.turn_log.rolled.get('p1', 0)
    assert not [c for c in s.state.cards.values() if c.is_token]


def accept(s, index='0', direction='plus'):
    d = s.state.rules.decision
    option = next(o.id for o in d.options if o.id.startswith('roll_adjust42:'))
    answer(s, [option])
    answer(s, ['pay'])
    answer(s, [index])
    answer(s, [direction])


@pytest.mark.parametrize('natural,direction,zombies', [(5, 'plus', 1), (6, 'minus', 0)])
def test_real_raw_action_waits_for_native_life_payment_and_final_result_before_count_or_trigger(cards, monkeypatch, natural, direction, zombies):
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    faces(monkeypatch, [natural])
    activate_troll(s)
    uncounted(s)
    option = next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))
    answer(s, [option])
    uncounted(s)
    answer(s, ['pay'])
    assert s.state.players['p1'].life == 39
    uncounted(s)
    answer(s, ['0'])
    uncounted(s)
    answer(s, [direction])
    assert s.state.rules.turn_log.rolled['p1'] == 1
    actual = [c for c in s.state.cards.values() if c.is_token and 'Employee' in Plan(s.state, 'p1', cards, None).ch(c).subtypes]
    assert len(actual) == zombies
    assert all(Plan(s.state, 'p1', cards, None).ch(c).pt == (2, 2) for c in actual)
    roundtrip(s)


def test_declining_native_cost_does_not_consume_once_accepted_use(cards, monkeypatch):
    s = setup(cards)
    source = put(s, 'Night Shift of the Living Dead', 'battlefield')
    faces(monkeypatch, [5, 5])
    activate_troll(s)
    option = next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))
    answer(s, [option])
    answer(s, ['decline'])
    assert s.state.players['p1'].life == 40
    assert not any(source.id in k for k in s.state.rules.once_per_turn)
    activate_troll(s)
    accept(s)
    assert s.state.players['p1'].life == 39
    assert s.state.rules.turn_log.rolled['p1'] == 2
    roundtrip(s)


def test_one_paid_adjustment_selects_one_of_two_dice_before_native_choice_and_entry(cards, monkeypatch):
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    target = put(s, 'Grizzly Bears', 'graveyard')
    faces(monkeypatch, [2, 5])
    spell(s, 'Grave Endeavor', {'C': 5, 'B': 2})
    uncounted(s)
    accept(s, index='1')
    assert s.state.rules.decision.resume['step'] == 'roll_choose'
    assert s.state.rules.turn_log.rolled['p1'] == 2
    answer(s, ['0'])
    assert s.state.cards[target.id].counters['+1/+1'] == 2
    assert s.state.players['p1'].life == 45  # paid1, gainedOTHER6 once
    assert s.state.players['p2'].life == s.state.players['p3'].life == 34
    roundtrip(s)


@pytest.mark.parametrize('phase', ['pay', 'die', 'direction'])
def test_isolated_numeric_packet_native_payment_resumes_fresh_without_raw_driver(cards, monkeypatch, tmp_path, phase):
    import subprocess
    import sys
    from pathlib import Path
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    faces(monkeypatch, [5])
    activate_troll(s)
    option = next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))
    answer(s, [option])
    if phase != 'pay':
        answer(s, ['pay'])
    if phase == 'direction':
        answer(s, ['0'])
    uncounted(s)
    path = tmp_path / (phase + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path, db, phase = sys.argv[1:]
repo = CardRepository(Path(db), ImageStore(Path(db).parent / 'images'))
s = GameSession(GameState.model_validate_json(Path(path).read_text()), cards=repo)
s.view('p3')
importlib.import_module('app.game.resolve')._rng_int = lambda *args: (_ for _ in ()).throw(AssertionError('raw die rolled twice'))
def choose(ids):
 d=s.state.rules.decision
 assert d is not None
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':ids})
assert not s.state.rules.turn_log.rolled.get('p1',0)
if phase == 'pay':choose(['pay'])
assert s.state.players['p1'].life==39
assert any(k.startswith('roll_adjust42:') and v==s.state.turn.number for k,v in s.state.rules.once_per_turn.items())
assert not s.state.rules.turn_log.rolled.get('p1',0)
if phase != 'direction':choose(['0'])
assert not s.state.rules.turn_log.rolled.get('p1',0)
choose(['plus'])
for _ in range(40):
 if not s.state.zones.get('stack'):break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority, {'type':'pass_priority'})
assert s.state.rules.turn_log.rolled['p1']==1
assert len([c for c in s.state.cards.values() if c.is_token])==1
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), phase], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('printed_first', [False, True])
def test_printed_modifier_reads_live_operand_in_original_rollers_chosen_order(cards, monkeypatch, printed_first):
    # Isolated existing native modifier descriptor; not a fictional card admission.
    original = effects.PRIMITIVES['roll']
    def with_life_modifier(plan, ctx, effect):
        return original(plan, ctx, {**effect, 'mod': {'op': '+', 'v': {'life': 'you'}}})
    monkeypatch.setitem(effects.PRIMITIVES, 'roll', with_life_modifier)
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    target = put(s, 'Grizzly Bears', 'graveyard')
    act(s, 'p1', type='life', player='p1', delta=-37)
    faces(monkeypatch, [2, 5])
    spell(s, 'Grave Endeavor', {'C': 5, 'B': 2})
    if printed_first:
        answer(s, ['printed'])
    uncounted(s)
    accept(s, index='1')
    answer(s, ['0'])
    assert s.state.cards[target.id].counters['+1/+1'] == (5 if printed_first else 4)
    assert s.state.players['p1'].life == (11 if printed_first else 10)
    assert s.state.players['p2'].life == s.state.players['p3'].life == (31 if printed_first else 32)
    roundtrip(s)


def test_accepted_cost_consumes_this_sources_use_before_another_roll_same_turn(cards, monkeypatch):
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    faces(monkeypatch, [5, 5])
    activate_troll(s)
    accept(s)
    activate_troll(s)
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life == 39
    assert s.state.rules.turn_log.rolled['p1'] == 2
    assert len([c for c in s.state.cards.values() if c.is_token]) == 1
    roundtrip(s)


def test_paid_life_can_reach_zero_while_original_roll_remains_unpublished_and_resolving(cards, monkeypatch):
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    act(s, 'p1', type='life', player='p1', delta=-39)
    faces(monkeypatch, [5])
    activate_troll(s)
    option = next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))
    answer(s, [option])
    answer(s, ['pay'])
    assert s.state.players['p1'].life == 0
    assert 'p1' in Plan(s.state, 'p1', cards, None).live()
    uncounted(s)
    assert s.state.rules.decision.resume['phase'] == 'die'
    roundtrip(s)


def test_opponents_adjustment_source_does_not_offer_for_our_roll(cards, monkeypatch):
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield', 'p2')
    faces(monkeypatch, [5])
    activate_troll(s)
    assert s.state.rules.decision is None
    assert s.state.rules.turn_log.rolled['p1'] == 1
    assert s.state.players['p1'].life == s.state.players['p2'].life == 40
    roundtrip(s)


def test_accepted_source_use_resets_on_native_next_turn(cards, monkeypatch):
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    faces(monkeypatch, [5, 5])
    activate_troll(s)
    accept(s)
    to_phase(s, 'main1', turn=4)
    activate_troll(s)
    accept(s)
    assert s.state.players['p1'].life == 38
    assert s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


@pytest.mark.parametrize('phase', ['offer', 'die', 'direction'])
def test_saved_source_control_is_revalidated_at_each_native_choice(cards, monkeypatch, phase):
    s = setup(cards)
    source = put(s, 'Night Shift of the Living Dead', 'battlefield')
    faces(monkeypatch, [5])
    activate_troll(s)
    option = next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))
    if phase != 'offer':
        answer(s, [option])
        answer(s, ['pay'])
    if phase == 'direction':
        answer(s, ['0'])
    act(s, 'p1', type='set_controller', card_ids=[source.id], player='p2')
    answer(s, [option if phase == 'offer' else '0' if phase == 'die' else 'plus'])
    assert s.state.rules.decision is None
    assert s.state.rules.turn_log.rolled['p1'] == 1
    assert not [c for c in s.state.cards.values() if c.is_token]
    assert s.state.players['p1'].life == (40 if phase == 'offer' else 39)
    roundtrip(s)


def test_manual_modifier_source_never_offers_an_automatic_payment(cards, monkeypatch):
    s = setup(cards)
    source = put(s, 'Night Shift of the Living Dead', 'battlefield')
    s.state.rules.card_modes[source.id] = 'manual'
    faces(monkeypatch, [5])
    activate_troll(s)
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life == 40
    assert s.state.rules.turn_log.rolled['p1'] == 1


def test_production_adjustment_then_801_kept_dice_emission_resumes_cold_once(cards, monkeypatch, tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    original = effects.PRIMITIVES['roll']
    # Isolated group-size descriptor, through the unchanged native raw collector.
    def many(plan, ctx, effect):
        return original(plan, ctx, {**effect, 'count': 801})
    monkeypatch.setitem(effects.PRIMITIVES, 'roll', many)
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    faces(monkeypatch, [5] * 801)
    activate_troll(s)
    d = s.state.rules.decision
    assert d.resume['step'] == 'roll_group_continue' and len(d.resume['results']) == 800
    uncounted(s)
    answer(s, ['continue'])
    uncounted(s)
    accept(s, index='800')
    d = s.state.rules.decision
    assert d.resume['step'] == 'roll_group_continue' and d.resume['phase'] == 'emit'
    assert d.resume['start'] == 800 and d.resume['results'][-1] == 6
    assert s.state.rules.turn_log.rolled['p1'] == 801
    retained = [e.nth for e in s.state.rules.events if e.counter == 'roll_die']
    assert len(retained) == 500 and max(retained) == 800 and len(set(retained)) == len(retained)
    path = tmp_path / 'emit801.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib, sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
repo=CardRepository(Path(sys.argv[2]), ImageStore(Path(sys.argv[2]).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(sys.argv[1]).read_text()),cards=repo)
importlib.import_module('app.game.resolve')._rng_int=lambda *a: (_ for _ in ()).throw(AssertionError('rerolled'))
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['continue']})
for _ in range(50):
 if not s.state.zones.get('stack'):break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.rules.turn_log.rolled['p1']==801
assert s.state.players['p1'].life==39
assert len([c for c in s.state.cards.values() if c.is_token])==1
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path)], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_native_unpayable_life_cost_does_not_consume_adjustment_use(cards, monkeypatch):
    s = setup(cards)
    source = put(s, 'Night Shift of the Living Dead', 'battlefield')
    put(s, 'Platinum Emperion', 'battlefield')
    faces(monkeypatch, [5])
    activate_troll(s)
    option = next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))
    answer(s, [option])
    if s.state.rules.decision is not None:
        assert [o.id for o in s.state.rules.decision.options] == ['decline']
        answer(s, ['decline'])
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life == 40
    assert s.state.rules.turn_log.rolled['p1'] == 1
    assert not any(k.startswith('roll_adjust42:') for k in s.state.rules.once_per_turn)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_two_actual_modifier_sources_apply_separately_before_any_six_trigger(cards, monkeypatch):
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    act(s, 'p1', type='create_token', player='p1', count=1, stacked=False,
        token={'name': 'Night Shift of the Living Dead', 'type_line': 'Token Enchantment',
               'text': cards.resolve('Night Shift of the Living Dead')['oracle_text']})
    faces(monkeypatch, [5])
    activate_troll(s)
    assert len([o for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:')]) == 2
    accept(s)
    assert not s.state.rules.turn_log.rolled.get('p1', 0)
    assert len([c for c in s.state.cards.values() if c.is_token]) == 1
    accept(s)
    assert s.state.rules.decision is None
    assert s.state.players['p1'].life == 38
    assert len([k for k in s.state.rules.once_per_turn if k.startswith('roll_adjust42:')]) == 2
    assert s.state.rules.turn_log.rolled['p1'] == 1
    assert not [c for c in s.state.cards.values() if c.is_token and c.token.type_line != 'Token Enchantment']
    roundtrip(s)


def test_final_six_trigger_occurs_for_each_actual_kept_die(cards, monkeypatch):
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    faces(monkeypatch, [6, 6])
    spell(s, 'Grave Endeavor', {'C': 5, 'B': 2})
    answer(s, ['done'])
    settle(s)
    assert s.state.rules.turn_log.rolled['p1'] == 2
    assert len([c for c in s.state.cards.values() if c.is_token]) == 2
    assert all(Plan(s.state, 'p1', cards, None).ch(c).pt == (2, 2) for c in s.state.cards.values() if c.is_token)
    assert s.state.players['p1'].life == 46
    roundtrip(s)


def test_ignored_natural_six_never_qualifies_as_a_kept_six(cards, monkeypatch):
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    put(s, 'Pixie Guide', 'battlefield')
    faces(monkeypatch, [6, 7])
    activate_troll(s)
    answer(s, ['done'])
    assert s.state.rules.turn_log.rolled['p1'] == 1
    assert not [c for c in s.state.cards.values() if c.is_token]
    roundtrip(s)


def test_night_shift_is_full_because_commander_has_no_planar_die(cards):
    """CR 901 (Planechase) owns the planar die; a Commander game has none, so every die Night Shift can adjust is a numeric one (wave 110B; the accepted-use rule is tested above)."""
    from app.rules import coverage
    got = coverage.of_card_data(cards.resolve('Night Shift of the Living Dead'))
    assert got.level == 'FULL'
