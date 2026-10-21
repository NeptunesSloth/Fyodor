"""Native casting additional-cost shuffle boundary; no parser or payment adapters."""
import pytest

from app.rules import alt_costs, characteristics
from tests import test_rules_exile_cast_outcomes45_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_library_look import settle

cards=gameplay.cards


@pytest.mark.parametrize('zone',['hand','library'])
def test_native_emerge_sacrifice_shuffle_keeps_announced_spell_out_of_library(cards,zone):
    s=gameplay.setup(cards,'Mystic Forge','Elder Deep-Fiend','Progenitus')
    put(s,'Mystic Forge','battlefield')
    victim=put(s,'Progenitus','battlefield')
    spell=put(s,'Elder Deep-Fiend',zone)
    choice=next(o.key for o in alt_costs.offers(s.state,'p1',spell,characteristics.of(spell,cards),cards) if o.tag=='emerge')
    mana(s,U=2)
    act(s,'p1',type='cast_spell',card_id=spell.id,alt_cost=choice,cost_choices=[{'component':0,'cards':[victim.id]}])
    settle(s)
    for _ in range(4):
        d=s.state.rules.decision
        if d is None:
            break
        assert d.min_choices==0
        act(s,d.player,type='choose',decision_id=d.id,option_ids=[])
        settle(s)
    actual=[c for c in s.state.cards.values() if c.name=='Elder Deep-Fiend' and c.owner=='p1']
    assert len(actual)==1 and actual[0].zone=='p1:battlefield'
    assert any(c.name=='Progenitus' and c.zone=='p1:library' for c in s.state.cards.values())
    roundtrip(s)


@pytest.mark.xfail(strict=True,reason='Known401.5 frontier: FULL Mystic Forge exposes next top during an unfinished emerge replacement-payment choice')
def test_native_top_spell_replacement_payment_choice_does_not_expose_next_top(cards):
    from app.game.visibility import can_see

    s=gameplay.setup(cards,'Mystic Forge','Elder Deep-Fiend','Progenitus','Rest in Peace')
    put(s,'Mystic Forge','battlefield')
    put(s,'Rest in Peace','battlefield')
    victim=put(s,'Progenitus','battlefield')
    next_top=put(s,'Divination','library')
    spell=put(s,'Elder Deep-Fiend','library')
    choice=next(o.key for o in alt_costs.offers(s.state,'p1',spell,characteristics.of(spell,cards),cards) if o.tag=='emerge')
    mana(s,U=2)
    act(s,'p1',type='cast_spell',card_id=spell.id,alt_cost=choice,cost_choices=[{'component':0,'cards':[victim.id]}])
    d=s.state.rules.decision
    assert d is not None
    assert d.resume['step']=='zone_replace_order'
    assert s.state.cards[spell.id].zone=='stack'
    assert not can_see(s.state,s.state.cards[next_top.id],'p1')
    assert not can_see(s.state,s.state.cards[next_top.id],'p2')
    roundtrip(s)
