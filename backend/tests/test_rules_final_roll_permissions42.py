"""Whole printed production casting and final-result authority proofs."""
import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_designations import put, roundtrip, settle
from tests.test_rules_numeric_roll_finalization42 import activate_troll
from tests.test_rules_player_protection import priority
from tests.test_rules_random_consequences import answer, faces
from tests.test_rules_random_native_outcomes42 import cards as cards
from tests.test_rules_random_native_outcomes42 import setup
from tests.test_rules_wave7b_activation import ability_index


def cast_eel(s, cards, source, **kwargs):
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'], **kwargs)
    settle(s)


@pytest.mark.parametrize('result', [5, 6, 20])
def test_exact_final_six_unlocks_real_paid_graveyard_cast_and_exiles_that_authority(cards, monkeypatch, result):
    s = setup(cards)
    source = put(s, 'Eelectrocute', 'graveyard')
    faces(monkeypatch, [result])
    activate_troll(s)
    if result != 6:
        with pytest.raises(ActionError):
            cast_eel(s, cards, source)
        assert s.state.cards[source.id].zone == 'p1:graveyard'
        assert s.state.players['p2'].life == 40
    else:
        cast_eel(s, cards, source)
        assert s.state.cards[source.id].zone == 'p1:exile'
        assert s.state.players['p2'].life == 38
    roundtrip(s)


def test_actual_wrenn_retrace_authority_while_own_six_authority_exists_keeps_spell_in_graveyard(cards, monkeypatch):
    from app.rules import permissions
    s = setup(cards)
    wrenn = put(s, 'Wrenn and Six', 'battlefield')
    act(s, 'p1', type='set_counter', card_id=wrenn.id, kind='loyalty', value=7)
    priority(s, 'p1')
    act(s, 'p1', type='activate_ability', card_id=wrenn.id, ability=ability_index(s, wrenn, 'You get an emblem'))
    settle(s)
    source = put(s, 'Eelectrocute', 'graveyard')
    land = put(s, 'Forest', 'hand')
    faces(monkeypatch, [6])
    activate_troll(s)
    ch = __import__('app.rules.plan', fromlist=['Plan']).Plan(s.state, 'p1', cards, None).ch(s.state.cards[source.id])
    grants = permissions.grants(s.state, 'p1', s.state.cards[source.id], ch, cards)
    alternate = next(g for g in grants if not g.exile_gy and 'discard' in g.extra)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1})
    act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'], via=alternate.choice_key)
    if s.state.rules.decision is not None:
        answer(s, [land.id])
    settle(s)
    assert s.state.cards[source.id].zone == s.state.cards[land.id].zone == 'p1:graveyard'
    assert s.state.players['p2'].life == 38
    roundtrip(s)


def test_other_player_final_six_does_not_unlock_ours_and_current_turn_receipt_controls_hints(cards, monkeypatch):
    from app.rules import casting
    from tests.test_rules_wave30m_durations import to_phase
    s = setup(cards)
    source = put(s, 'Eelectrocute', 'graveyard')
    other = put(s, 'Eelectrocute', 'graveyard', 'p2')
    faces(monkeypatch, [6])
    activate_troll(s)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1})
    assert casting.castable(s.state, 'p1', s.state.cards[source.id], cards)
    assert source.id in s.view('p1')['rules']['hints']['castable']
    assert not casting.castable(s.state, 'p2', s.state.cards[other.id], cards, check_priority=False)
    to_phase(s, 'main1', turn=4)
    assert not casting.castable(s.state, 'p1', s.state.cards[source.id], cards, check_priority=False)
    assert source.id not in s.view('p1')['rules']['hints']['castable']
    roundtrip(s)


def test_cast_from_hand_after_final_six_does_not_inherit_graveyard_exile_authority(cards, monkeypatch):
    s = setup(cards)
    source = put(s, 'Eelectrocute', 'hand')
    faces(monkeypatch, [6])
    activate_troll(s)
    cast_eel(s, cards, source)
    assert s.state.cards[source.id].zone == 'p1:graveyard'
    assert s.state.players['p2'].life == 38
    roundtrip(s)


@pytest.mark.parametrize('stage', ['six_receipt', 'paid_stack'])
def test_saved_real_final_six_permission_and_selected_authority_resume_cold(cards, monkeypatch, tmp_path, stage):
    import subprocess
    import sys
    from pathlib import Path
    s = setup(cards)
    source = put(s, 'Eelectrocute', 'graveyard')
    faces(monkeypatch, [6])
    activate_troll(s)
    priority(s, 'p1')
    act(s, 'p1', type='add_mana', player='p1', mana={'R': 1, 'C': 1})
    if stage == 'paid_stack':
        act(s, 'p1', type='cast_spell', card_id=source.id, targets=['p2'])
        assert s.state.cards[source.id].zone == 'stack'
    path = tmp_path / (stage + '.json')
    path.write_text(s.state.model_dump_json())
    code = r'''
import sys
from pathlib import Path
from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.game.session import GameSession
from app.game.state import GameState
path,db,stage,cid=sys.argv[1:]
repo=CardRepository(Path(db),ImageStore(Path(db).parent/'images'))
s=GameSession(GameState.model_validate_json(Path(path).read_text()),cards=repo)
if stage=='six_receipt':
 assert cid in s.view('p1')['rules']['hints']['castable']
 s.perform('p1',{'type':'cast_spell','card_id':cid,'targets':['p2']})
for _ in range(45):
 if not s.state.zones.get('stack'):break
 assert s.state.rules.decision is None
 s.perform(s.state.rules.priority,{'type':'pass_priority'})
assert s.state.cards[cid].zone=='p1:exile'
assert s.state.players['p2'].life==38
assert s.history.rebuild()==s.state
assert GameState.model_validate_json(s.state.model_dump_json())==s.state
'''
    result = subprocess.run([sys.executable, '-c', code, str(path), str(cards.db_path), stage, source.id], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=120)
    assert result.returncode == 0, result.stderr


def test_eelectrocute_whole_printed_canonical_gate(cards):
    from app.rules import coverage
    assert coverage.of_card_data(cards.resolve('Eelectrocute')).level == 'FULL'
