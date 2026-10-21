"""Native primitive receipts, explicitly separate from printed-card gameplay proofs."""
from __future__ import annotations

import random

from app.game.session import GameSession
from app.game.state import GameState
from app.rules import replace
from app.rules.plan import Plan
from tests import test_rules_exile_outcomes42_foundation as gameplay
from tests.game_helpers import act
from tests.test_rules_designations import put
from tests.test_rules_library_look import settle

cards=gameplay.cards
staged=gameplay.staged


def test_native_gain_vector_actual_tainted_remedy_conversions_keep_one_typed_loss_operation(cards):
    s=gameplay.setup(cards,'Tainted Remedy','Ob Nixilis, Captive Kingpin')
    put(s,'Tainted Remedy','battlefield')
    kingpin=put(s,'Ob Nixilis, Captive Kingpin','battlefield')
    plan=Plan(s.state,'p1',cards,random.Random(42))
    assert replace.gain_life(plan,[('p2',1),('p3',1)],actor='p1',then={'do':'noop'})
    losses=[e for e in plan.rules.events if e.kind=='life_loss']
    assert [(e.player,e.amount) for e in losses]==[('p2',1),('p3',1)]
    assert losses[0].group==losses[1].group>0
    s=GameSession(GameState.model_validate_json(plan.state.model_dump_json()),cards=cards)
    act(s,'p1',type='pass_priority')
    settle(s)
    assert s.state.players['p2'].life==39 and s.state.players['p3'].life==39
    assert s.state.cards[kingpin.id].counters.get('+1/+1')==1


def test_native_paused_gain_operation_reserves_id_before_nested_loss_and_survives_save(cards):
    s=gameplay.setup(cards,'Tainted Remedy','Boon Reflection')
    put(s,'Tainted Remedy','battlefield')
    put(s,'Boon Reflection','battlefield','p2')
    plan=Plan(s.state,'p1',cards,random.Random(42))
    assert not replace.gain_life(plan,[('p2',1),('p3',1)],actor='p1',then={'do':'noop'})
    d=plan.rules.decision
    assert d is not None and d.resume['site']=='life'
    operation=d.resume['request']['operation']
    assert operation==plan.rules.next_life_operation>0
    # Native nested loss reserves a distinct receipt while the outer operation is paused.
    assert replace.lose_life(plan,[('p1',1)],actor='p1')
    assert plan.rules.next_life_operation>operation
    nested=next(e for e in plan.rules.events if e.kind=='life_loss' and e.player=='p1')
    assert nested.group!=operation
    restored=GameState.model_validate_json(plan.state.model_dump_json())
    s=GameSession(restored,cards=cards)
    d=s.state.rules.decision
    option=next(o for o in d.options if 'Boon Reflection' in o.label)
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[option.id])
    settle(s)
    losses=[e for e in s.state.rules.events if e.kind=='life_loss' and e.player in {'p2','p3'}]
    assert [(e.player,e.amount) for e in losses]==[('p2',2),('p3',1)]
    assert all(e.group==operation for e in losses)
