"""Whole printed production artifact tables, entry receipts and delayed owner loss."""
import pytest

from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_player_protection import priority
from tests.test_rules_random_consequences import answer, faces
from tests.test_rules_random_native_outcomes42 import cards as cards
from tests.test_rules_random_native_outcomes42 import setup


def deck_ready(s):
    source = put(s, 'The Deck of Many Things', 'battlefield')
    hand = list(s.state.zones['p1:hand'])
    if hand:
        act(s, 'p1', type='move', card_ids=hand, to={'player': 'p1', 'zone': 'library'})
    return source


def activate(s, source):
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    settle(s)


@pytest.mark.parametrize('natural,hand', [(1, 1), (1, 2)])
def test_actual_modified_nonpositive_result_discards_whole_hand_after_paid_activation(cards, monkeypatch, natural, hand):
    s = setup(cards)
    source = deck_ready(s)
    cards_in_hand = [put(s, n, 'hand') for n in ['Forest', 'Grizzly Bears'][:hand]]
    faces(monkeypatch, [natural])
    activate(s, source)
    assert s.state.cards[source.id].tapped
    assert all(s.state.cards[c.id].zone == 'p1:graveyard' for c in cards_in_hand)
    assert not s.state.zones['p1:hand']
    assert s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


@pytest.mark.parametrize('natural', [1, 9])
def test_native_random_graveyard_return_once_without_target_or_user_choice(cards, monkeypatch, natural):
    s = setup(cards)
    source = deck_ready(s)
    selected = put(s, 'Grizzly Bears', 'graveyard')
    other = put(s, 'Forest', 'graveyard')
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert selected.id in pool and other.id in pool
        return selected.id
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    faces(monkeypatch, [natural])
    activate(s, source)
    assert len(sampled) == 1
    assert s.state.rules.decision is None
    assert s.state.cards[selected.id].zone == 'p1:hand'
    assert s.state.cards[other.id].zone == 'p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('natural', [10, 19])
def test_native_draw_two_uses_each_table_boundary(cards, monkeypatch, natural):
    s = setup(cards)
    source = deck_ready(s)
    faces(monkeypatch, [natural])
    activate(s, source)
    assert len(s.state.zones['p1:hand']) == 2
    assert s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


def test_native_twenty_entry_any_graveyard_and_eventual_owner_loss(cards, monkeypatch):
    from app.rules.plan import Plan
    from tests.test_rules_source_quality_protection import spell
    s = setup(cards)
    source = deck_ready(s)
    chosen = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    put(s, 'Forest', 'graveyard', 'p3')
    faces(monkeypatch, [20])
    activate(s, source)
    if s.state.rules.decision is not None:
        answer(s, [chosen.id])
    assert s.state.cards[chosen.id].zone == 'p1:battlefield'
    assert s.state.cards[chosen.id].controller == 'p1' and s.state.cards[chosen.id].owner == 'p2'
    assert len(s.state.rules.delayed) == 1
    spell(s, 'Lightning Bolt', {'R': 1}, target=[chosen.id])
    assert 'p2' not in Plan(s.state, 'p1', cards, None).live()
    assert 'p1' in Plan(s.state, 'p1', cards, None).live()
    assert not s.state.rules.delayed
    roundtrip(s)


def chosen_creature(s, monkeypatch):
    source = deck_ready(s)
    chosen = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    faces(monkeypatch, [20])
    activate(s, source)
    if s.state.rules.decision is not None:
        answer(s, [chosen.id])
    assert len(s.state.rules.delayed) == 1
    return source, chosen


def test_actual_native_blink_removes_only_old_oid_watcher_and_new_object_can_die_safely(cards, monkeypatch):
    from app.rules.plan import Plan
    from tests.test_rules_source_quality_protection import spell
    s = setup(cards)
    source, chosen = chosen_creature(s, monkeypatch)
    old = Plan(s.state, 'p1', cards, None).oid(s.state.cards[chosen.id])
    spell(s, 'Cloudshift', {'W': 1}, target=[chosen.id])
    assert Plan(s.state, 'p1', cards, None).oid(s.state.cards[chosen.id]) != old
    assert not s.state.rules.delayed
    assert not s.state.zones.get('stack')
    spell(s, 'Lightning Bolt', {'R': 1}, target=[chosen.id])
    assert 'p2' in Plan(s.state, 'p1', cards, None).live()
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    roundtrip(s)


def test_actual_rip_death_replacement_exiles_without_owner_loss_or_stale_watcher(cards, monkeypatch):
    from app.rules.plan import Plan
    from tests.test_rules_source_quality_protection import spell
    s = setup(cards)
    _, chosen = chosen_creature(s, monkeypatch)
    put(s, 'Rest in Peace', 'battlefield')
    spell(s, 'Lightning Bolt', {'R': 1}, target=[chosen.id])
    assert s.state.cards[chosen.id].zone == 'p2:exile'
    assert 'p2' in Plan(s.state, 'p1', cards, None).live()
    assert not s.state.rules.delayed
    roundtrip(s)


def test_same_native_watcher_without_opt_in_is_not_removed_by_new_cleanup(cards, monkeypatch):
    from tests.test_rules_source_quality_protection import spell
    s = setup(cards)
    _, chosen = chosen_creature(s, monkeypatch)
    spell(s, 'Graceful Reprieve', {'C': 1, 'W': 1}, target=[chosen.id])
    assert len(s.state.rules.delayed) == 2
    watch = next(w for w in s.state.rules.delayed if not w.when.get('forget_on_departure'))
    spell(s, 'Cloudshift', {'W': 1}, target=[chosen.id])
    assert [w.id for w in s.state.rules.delayed] == [watch.id]
    roundtrip(s)


def test_copied_native_twenty_abilities_keep_two_distinct_entry_watchers_and_blink_only_one(cards, monkeypatch):
    from app.rules.plan import Plan
    from tests.test_rules_source_quality_protection import spell
    s = setup(cards)
    engine = put(s, 'Lithoform Engine', 'battlefield')
    source = deck_ready(s)
    one = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    two = put(s, 'Grizzly Bears', 'graveyard', 'p3')
    faces(monkeypatch, [20, 20])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    target = s.state.zones['stack'][-1]
    act(s, 'p1', type='activate_ability', card_id=engine.id, ability=0, targets=[target], sources=[])
    settle(s)
    answer(s, [one.id])
    assert len(s.state.rules.delayed) == 2
    assert s.state.cards[one.id].zone == s.state.cards[two.id].zone == 'p1:battlefield'
    spell(s, 'Cloudshift', {'W': 1}, target=[one.id])
    assert len(s.state.rules.delayed) == 1
    spell(s, 'Lightning Bolt', {'R': 1}, target=[two.id])
    assert 'p3' not in Plan(s.state, 'p1', cards, None).live()
    assert 'p2' in Plan(s.state, 'p1', cards, None).live()
    assert not s.state.rules.delayed
    spell(s, 'Lightning Bolt', {'R': 1}, target=[one.id])
    assert 'p2' in Plan(s.state, 'p1', cards, None).live()
    roundtrip(s)


def test_zero_toughness_native_entry_installs_watcher_before_sba_death(cards, monkeypatch):
    from app.rules.plan import Plan
    s = setup(cards)
    source = deck_ready(s)
    chosen = put(s, 'Stonecoil Serpent', 'graveyard', 'p2')
    faces(monkeypatch, [20])
    activate(s, source)
    if s.state.rules.decision is not None:
        answer(s, [chosen.id])
    assert 'p2' not in Plan(s.state, 'p1', cards, None).live()
    assert not s.state.rules.delayed
    roundtrip(s)


def test_printed_hand_subtraction_reads_actual_resolution_hand_after_response_draw(cards, monkeypatch):
    s = setup(cards)
    source = deck_ready(s)
    response = put(s, 'Quick Study', 'hand')
    selected = put(s, 'Forest', 'graveyard')
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        return selected.id
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    faces(monkeypatch, [11])
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 4, 'U': 1})
    act(s, 'p1', type='activate_ability', card_id=source.id, ability=0, sources=[])
    act(s, 'p1', type='cast_spell', card_id=response.id)
    settle(s)
    assert len(sampled) == 1  # actual hand2 gives9; announcement hand1 would give10/draw.
    assert s.state.cards[selected.id].zone == 'p1:hand'
    assert len(s.state.zones['p1:hand']) == 3
    assert s.state.cards[source.id].tapped
    roundtrip(s)


@pytest.mark.parametrize('natural,final', [(19, 20), (20, 21)])
def test_native_night_modifier_changes_twenty_row_and_outside_table_is_no_effect(cards, monkeypatch, natural, final):
    from tests.test_rules_numeric_roll_finalization42 import accept
    s = setup(cards)
    source = deck_ready(s)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    chosen = put(s, 'Grizzly Bears', 'graveyard', 'p2')
    faces(monkeypatch, [natural])
    activate(s, source)
    accept(s)
    if final == 20:
        if s.state.rules.decision is not None:
            answer(s, [chosen.id])
        assert s.state.cards[chosen.id].zone == 'p1:battlefield'
        assert len(s.state.rules.delayed) == 1
    else:
        assert s.state.cards[chosen.id].zone == 'p2:graveyard'
        assert not s.state.rules.delayed
        assert not s.state.zones['p1:hand']
    assert s.state.players['p1'].life == 39
    assert s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


def test_delayed_owner_loss_survives_actual_original_deck_destruction(cards, monkeypatch):
    from app.rules.plan import Plan
    from tests.test_rules_source_quality_protection import spell
    s = setup(cards)
    source, chosen = chosen_creature(s, monkeypatch)
    spell(s, 'Disenchant', {'C': 1, 'W': 1}, target=[source.id])
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    spell(s, 'Lightning Bolt', {'R': 1}, target=[chosen.id])
    assert 'p2' not in Plan(s.state, 'p1', cards, None).live()
    assert not s.state.rules.delayed
    roundtrip(s)


@pytest.mark.parametrize('answer_id,zone', [('no', 'hand'), ('yes', 'command')])
def test_saved_random_commander_selection_survives_native903_without_resampling(cards, monkeypatch, tmp_path, answer_id, zone):
    import subprocess
    import sys
    from pathlib import Path

    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    commander = next(c for c in s.state.cards.values() if c.owner == 'p1' and c.commander_key)
    act(s, 'p1', type='move', card_ids=[commander.id], to={'player': 'p1', 'zone': 'graveyard'})
    act(s, s.state.rules.priority, type='pass_priority')
    if s.state.rules.decision is not None:
        answer(s, ['no'])
    to_phase(s, 'main1', turn=4)
    source = deck_ready(s)
    put(s, 'Forest', 'graveyard')
    sampled = []
    def choose(rng, pool):
        sampled.append(tuple(pool))
        assert commander.id in pool
        return commander.id
    monkeypatch.setattr('secrets.SystemRandom.choice', choose)
    faces(monkeypatch, [1])
    activate(s, source)
    assert len(sampled) == 1
    assert s.state.rules.decision.resume['step'] == 'commander_first'
    path = tmp_path / (zone + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib,secrets,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path,db,choice,zone,cid=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
secrets.SystemRandom.choice=lambda *a: (_ for _ in ()).throw(AssertionError('commander resampled'))
importlib.import_module('app.game.resolve')._rng_int=lambda *a: (_ for _ in ()).throw(AssertionError('die rerolled'))
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':[choice]})
for _ in range(30):
 if not s.state.zones.get('stack'):break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.cards[cid].zone=='p1:'+zone
assert s.state.rules.turn_log.rolled['p1']==1
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), answer_id, zone, commander.id], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_saved_native_entry_choice_then_exact_new_oid_watcher_completes_and_owner_loses(cards, monkeypatch, tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    s = setup(cards)
    source = deck_ready(s)
    chosen = put(s, 'True-Name Nemesis', 'graveyard', 'p2')
    faces(monkeypatch, [20])
    activate(s, source)
    assert s.state.rules.decision.resume['step'] == 'enter_choice'
    path = tmp_path / 'entry.json'
    path.write_text(s.state.model_dump_json())
    code = r'''
import importlib,secrets,sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
from app.rules.plan import Plan
path,db,cid=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
secrets.SystemRandom.choice=lambda *a: (_ for _ in ()).throw(AssertionError('resampled'))
importlib.import_module('app.game.resolve')._rng_int=lambda *a: (_ for _ in ()).throw(AssertionError('rerolled'))
d=s.state.rules.decision
s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['p3']})
for _ in range(30):
 if not s.state.zones.get('stack'):break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.cards[cid].zone=='p1:battlefield'
assert len(s.state.rules.delayed)==1
watch=s.state.rules.delayed[0]
assert watch.refs['watch']['objects'][0]['object_id']==Plan(s.state,'p1',repo,None).oid(s.state.cards[cid])
assert s.state.rules.turn_log.rolled['p1']==1
while s.state.rules.priority!='p1':s.perform(s.state.rules.priority,{'type':'pass_priority'})
bolt=next(c for c in s.state.cards.values() if c.name=='Lightning Bolt' and c.owner=='p1')
s.perform('p1',{'type':'move','card_ids':[bolt.id],'to':{'player':'p1','zone':'hand'}})
bolt=next(c for c in s.state.cards.values() if c.name=='Lightning Bolt' and c.owner=='p1' and c.zone=='p1:hand')
s.perform('p1',{'type':'add_mana','player':'p1','mana':{'R':1}})
s.perform('p1',{'type':'cast_spell','card_id':bolt.id,'targets':[cid]})
for _ in range(45):
 if not s.state.zones.get('stack'):break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert 'p2' not in Plan(s.state,'p1',repo,None).live()
assert not s.state.rules.delayed
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), chosen.id], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('natural', [1, 20])
def test_empty_eligible_zones_leave_native_table_actions_empty_without_random_choice(cards, monkeypatch, natural):
    s = setup(cards)
    source = deck_ready(s)
    faces(monkeypatch, [natural])
    monkeypatch.setattr('secrets.SystemRandom.choice', lambda *args: (_ for _ in ()).throw(AssertionError('empty pool sampled')))
    activate(s, source)
    assert s.state.rules.decision is None
    assert not s.state.rules.delayed
    assert not s.state.zones['p1:hand']
    assert s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


def test_actual_draw_replacement_uses_native_notion_thief_for_both_cards(cards, monkeypatch):
    s = setup(cards)
    source = deck_ready(s)
    put(s, 'Notion Thief', 'battlefield', 'p2')
    before = len(s.state.zones['p2:hand'])
    faces(monkeypatch, [10])
    activate(s, source)
    assert not s.state.zones['p1:hand']
    assert len(s.state.zones['p2:hand']) == before + 2
    roundtrip(s)


def test_native_discard_replacement_gets_actual_nonpositive_table_hand(cards, monkeypatch):
    s = setup(cards)
    source = deck_ready(s)
    put(s, 'Rest in Peace', 'battlefield')
    chosen = put(s, 'Progenitus', 'hand')
    faces(monkeypatch, [1])
    activate(s, source)
    d = s.state.rules.decision
    assert d is not None
    assert s.state.rules.turn_log.rolled['p1'] == 1
    option = next(o.id for o in d.options if 'Progenitus' in o.label)
    answer(s, [option])
    assert any(c.name == chosen.name and c.owner == 'p1' and c.zone == 'p1:library' for c in s.state.cards.values())
    assert not s.state.zones['p1:hand']
    roundtrip(s)


def test_native_owner_cannot_lose_does_not_loop_or_keep_once_watcher(cards, monkeypatch):
    from app.rules.plan import Plan
    from tests.test_rules_source_quality_protection import spell
    s = setup(cards)
    _, chosen = chosen_creature(s, monkeypatch)
    put(s, 'Platinum Angel', 'battlefield', 'p2')
    spell(s, 'Lightning Bolt', {'R': 1}, target=[chosen.id])
    assert 'p2' in Plan(s.state, 'p1', cards, None).live()
    assert not s.state.rules.delayed
    assert not s.state.zones.get('stack')
    roundtrip(s)


def test_delayed_exact_creature_death_is_not_limited_to_original_turn(cards, monkeypatch):
    from app.rules.plan import Plan
    from tests.test_rules_source_quality_protection import spell
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    _, chosen = chosen_creature(s, monkeypatch)
    to_phase(s, 'main1', turn=4)
    assert len(s.state.rules.delayed) == 1
    spell(s, 'Lightning Bolt', {'R': 1}, target=[chosen.id])
    assert 'p2' not in Plan(s.state, 'p1', cards, None).live()
    assert not s.state.rules.delayed
    roundtrip(s)


def test_deck_of_many_things_whole_printed_canonical_gate(cards):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve('The Deck of Many Things')).level == 'FULL'
