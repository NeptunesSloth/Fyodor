"""Native numeric quantity production proofs, without parser or continuation adapters."""
import pytest

from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle
from tests.test_rules_wave30m_durations import to_phase

cards=gameplay.cards


@pytest.mark.parametrize('count',[7,20,21])
def test_numeric_multikicker_actual_life_alternative_and_real_total_payment(cards,count):
    s=gameplay.setup(cards,'Anrakyr the Traveller','Everflowing Chalice')
    source=put(s,'Anrakyr the Traveller','battlefield')
    spell=put(s,'Everflowing Chalice','hand')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='set_prefs',payment='self')
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    answer(s,[spell.id])
    assert 'kicker:other' in [o.id for o in s.state.rules.decision.options]
    answer(s,['kicker:other'])
    d=s.state.rules.decision
    assert d.resume['step']=='free_multikicker'
    act(s,d.player,type='choose',decision_id=d.id,name=str(count))
    settle(s)
    assert s.state.rules.decision.resume['step']=='pay_mana'
    mana(s,C=2*count)
    answer(s,['pay'])
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    assert s.state.cards[spell.id].counters.get('charge',0)==count
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_multikicker_platform_range_matches_announced_x():
    from pydantic import ValidationError

    from app.game.actions import CastSpell, parse_action
    assert CastSpell(card_id='card',kicker=1000).kicker==1000
    assert parse_action({'type':'cast_spell','card_id':'card','kicker':1000}).kicker==1000
    with pytest.raises(ValidationError):
        parse_action({'type':'cast_spell','card_id':'card','kicker':1001})


def numeric_offer(cards,*,tax=False,before_other=False,shortcut=False):
    s=gameplay.setup(cards,'Anrakyr the Traveller','Everflowing Chalice','Thalia, Guardian of Thraben')
    if tax:
        put(s,'Thalia, Guardian of Thraben','battlefield')
    source=put(s,'Anrakyr the Traveller','battlefield')
    spell=put(s,'Everflowing Chalice','hand')
    to_phase(s,'declare_attackers',turn=4)
    act(s,'p1',type='set_prefs',payment='self')
    act(s,'p1',type='declare_attackers',attackers=[{'card_id':source.id,'target':'p2'}])
    settle(s)
    if shortcut:
        mana(s,C=2)
    answer(s,[spell.id])
    if not before_other:
        answer(s,['kicker:other'])
    return s,spell


def test_numeric_multikicker_over_platform_bound_is_atomic_and_max_count_can_cancel_payment(cards):
    from app.game.errors import ActionError

    s,spell=numeric_offer(cards)
    d=s.state.rules.decision
    before=s.state.model_dump_json()
    with pytest.raises(ActionError,match='0 to 1000'):
        act(s,d.player,type='choose',decision_id=d.id,name='1001')
    assert s.state.model_dump_json()==before
    act(s,d.player,type='choose',decision_id=d.id,name='1000')
    settle(s)
    assert s.state.rules.decision.resume['step']=='pay_mana'
    answer(s,['cancel'])
    assert s.state.cards[spell.id].zone=='p1:hand'
    assert s.state.rules.free_cast_then is None
    roundtrip(s)


def test_numeric_multikicker_cold_prompt_then_self_payment_preserves_count(cards,tmp_path):
    from tests.test_rules_exile_outcomes42_cold import fresh

    s,spell=numeric_offer(cards)
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'number.json',d.player,{'type':'choose','decision_id':d.id,'name':'21'})
    assert s.state.rules.decision.resume['step']=='pay_mana'
    mana(s,C=42)
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'payment.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['pay']})
    assert s.state.cards[spell.id].zone=='p1:battlefield'
    assert s.state.cards[spell.id].counters.get('charge',0)==21


def test_numeric_multikicker_source_reincarnation_cannot_consume_old_free_cast_authority(cards):
    from app.game.errors import ActionError

    s,spell=numeric_offer(cards)
    act(s,'p1',type='move',card_ids=[spell.id],to={'player':'p1','zone':'exile'})
    act(s,'p1',type='move',card_ids=[spell.id],to={'player':'p1','zone':'hand'})
    d=s.state.rules.decision
    with pytest.raises(ActionError):
        act(s,d.player,type='choose',decision_id=d.id,name='7')
    assert s.state.cards[spell.id].zone=='p1:hand'
    assert not s.state.cards[spell.id].counters
    roundtrip(s)


def test_numeric_multikicker_actual_cost_increase_is_paid_after_announced_count(cards):
    from app.game.errors import ActionError

    s,spell=numeric_offer(cards,tax=True)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,name='7')
    settle(s)
    assert s.state.rules.decision.resume['step']=='pay_mana'
    mana(s,C=14)
    with pytest.raises(ActionError):
        answer(s,['pay'])
    assert s.state.cards[spell.id].zone=='p1:hand'
    mana(s,C=1)
    answer(s,['pay'])
    assert s.state.cards[spell.id].counters.get('charge',0)==7
    assert not s.state.players['p1'].mana
    roundtrip(s)


def test_numeric_other_preserves_selected_conspire_optional_cost_and_real_payment(cards):
    from tests.test_rules_ordered_tutor_continuations import cast

    s=gameplay.setup(cards,'Mindclaw Shaman','Comet Storm','Wort, the Raidmother')
    wort=put(s,'Wort, the Raidmother','battlefield')
    rivaz=put(s,'Rivaz of the Claw','battlefield')
    spell=put(s,'Comet Storm','hand',pid='p2')
    cast(s,'Mindclaw Shaman')
    answer(s,['p2'])
    act(s,'p1',type='clear_mana',player='p1')
    act(s,'p1',type='set_prefs',payment='self')
    answer(s,[spell.id])
    answer(s,['kicker:other',spell.id+':conspire'])
    d=s.state.rules.decision
    assert d.resume['intent']['optional_costs']==[spell.id+':conspire']
    act(s,d.player,type='choose',decision_id=d.id,name='1')
    for _ in range(12):
        d=s.state.rules.decision
        if d is None:
            act(s,s.state.rules.priority,type='pass_priority')
            continue
        if d.resume['step']=='pay_mana':
            break
        ids=[o.id for o in d.options]
        if wort.id in ids and rivaz.id in ids and d.resume['step']=='ability_cost':
            answer(s,[wort.id,rivaz.id])
        elif 'p2' in ids and 'p3' in ids:
            answer(s,['p2','p3'])
        else:
            raise AssertionError(d)
    assert s.state.rules.decision.resume['step']=='pay_mana'
    mana(s,C=1)
    answer(s,['pay'])
    assert s.state.cards[wort.id].tapped and s.state.cards[rivaz.id].tapped
    assert s.state.rules.decision is not None
    roundtrip(s)


def test_numeric_multikicker_before_other_source_reincarnation_cannot_mint_new_identity(cards):
    from app.game.errors import ActionError

    s,spell=numeric_offer(cards,before_other=True)
    act(s,'p1',type='move',card_ids=[spell.id],to={'player':'p1','zone':'exile'})
    act(s,'p1',type='move',card_ids=[spell.id],to={'player':'p1','zone':'hand'})
    with pytest.raises(ActionError):
        answer(s,['kicker:other'])
    assert s.state.cards[spell.id].zone=='p1:hand'
    assert s.state.rules.decision.resume['step']=='free_optional'
    roundtrip(s)


@pytest.mark.parametrize('other',[False,True])
def test_numeric_multikicker_missing_original_identity_cannot_enable_other_but_preserves_legacy_shortcut(cards,other):
    from app.game.errors import ActionError

    s,spell=numeric_offer(cards,before_other=True,shortcut=True)
    s.state.rules.decision.resume.pop('card_object')
    from app.game.session import GameSession
    from app.game.state import GameState

    s=GameSession(GameState.model_validate_json(s.state.model_dump_json()),cards=cards)
    roundtrip(s)
    if other:
        with pytest.raises(ActionError):
            answer(s,['kicker:other'])
        assert s.state.rules.decision.resume['step']=='free_optional'
    else:
        answer(s,['kicker:1'])
        assert s.state.cards[spell.id].counters.get('charge',0)==1
    roundtrip(s)
