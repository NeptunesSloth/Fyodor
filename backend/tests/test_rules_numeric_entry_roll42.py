"""Whole printed production X-d6 entry and original receipt identity proofs."""
import pytest

from app.rules import replacements
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_numeric_roll_finalization42 import accept
from tests.test_rules_random_consequences import faces
from tests.test_rules_random_native_outcomes42 import cards as cards
from tests.test_rules_random_native_outcomes42 import setup
from tests.test_rules_source_quality_protection import spell


@pytest.mark.parametrize('x', [0, 2])
def test_actual_paid_x_spell_rolls_before_entry_and_uses_kept_sum_not_max(cards, monkeypatch, x):
    s = setup(cards)
    faces(monkeypatch, [1, 6] if x else [])
    source = spell(s, 'Neverwinter Hydra', {'C': 2 * x, 'G': 2}, x_value=x)
    if x:
        assert s.state.cards[source.id].zone == 'p1:battlefield'
        assert s.state.cards[source.id].counters['+1/+1'] == 7
    else:
        assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.rules.turn_log.rolled.get('p1', 0) == x
    assert not s.state.cards[source.id].choices
    roundtrip(s)


def test_actual_extra_die_ignored_before_sum_and_entry_counter_replacement(cards, monkeypatch):
    s = setup(cards)
    put(s, 'Pixie Guide', 'battlefield')
    put(s, 'Doubling Season', 'battlefield')
    faces(monkeypatch, [1, 2, 6])
    source = spell(s, 'Neverwinter Hydra', {'C': 4, 'G': 2}, x_value=2)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].counters['+1/+1'] == 16
    assert s.state.rules.turn_log.rolled['p1'] == 2
    roundtrip(s)


def test_actual_native_modifier_pauses_original_entry_and_total_uses_final_vector(cards, monkeypatch):
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    faces(monkeypatch, [2, 5])
    source = spell(s, 'Neverwinter Hydra', {'C': 4, 'G': 2}, x_value=2)
    assert s.state.cards[source.id].zone == 'stack'
    assert not s.state.cards[source.id].counters
    assert not s.state.rules.turn_log.rolled
    accept(s, index='1')
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].counters['+1/+1'] == 8
    assert s.state.players['p1'].life == 39
    assert s.state.rules.turn_log.rolled['p1'] == 2
    roundtrip(s)


def test_simulated_humility_removes_entry_roll_before_any_preview_or_native_move(cards, monkeypatch):
    s = setup(cards)
    put(s, 'Humility', 'battlefield')
    faces(monkeypatch, [])
    source = spell(s, 'Neverwinter Hydra', {'C': 4, 'G': 2}, x_value=2)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert not s.state.cards[source.id].counters
    assert not s.state.rules.turn_log.rolled
    roundtrip(s)


@pytest.mark.parametrize('phase', ['offer', 'paid'])
def test_isolated_stack_entry_packet_survives_fresh_process_native_modifier_choices(cards, monkeypatch, tmp_path, phase):
    import subprocess
    import sys
    from pathlib import Path

    from tests.test_rules_random_consequences import answer
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    faces(monkeypatch, [2, 5])
    source = spell(s, 'Neverwinter Hydra', {'C': 4, 'G': 2}, x_value=2)
    if phase == 'paid':
        option = next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))
        answer(s, [option])
        answer(s, ['pay'])
    assert s.state.cards[source.id].zone == 'stack'
    assert not s.state.rules.turn_log.rolled
    path = tmp_path / (phase + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path,db,phase,cid=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
importlib.import_module('app.game.resolve')._rng_int=lambda *a: (_ for _ in ()).throw(AssertionError('entry rerolled'))
def choose(ids):
 d=s.state.rules.decision
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':ids})
if phase=='offer':
 choose([next(o.id for o in s.state.rules.decision.options if o.id.startswith('roll_adjust42:'))])
 choose(['pay'])
assert s.state.cards[cid].zone=='stack'
assert not s.state.rules.turn_log.rolled
choose(['1']);choose(['plus'])
for _ in range(40):
 if not s.state.zones.get('stack'):break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.cards[cid].zone=='p1:battlefield'
assert s.state.cards[cid].counters['+1/+1']==8
assert not s.state.cards[cid].choices
assert s.state.players['p1'].life==39
assert s.state.rules.turn_log.rolled['p1']==2
assert len([c for c in s.state.cards.values() if c.is_token])==1
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), phase, source.id], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_repeated_native_entry_previews_never_collect_private_raw_rolls(cards, monkeypatch):
    from app.rules.plan import Plan
    from tests.test_rules_designations import settle
    s = setup(cards)
    source = spell(s, 'Neverwinter Hydra', {'C': 4, 'G': 2}, x_value=2, finish=False)
    faces(monkeypatch, [])
    plan = Plan(s.state, 'p1', cards, None)
    for _ in range(3):
        replacements.entry_plan(plan, s.state.cards[source.id], 'p1')
    assert not s.state.rules.turn_log.rolled
    assert 'numeric_entry42_total' not in s.state.rules.entry_choices.get(source.id, {})
    faces(monkeypatch, [1, 6])
    settle(s)
    assert s.state.cards[source.id].counters['+1/+1'] == 7
    roundtrip(s)


@pytest.mark.parametrize('first,expected', [('Doubling Season', 7), ('Winding Constrictor', 8)])
def test_actual_entry_sum_waits_native_counter_replacement_order_before_birth(cards, monkeypatch, first, expected):
    from tests.test_rules_random_consequences import answer
    s = setup(cards)
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Winding Constrictor', 'battlefield')
    faces(monkeypatch, [3])
    source = spell(s, 'Neverwinter Hydra', {'C': 2, 'G': 2}, x_value=1)
    assert s.state.cards[source.id].zone == 'stack'
    assert s.state.rules.turn_log.rolled['p1'] == 1
    assert not s.state.cards[source.id].counters
    d = s.state.rules.decision
    assert d is not None
    option = next(o.id for o in d.options if first in o.label)
    answer(s, [option])
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.cards[source.id].counters['+1/+1'] == expected
    assert s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


def test_actual_reanimate_put_is_x_zero_no_roll_and_native_zero_toughness_sba(cards, monkeypatch):
    s = setup(cards)
    source = put(s, 'Neverwinter Hydra', 'graveyard')
    faces(monkeypatch, [])
    spell(s, 'Reanimate', {'B': 1}, target=[source.id])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.players['p1'].life == 38
    assert not s.state.rules.turn_log.rolled
    roundtrip(s)


def test_native_flicker_of_previously_cast_hydra_does_not_reuse_old_cast_x_or_counters(cards, monkeypatch):
    s = setup(cards)
    faces(monkeypatch, [1, 6])
    source = spell(s, 'Neverwinter Hydra', {'C': 4, 'G': 2}, x_value=2)
    assert s.state.cards[source.id].counters['+1/+1'] == 7
    faces(monkeypatch, [])
    spell(s, 'Cloudshift', {'W': 1}, target=[source.id])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert not s.state.cards[source.id].counters
    assert s.state.rules.turn_log.rolled['p1'] == 2
    roundtrip(s)


def test_actual_clone_entry_has_its_own_zero_x_and_never_copies_counters(cards, monkeypatch):
    from tests.test_rules_random_consequences import answer
    s = setup(cards)
    faces(monkeypatch, [1, 6])
    source = spell(s, 'Neverwinter Hydra', {'C': 4, 'G': 2}, x_value=2)
    faces(monkeypatch, [])
    clone = spell(s, 'Clone', {'C': 3, 'U': 1})
    answer(s, [source.id])
    assert s.state.cards[clone.id].zone == 'p1:graveyard'
    assert s.state.cards[source.id].counters['+1/+1'] == 7
    assert s.state.rules.turn_log.rolled['p1'] == 2
    roundtrip(s)


def test_actual_cackling_token_copy_has_zero_x_no_roll_and_native_sba(cards, monkeypatch):
    s = setup(cards)
    faces(monkeypatch, [1, 6])
    source = spell(s, 'Neverwinter Hydra', {'C': 4, 'G': 2}, x_value=2)
    faces(monkeypatch, [])
    spell(s, 'Cackling Counterpart', {'C': 1, 'U': 2}, target=[source.id])
    assert s.state.cards[source.id].counters['+1/+1'] == 7
    assert not [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(':battlefield')]
    assert s.state.rules.turn_log.rolled['p1'] == 2
    roundtrip(s)


def test_actual_lithoform_permanent_spell_copy_retains_paid_x_two_and_rolls_separately(cards, monkeypatch):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle
    from tests.test_rules_player_protection import priority
    s = setup(cards)
    engine = put(s, 'Lithoform Engine', 'battlefield')
    faces(monkeypatch, [1, 2, 4, 5])
    source = spell(s, 'Neverwinter Hydra', {'C': 4, 'G': 2}, x_value=2, finish=False)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    act(s, 'p1', type='activate_ability', card_id=engine.id, ability=2, targets=[source.id], sources=[])
    settle(s)
    assert s.state.cards[source.id].counters['+1/+1'] == 9
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone.endswith(':battlefield')]
    assert len(tokens) == 1 and tokens[0].counters['+1/+1'] == 3
    assert s.state.rules.turn_log.rolled['p1'] == 4
    roundtrip(s)


def test_saved_native_counter_order_after_original_roll_keeps_receipt_and_never_rerolls(cards, monkeypatch, tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    s = setup(cards)
    put(s, 'Doubling Season', 'battlefield')
    put(s, 'Winding Constrictor', 'battlefield')
    faces(monkeypatch, [3])
    source = spell(s, 'Neverwinter Hydra', {'C': 2, 'G': 2}, x_value=1)
    assert s.state.cards[source.id].zone == 'stack'
    assert s.state.rules.turn_log.rolled['p1'] == 1
    path = tmp_path / 'counter-order.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path,db,cid=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
importlib.import_module('app.game.resolve')._rng_int=lambda *a: (_ for _ in ()).throw(AssertionError('entry resampled'))
d=s.state.rules.decision
choice=next(o.id for o in d.options if 'Winding Constrictor' in o.label)
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[choice]})
for _ in range(40):
 if not s.state.zones.get('stack'):break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.cards[cid].zone=='p1:battlefield'
assert s.state.cards[cid].counters['+1/+1']==8
assert s.state.rules.turn_log.rolled['p1']==1
assert not s.state.cards[cid].choices
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), source.id], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('pay', [False, True])
def test_actual_printed_ward_four_uses_opponents_native_payment_and_counters_only_on_refusal(cards, monkeypatch, pay):
    from app.rules.mana_units import visible_pool
    from tests.test_rules_random_consequences import answer
    s = setup(cards)
    faces(monkeypatch, [1, 6])
    source = spell(s, 'Neverwinter Hydra', {'C': 4, 'G': 2}, x_value=2)
    bolt = spell(s, 'Lightning Bolt', {'C': 4, 'R': 1}, target=[source.id], player='p2')
    assert s.state.rules.decision.player == 'p2'
    assert {o.id for o in s.state.rules.decision.options} == {'pay', 'decline'}
    answer(s, ['pay' if pay else 'decline'])
    assert s.state.cards[source.id].damage == (3 if pay else 0)
    assert s.state.cards[bolt.id].zone == 'p2:graveyard'
    assert visible_pool(s.state, 'p2') == ({} if pay else {'C': 4})
    roundtrip(s)


def test_actual_printed_trample_assigns_lethal_to_native_blocker_and_excess_to_defender(cards, monkeypatch):
    from tests.game_helpers import act
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    faces(monkeypatch, [1, 6])
    source = spell(s, 'Neverwinter Hydra', {'C': 4, 'G': 2}, x_value=2)
    blocker = put(s, 'Grizzly Bears', 'battlefield', 'p2')
    to_phase(s, 'declare_attackers', turn=4)
    act(s, 'p1', type='declare_attackers', attackers=[{'card_id': source.id, 'target': 'p2'}])
    to_phase(s, 'declare_blockers', turn=4)
    act(s, 'p2', type='declare_blockers', blocks=[{'blocker_id': blocker.id, 'attacker_id': source.id}])
    for _ in range(15):
        d = s.state.rules.decision
        if d is not None:
            assert d.kind == 'divide' and d.player == 'p1'
            break
        act(s, s.state.rules.priority, type='pass_priority')
    else:
        raise AssertionError('No native trample division')
    act(s, 'p1', type='choose', decision_id=d.id, amounts=[2, 5])
    assert s.state.players['p2'].life == 35
    assert s.state.cards[blocker.id].zone == 'p2:graveyard'
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_neverwinter_hydra_whole_printed_canonical_gate(cards):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve('Neverwinter Hydra')).level == 'FULL'
