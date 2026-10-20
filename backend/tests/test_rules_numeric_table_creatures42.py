"""Whole printed production numeric-table creature proofs."""
import pytest

from tests.test_rules_designations import put, roundtrip
from tests.test_rules_random_consequences import faces
from tests.test_rules_random_native_outcomes42 import cards as cards
from tests.test_rules_random_native_outcomes42 import setup
from tests.test_rules_source_quality_protection import spell


@pytest.mark.parametrize('result,amount', [(1, 4), (6, 4), (7, 5), (14, 5), (15, 6), (20, 6)])
def test_goblin_actual_cast_etb_retains_each_table_boundary_and_mana_provenance(cards, monkeypatch, result, amount):
    from app.rules.mana_units import visible_pool
    s = setup(cards)
    faces(monkeypatch, [result])
    source = spell(s, '"Name Sticker" Goblin', {'C': 2, 'R': 1})
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.rules.turn_log.rolled['p1'] == 1
    assert visible_pool(s.state, 'p1') == {'R': amount}
    roundtrip(s)


def test_goblin_actual_graveyard_entry_never_rolls_again(cards, monkeypatch):
    from tests.test_rules_random_consequences import answer
    s = setup(cards)
    source = put(s, '"Name Sticker" Goblin', 'graveyard')
    faces(monkeypatch, [2, 3])
    spell(s, 'Grave Endeavor', {'C': 5, 'B': 2})
    answer(s, ['0'])
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert s.state.rules.turn_log.rolled['p1'] == 2
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_native_cloudshift_exile_entry_never_rolls(cards, monkeypatch):
    s = setup(cards)
    source = put(s, '"Name Sticker" Goblin', 'battlefield')
    faces(monkeypatch, [])
    spell(s, 'Cloudshift', {'W': 1}, target=[source.id])
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert not s.state.rules.turn_log.rolled
    roundtrip(s)


@pytest.mark.parametrize('natural,direction', [(1, 'minus'), (20, 'plus')])
def test_actual_modified_outside_table_result_produces_no_mana(cards, monkeypatch, natural, direction):
    from app.rules.mana_units import visible_pool
    from tests.test_rules_numeric_roll_finalization42 import accept
    s = setup(cards)
    put(s, 'Night Shift of the Living Dead', 'battlefield')
    faces(monkeypatch, [natural])
    spell(s, '"Name Sticker" Goblin', {'C': 2, 'R': 1})
    accept(s, direction=direction)
    assert visible_pool(s.state, 'p1') == {}
    assert s.state.players['p1'].life == 39
    assert s.state.rules.turn_log.rolled['p1'] == 1
    roundtrip(s)


@pytest.mark.parametrize('others,rolls', [(8, True), (9, False)])
def test_named_creature_limit_counts_source_and_rechecks_real_battlefield(cards, monkeypatch, others, rolls):
    from app.rules.mana_units import visible_pool
    from tests.game_helpers import act
    s = setup(cards)
    act(s, 'p1', type='create_token', player='p1', count=others, stacked=False,
        token={'name': '"Name Sticker" Goblin', 'type_line': 'Token Creature — Goblin', 'power': '1', 'toughness': '1', 'text': ''})
    assert not s.state.rules.turn_log.rolled
    faces(monkeypatch, [10] if rolls else [])
    spell(s, '"Name Sticker" Goblin', {'C': 2, 'R': 1})
    assert s.state.rules.turn_log.rolled.get('p1', 0) == int(rolls)
    assert visible_pool(s.state, 'p1') == ({'R': 5} if rolls else {})
    roundtrip(s)


def cast_goblin_until_etb_stack(s):
    from tests.game_helpers import act
    from tests.test_rules_player_protection import priority
    from tests.test_rules_wave31d_spell_copies import resolve_one
    source = put(s, '"Name Sticker" Goblin', 'hand')
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 2, 'R': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id)
    resolve_one(s)
    assert s.state.cards[source.id].zone == 'p1:battlefield'
    assert len(s.state.zones['stack']) == 1
    assert not s.state.rules.turn_log.rolled
    return source


@pytest.mark.parametrize('response', ['source_blink', 'stifle'])
def test_real_trigger_can_be_countered_or_fails_intervening_same_object_condition(cards, monkeypatch, response):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle
    from tests.test_rules_player_protection import priority
    s = setup(cards)
    faces(monkeypatch, [])
    source = cast_goblin_until_etb_stack(s)
    if response == 'source_blink':
        spell(s, 'Cloudshift', {'W': 1}, target=[source.id])
    else:
        counter = put(s, 'Stifle', 'hand', 'p2')
        target = s.state.zones['stack'][-1]
        priority(s, 'p2')
        act(s, 'p2', type='add_mana', player='p2', mana={'U': 1})
        act(s, 'p2', type='cast_spell', card_id=counter.id, targets=[target])
        settle(s)
    assert not s.state.rules.turn_log.rolled
    roundtrip(s)


def test_actual_other_player_cast_produces_only_that_players_mana(cards, monkeypatch):
    from app.rules.mana_units import visible_pool
    s = setup(cards)
    from tests.test_rules_wave30m_durations import to_phase
    to_phase(s, 'main1', turn=2)
    faces(monkeypatch, [15])
    spell(s, '"Name Sticker" Goblin', {'C': 2, 'R': 1}, player='p2')
    assert visible_pool(s.state, 'p2') == {'R': 6}
    assert visible_pool(s.state, 'p1') == visible_pool(s.state, 'p3') == {}
    assert s.state.rules.turn_log.rolled == {'p2': 1}
    roundtrip(s)


@pytest.mark.parametrize('phase', ['trigger', 'kept'])
def test_saved_native_trigger_origin_and_final_kept_table_continue_fresh(cards, monkeypatch, tmp_path, phase):
    import subprocess
    import sys
    from pathlib import Path
    s = setup(cards)
    if phase == 'kept':
        put(s, 'Night Shift of the Living Dead', 'battlefield')
        faces(monkeypatch, [10])
        spell(s, '"Name Sticker" Goblin', {'C': 2, 'R': 1})
        assert s.state.rules.decision.resume['step'] == 'numeric_roll42'
    else:
        cast_goblin_until_etb_stack(s)
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
path,db,phase=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
count=[]
def raw(*a):
 assert phase=='trigger' and not count
 count.append(10);return 10
importlib.import_module('app.game.resolve')._rng_int=raw
if phase=='kept':
 d=s.state.rules.decision
 s.perform(d.player,{'type':'choose','decision_id':d.id,'option_ids':['done']})
for _ in range(40):
 if not s.state.zones.get('stack'):break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
from app.rules.mana_units import visible_pool
assert visible_pool(s.state,'p1')=={'R':5}
assert visible_pool(s.state,'p2')=={}
assert s.state.rules.turn_log.rolled=={'p1':1}
assert len(count)==(1 if phase=='trigger' else 0)
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), phase], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_intervening_limit_rechecks_after_more_named_creatures_enter(cards, monkeypatch):
    from tests.game_helpers import act
    from tests.test_rules_designations import settle
    s = setup(cards)
    faces(monkeypatch, [])
    cast_goblin_until_etb_stack(s)
    act(s, 'p1', type='create_token', player='p1', count=9, stacked=False,
        token={'name': '"Name Sticker" Goblin', 'type_line': 'Token Creature — Goblin', 'power': '1', 'toughness': '1', 'text': ''})
    settle(s)
    assert not s.state.rules.turn_log.rolled
    roundtrip(s)


def test_named_noncreatures_and_differently_named_creatures_do_not_count(cards, monkeypatch):
    from app.rules.mana_units import visible_pool
    from tests.game_helpers import act
    s = setup(cards)
    act(s, 'p1', type='create_token', player='p1', count=10, stacked=False,
        token={'name': '"Name Sticker" Goblin', 'type_line': 'Token Artifact', 'text': ''})
    act(s, 'p1', type='create_token', player='p1', count=10, stacked=False,
        token={'name': 'Name Sticker Goblin', 'type_line': 'Token Creature — Goblin', 'power': '1', 'toughness': '1', 'text': ''})
    faces(monkeypatch, [10])
    spell(s, '"Name Sticker" Goblin', {'C': 2, 'R': 1})
    assert visible_pool(s.state, 'p1') == {'R': 5}
    assert s.state.rules.turn_log.rolled == {'p1': 1}
    roundtrip(s)


def test_name_sticker_goblin_whole_printed_canonical_gate(cards):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve('"Name Sticker" Goblin')).level == 'FULL'
