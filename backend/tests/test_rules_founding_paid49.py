"""Founding chapters through production paid-copy casting."""
import pytest

from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import roundtrip
from tests.test_rules_ordered_tutor_continuations import cast

cards=gameplay.cards


@pytest.mark.parametrize('response',['Stifle','Cremate','Disenchant'])
def test_founding_announced_third_chapter_rechecks_target_and_survives_source_departure(cards,response):
    s,source=gameplay.founding_chapter(cards,3,third_graveyard=['Divination'],first_hand=[response])
    original=next(c for c in s.state.cards.values() if c.name=='Divination' and c.zone=='p1:graveyard')
    mana(s,U=1,C=2)
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[original.id])
    trigger=next(k for k,e in s.state.rules.stack.items() if e.kind=='trigger' and e.source_card==source.id)
    cast(s,response,targets=[trigger if response=='Stifle' else original.id if response=='Cremate' else source.id])
    if response=='Disenchant':
        assert s.state.cards[source.id].zone=='p1:graveyard'
        assert s.state.rules.decision.resume['step']=='free_cast_pick'
        copy=s.state.rules.decision.options[0].card_id
        answer(s,[copy])
        assert copy not in s.state.cards
    else:
        assert s.state.rules.decision is None
    assert s.state.cards[original.id].zone==('p1:graveyard' if response=='Stifle' else 'p1:exile')
    assert s.state.rules.free_cast_then is None
    roundtrip(s)


def test_founding_paid_copy_mandatory_additional_discard_uses_real_cost_and_original_stays_exiled(cards):
    s,source=gameplay.founding_chapter(cards,3,third_graveyard=['Cathartic Reunion'],first_hand=['Murder','Divination'])
    original=next(c for c in s.state.cards.values() if c.name=='Cathartic Reunion' and c.zone=='p1:graveyard')
    discards=[c.id for c in s.state.cards.values() if c.zone=='p1:hand' and c.name in ('Murder','Divination')]
    mana(s,R=1,C=1)
    answer(s,[original.id])
    copy=s.state.rules.decision.options[0].card_id
    answer(s,[copy])
    if s.state.rules.decision is not None:
        assert s.state.rules.decision.resume['step']=='ability_cost'
        answer(s,discards)
    assert all(s.state.cards[c].zone=='p1:graveyard' for c in discards)
    assert s.state.cards[original.id].zone=='p1:exile'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert copy not in s.state.cards
    roundtrip(s)


def test_founding_paid_copy_without_mana_cost_cannot_be_cast_for_free(cards):
    s,source=gameplay.founding_chapter(cards,3,third_graveyard=['Ancestral Vision'])
    original=next(c for c in s.state.cards.values() if c.name=='Ancestral Vision' and c.zone=='p1:graveyard')
    answer(s,[original.id])
    assert s.state.rules.decision is None
    assert s.state.cards[original.id].zone=='p1:exile'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert not any(c.name=='Ancestral Vision' and c.zone in ('stack','p1:hand','p1:graveyard') for c in s.state.cards.values())
    roundtrip(s)


def test_founding_cold_first_chapter_hand_permission_and_actual_free_cast(cards,tmp_path):
    from tests.test_rules_exile_cast_outcomes45_cold import fresh

    s,source=gameplay.founding_chapter(cards,1,first_hand=['Giant Growth'])
    spell=next(c for c in s.state.cards.values() if c.name=='Giant Growth' and c.zone=='p1:hand')
    bear=next(c for c in s.state.cards.values() if c.name=='Grizzly Bears' and c.zone=='p1:battlefield')
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'hand.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[spell.id]})
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'target.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[bear.id]})
    assert s.state.cards[spell.id].zone=='p1:graveyard'
    assert s.state.cards[source.id].zone=='p1:battlefield'
    roundtrip(s)


def test_founding_cold_third_chapter_original_exile_paid_copy_and_payment_cancel(cards,tmp_path):
    from tests.test_rules_exile_cast_outcomes45_cold import fresh

    s,source=gameplay.founding_chapter(cards,3,third_graveyard=['Divination'])
    original=next(c for c in s.state.cards.values() if c.name=='Divination' and c.zone=='p1:graveyard')
    mana(s,U=1,C=2)
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'exile.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[original.id]})
    copy=s.state.rules.decision.options[0].card_id
    act(s,'p1',type='clear_mana',player='p1')
    act(s,'p1',type='set_prefs',payment='self')
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'copy.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':[copy]})
    assert s.state.rules.decision.resume['step']=='pay_mana'
    d=s.state.rules.decision
    s=fresh(s,cards,tmp_path/'cancel.json',d.player,{'type':'choose','decision_id':d.id,'option_ids':['cancel']})
    assert copy not in s.state.cards
    assert s.state.cards[original.id].zone=='p1:exile'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.rules.free_cast_then is None
    roundtrip(s)


def test_founding_first_chapter_decline_keeps_hand_and_creates_no_later_permission(cards):
    s,source=gameplay.founding_chapter(cards,1,first_hand=['Giant Growth'])
    spell=next(c for c in s.state.cards.values() if c.name=='Giant Growth' and c.zone=='p1:hand')
    answer(s,[])
    assert s.state.cards[spell.id].zone=='p1:hand'
    assert s.state.cards[source.id].zone=='p1:battlefield'
    assert s.state.rules.free_cast_then is None and not s.state.rules.permissions
    roundtrip(s)


def test_founding_all_three_actual_chapters_free_hand_then_mill_then_paid_copy(cards):
    from tests.test_rules_wave30m_durations import to_phase

    s,source=gameplay.founding_chapter(cards,1,first_hand=['Giant Growth'])
    spell=next(c for c in s.state.cards.values() if c.name=='Giant Growth' and c.zone=='p1:hand')
    bear=next(c for c in s.state.cards.values() if c.name=='Grizzly Bears' and c.zone=='p1:battlefield')
    answer(s,[spell.id])
    answer(s,[bear.id])
    for turn in (4,7):
        to_phase(s,'draw',turn=turn)
        for _ in range(20):
            if s.state.rules.decision is not None:
                break
            act(s,s.state.rules.priority,type='pass_priority')
        assert s.state.rules.decision is not None
        if turn==4:
            answer(s,['p2'])
            assert s.state.cards[source.id].counters.get('lore')==2
        else:
            mana(s,G=1)
            assert spell.id in [o.card_id for o in s.state.rules.decision.options]
            answer(s,[spell.id])
            assert s.state.rules.decision.resume['step']=='free_cast_pick'
            copy=s.state.rules.decision.options[0].card_id
            answer(s,[copy])
            if s.state.rules.decision is not None:
                answer(s,[bear.id])
            assert copy not in s.state.cards
    assert s.state.cards[spell.id].zone=='p1:exile'
    assert s.state.cards[source.id].zone=='p1:graveyard'
    assert s.state.rules.free_cast_then is None
    roundtrip(s)
