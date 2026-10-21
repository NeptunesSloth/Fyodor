"""Paid immediate X through production source and genuine cold continuations."""
import pytest

from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle

cards=gameplay.cards


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
    d=s.state.rules.decision
    act(s,'p1',type='move',card_ids=[copy],to={'player':'p1','zone':'hand'})
    assert copy not in s.state.cards  # A non-stack card copy ceases at the actual zone change/SBA.
    with pytest.raises(ActionError):
        act(s,d.player,type='choose',decision_id=d.id,**({'name':'2'} if phase=='number' else {'option_ids':['x:other']}))
    assert s.state.cards[original.id].zone=='p1:exile'
    roundtrip(s)


@pytest.mark.parametrize('phase',['initial','number'])
@pytest.mark.parametrize('missing',['window','paid'])
def test_paid_x_missing_saved_authority_cannot_be_replaced_by_numeric_choice(cards,phase,missing):
    from app.game.errors import ActionError
    from app.game.session import GameSession
    from app.game.state import GameState

    s,_,_,_,_,_=other_x(cards,number=phase=='number')
    if missing=='window':
        s.state.rules.free_cast_then=None
    else:
        s.state.rules.free_cast_then['e']['paid']=False
    s=GameSession(GameState.model_validate_json(s.state.model_dump_json()),cards=cards)
    d=s.state.rules.decision
    before=s.state.model_dump_json()
    with pytest.raises(ActionError,match='original paid spell object or casting permission'):
        act(s,d.player,type='choose',decision_id=d.id,**({'name':'2'} if phase=='number' else {'option_ids':['x:other']}))
    assert s.state.model_dump_json()==before
    roundtrip(s)


def test_paid_x_legacy_shortcut_retains_existing_cost_without_minting_numeric_identity(cards):
    from app.game.errors import ActionError
    from app.game.session import GameSession
    from app.game.state import GameState

    s,_,original,copy,_,_=other_x(cards)
    s.state.rules.decision.resume.pop('card_object')
    s=GameSession(GameState.model_validate_json(s.state.model_dump_json()),cards=cards)
    with pytest.raises(ActionError):
        answer(s,['x:other'])
    answer(s,['x:0'])
    settle(s)
    assert all(s.state.players[p].life==40 for p in ('p1','p2','p3'))
    assert s.state.cards[original.id].zone=='p1:exile'
    assert copy not in s.state.cards
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_paid_x_other_retains_native_printed_minimum_x_constraint(cards):
    from app.game.errors import ActionError

    s,_=gameplay.founding_chapter(cards,3,third_graveyard=['Mind Grind'])
    original=next(c for c in s.state.cards.values() if c.name=='Mind Grind' and c.zone=='p1:graveyard')
    mana(s,U=1,B=1)
    answer(s,[original.id])
    copy=s.state.rules.decision.options[0].card_id
    answer(s,[copy])
    answer(s,['x:other'])
    d=s.state.rules.decision
    before=s.state.model_dump_json()
    with pytest.raises(ActionError,match="X can't be 0"):
        act(s,d.player,type='choose',decision_id=d.id,name='0')
    assert s.state.model_dump_json()==before
    answer(s,['cancel'])
    assert copy not in s.state.cards
    assert s.state.cards[original.id].zone=='p1:exile'
    roundtrip(s)


def test_truly_free_chapter_one_ordinary_mana_x_remains_zero_without_numeric_other(cards):
    s,_=gameplay.founding_chapter(cards,1,first_hand=['Earthquake'])
    spell=next(c for c in s.state.cards.values() if c.name=='Earthquake' and c.zone=='p1:hand')
    answer(s,[spell.id])
    assert s.state.rules.decision is None
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    assert all(s.state.players[p].life==40 for p in ('p1','p2','p3'))
    roundtrip(s)


def test_paid_x_other_cold_number_then_real_self_payment_preserves_source_and_value(cards,tmp_path):
    from tests.test_rules_exile_cast_outcomes45_cold import fresh

    s,source,original,copy,_,_=other_x(cards)
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'other.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['x:other']})
    assert s.state.rules.decision.resume['step']=='paid_x_number'
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'number.json',d.player,{'type':'choose','decision_id':d.id,'name':'2'})
    assert s.state.rules.decision.resume['step']=='pay_mana'
    mana(s,C=2)
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'pay.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['pay']})
    assert all(s.state.players[p].life==38 for p in ('p1','p2','p3'))
    assert s.state.cards[original.id].zone=='p1:exile'
    assert copy not in s.state.cards
    assert s.state.cards[source.id].zone=='p1:graveyard'


def test_paid_x_other_applies_real_cost_increase_before_manual_mana_payment(cards):
    s,source=gameplay.founding_chapter(cards,3,third_graveyard=['Earthquake'],battlefield=['Thalia, Guardian of Thraben'],generic=2)
    altar=put(s,"Ashnod's Altar",'battlefield')
    bear=next(c for c in s.state.cards.values() if c.name=='Grizzly Bears' and c.zone=='p1:battlefield')
    original=next(c for c in s.state.cards.values() if c.name=='Earthquake' and c.zone=='p1:graveyard')
    mana(s,R=1,C=1)
    answer(s,[original.id])
    copy=s.state.rules.decision.options[0].card_id
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[copy])
    answer(s,['x:other'])
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,name='2')
    settle(s)
    assert s.state.rules.decision.resume['step']=='pay_mana'
    act(s,'p1',type='activate_ability',card_id=altar.id,ability=0)
    if s.state.rules.decision is not None and s.state.rules.decision.resume['step']=='ability_cost':
        answer(s,[bear.id])
    if s.state.rules.decision is not None:
        answer(s,['pay'])
    settle(s)
    assert all(s.state.players[p].life==38 for p in ('p1','p2','p3'))
    assert not s.state.players['p1'].mana
    assert s.state.cards[original.id].zone=='p1:exile'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_paid_x_other_preserves_kicker_and_selected_conspire_through_normal_payment(cards):
    s,source=gameplay.founding_chapter(cards,3,third_graveyard=['Comet Storm'],battlefield=['Wort, the Raidmother','Rivaz of the Claw'])
    altar=put(s,"Ashnod's Altar",'battlefield')
    bear=next(c for c in s.state.cards.values() if c.name=='Grizzly Bears' and c.zone=='p1:battlefield')
    wort=next(c for c in s.state.cards.values() if c.name=='Wort, the Raidmother' and c.zone=='p1:battlefield')
    rivaz=next(c for c in s.state.cards.values() if c.name=='Rivaz of the Claw' and c.zone=='p1:battlefield')
    original=next(c for c in s.state.cards.values() if c.name=='Comet Storm' and c.zone=='p1:graveyard')
    mana(s,R=2,C=1)
    answer(s,[original.id])
    copy=s.state.rules.decision.options[0].card_id
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[copy])
    assert s.state.rules.decision.resume['step']=='free_optional'
    answer(s,['kicker:1',copy+':conspire'])
    assert s.state.rules.decision.resume['step']=='free_x'
    answer(s,['x:other'])
    assert s.state.rules.decision.resume['intent']['kicker']==1
    assert s.state.rules.decision.resume['intent']['optional_costs']==[copy+':conspire']
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,name='2')
    for _ in range(10):
        d=s.state.rules.decision
        assert d is not None
        if d.resume['step']=='pay_mana':
            break
        ids=[o.id for o in d.options]
        if d.resume['step']=='ability_cost':
            assert wort.id in ids and rivaz.id in ids
            answer(s,[wort.id,rivaz.id])
        else:
            assert 'p2' in ids and 'p3' in ids
            answer(s,['p2','p3'])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    act(s,'p1',type='activate_ability',card_id=altar.id,ability=0)
    if s.state.rules.decision is not None and s.state.rules.decision.resume['step']=='ability_cost':
        answer(s,[bear.id])
    if s.state.rules.decision is not None and s.state.rules.decision.resume['step']=='pay_mana':
        answer(s,['pay'])
    for _ in range(5):
        d=s.state.rules.decision
        if d is None:
            break
        assert d.resume['step']=='copy_target'
        answer(s,['keep'])
    settle(s)
    assert s.state.cards[wort.id].tapped and s.state.cards[rivaz.id].tapped
    assert s.state.cards[bear.id].zone=='p1:graveyard'
    assert s.state.players['p2'].life==36 and s.state.players['p3'].life==36
    assert s.state.cards[original.id].zone=='p1:exile'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert copy not in s.state.cards
    roundtrip(s)


def test_paid_x_other_cold_numeric_cancel_ends_original_window_without_cast(cards,tmp_path):
    from tests.test_rules_exile_cast_outcomes45_cold import fresh

    s,source,original,copy,_,_=other_x(cards,number=True)
    assert s.state.rules.decision.resume['step']=='paid_x_number'
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'cancel.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['cancel']})
    assert s.state.rules.decision is None and s.state.rules.free_cast_then is None
    assert copy not in s.state.cards
    assert s.state.cards[original.id].zone=='p1:exile'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert all(s.state.players[p].life==40 for p in ('p1','p2','p3'))
    roundtrip(s)


@pytest.mark.parametrize('legacy_paid_chosen',[False,True])
def test_paid_optional_decline_is_recorded_once_across_x_and_payment_resume(cards,legacy_paid_chosen):
    from app.game.session import GameSession
    from app.game.state import GameState

    s,source=gameplay.founding_chapter(cards,3,third_graveyard=['Comet Storm'])
    original=next(c for c in s.state.cards.values() if c.name=='Comet Storm' and c.zone=='p1:graveyard')
    mana(s,R=2)
    answer(s,[original.id])
    copy=s.state.rules.decision.options[0].card_id
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[copy])
    assert s.state.rules.decision.resume['step']=='free_optional'
    if legacy_paid_chosen:
        s.state.rules.free_cast_then.pop('paid_cost_chosen',None)
        s=GameSession(GameState.model_validate_json(s.state.model_dump_json()),cards=cards)
    answer(s,[])
    assert s.state.rules.decision.resume['step']=='free_x'
    assert s.state.rules.decision.resume['intent']['optional_asked'] is True
    answer(s,['x:other'])
    assert s.state.rules.decision.resume['intent']['optional_asked'] is True
    assert s.state.rules.decision.resume['intent']['kicker']==0
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,name='2')
    settle(s)
    assert s.state.rules.decision.resume['step']=='cast_group'
    answer(s,['p2'])
    assert s.state.rules.decision.resume['step']=='pay_mana'
    assert s.state.rules.decision.resume['intent']['optional_asked'] is True
    mana(s,C=2)
    answer(s,['pay'])
    assert s.state.rules.decision is None
    assert s.state.players['p2'].life==38 and s.state.players['p3'].life==40
    assert s.state.cards[original.id].zone=='p1:exile' and copy not in s.state.cards
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_paid_optional_legacy_free_true_receipt_and_cold_decline_do_not_repeat_choice(cards,tmp_path):
    from app.game.session import GameSession
    from app.game.state import GameState
    from tests.test_rules_exile_cast_outcomes45_cold import fresh

    s,source=gameplay.founding_chapter(cards,3,third_graveyard=['Comet Storm'])
    original=next(c for c in s.state.cards.values() if c.name=='Comet Storm' and c.zone=='p1:graveyard')
    mana(s,R=2)
    answer(s,[original.id])
    copy=s.state.rules.decision.options[0].card_id
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[copy])
    assert s.state.rules.decision.resume['step']=='free_optional'
    s.state.rules.decision.resume['intent']['free']=True
    s.state.rules.free_cast_then.pop('paid_cost_chosen',None)
    s=GameSession(GameState.model_validate_json(s.state.model_dump_json()),cards=cards)
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'optional.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[]})
    assert s.state.rules.decision.resume['step']=='free_x'
    assert s.state.rules.decision.resume['intent']['optional_asked'] is True
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'other.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['x:other']})
    assert s.state.rules.decision.resume['step']=='paid_x_number'
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'cancel.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['cancel']})
    assert s.state.rules.decision is None and s.state.rules.free_cast_then is None
    assert copy not in s.state.cards and s.state.cards[original.id].zone=='p1:exile'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    roundtrip(s)


def test_paid_optional_multiple_kicker_counts_rejected_without_consuming_original_choice(cards):
    from app.game.errors import ActionError

    s,_=gameplay.founding_chapter(cards,3,third_graveyard=['Comet Storm'])
    original=next(c for c in s.state.cards.values() if c.name=='Comet Storm' and c.zone=='p1:graveyard')
    mana(s,R=2,C=2)
    answer(s,[original.id])
    copy=s.state.rules.decision.options[0].card_id
    answer(s,[copy])
    assert s.state.rules.decision.resume['step']=='free_optional'
    before=s.state.model_dump_json()
    d=s.state.rules.decision
    with pytest.raises(ActionError,match='one number'):
        act(s,d.player,type='choose',decision_id=d.id,option_ids=['kicker:1','kicker:2'])
    assert s.state.model_dump_json()==before
    answer(s,[])
    assert s.state.rules.decision.resume['step']=='free_x'
    answer(s,['x:other'])
    answer(s,['cancel'])
    assert copy not in s.state.cards and s.state.cards[original.id].zone=='p1:exile'
    roundtrip(s)
