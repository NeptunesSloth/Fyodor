"""Paid immediate X proposal: isolated native source, leaf staging only until admission."""
import pytest

from app.rules import casting
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle

pytestmark=pytest.mark.skipif(not hasattr(casting,'resume_paid_x_number'),reason='Paid-X numeric proposal is isolated pending gates')
cards=gameplay.cards
staged=gameplay.staged


def other_x(cards,*,number=False):
    s,source=gameplay.founding_chapter(cards,3,third_graveyard=['Earthquake'])
    altar=put(s,"Ashnod's Altar",'battlefield')
    bear=next(c for c in s.state.cards.values() if c.name=='Grizzly Bears' and c.zone=='p1:battlefield')
    original=next(c for c in s.state.cards.values() if c.name=='Earthquake' and c.zone=='p1:graveyard')
    mana(s,R=1)
    answer(s,[original.id])
    copy=s.state.rules.decision.options[0].card_id
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[copy])
    assert s.state.rules.decision.resume['step']=='free_x'
    assert 'x:0' in [o.id for o in s.state.rules.decision.options]
    assert 'x:2' not in [o.id for o in s.state.rules.decision.options]
    if number:
        answer(s,['x:other'])
        assert s.state.rules.decision.resume['step']=='paid_x_number'
    return s,source,original,copy,altar,bear


def test_paid_x_other_actual_self_altar_can_pay_two_beyond_auto_shortcut(cards):
    s,source,original,copy,altar,bear=other_x(cards,number=True)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,name='2')
    settle(s)
    assert s.state.rules.decision.resume['step']=='pay_mana'
    act(s,'p1',type='activate_ability',card_id=altar.id,ability=0)
    if s.state.rules.decision is not None and s.state.rules.decision.resume['step']=='ability_cost':
        answer(s,[bear.id])
    if s.state.rules.decision is not None:
        assert s.state.rules.decision.resume['step']=='pay_mana'
        answer(s,['pay'])
    settle(s)
    assert all(s.state.players[p].life==38 for p in ('p1','p2','p3'))
    assert s.state.cards[original.id].zone=='p1:exile'
    assert copy not in s.state.cards
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_paid_x_other_out_of_range_is_atomic_and_maximum_can_cancel_normal_payment(cards):
    from app.game.errors import ActionError

    s,source,original,copy,_,_=other_x(cards,number=True)
    d=s.state.rules.decision
    before=s.state.model_dump_json()
    with pytest.raises(ActionError,match='0 to 1000'):
        act(s,d.player,type='choose',decision_id=d.id,name='1001')
    assert s.state.model_dump_json()==before
    act(s,d.player,type='choose',decision_id=d.id,name='1000')
    settle(s)
    assert s.state.rules.decision.resume['step']=='pay_mana'
    answer(s,['cancel'])
    assert copy not in s.state.cards
    assert s.state.cards[original.id].zone=='p1:exile'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


@pytest.mark.parametrize('phase',['initial','number'])
def test_paid_x_original_copy_object_required_at_both_numeric_boundaries(cards,phase):
    from app.game.errors import ActionError

    s,_,original,copy,_,_=other_x(cards,number=phase=='number')
    act(s,'p1',type='move',card_ids=[copy],to={'player':'p1','zone':'hand'})
    act(s,'p1',type='move',card_ids=[copy],to={'player':'p1','zone':'exile'})
    d=s.state.rules.decision
    with pytest.raises(ActionError):
        act(s,d.player,type='choose',decision_id=d.id,**({'name':'2'} if phase=='number' else {'option_ids':['x:other']}))
    assert s.state.cards[original.id].zone=='p1:exile'
    roundtrip(s)
