"""Native frozen source-object 'another' retarget counterexample, no card/parser adapters."""
import inspect

import pytest

from app.rules import coverage, targets
from tests import test_rules_delayed_blinks50 as gameplay
from tests.game_helpers import act
from tests.test_rules_bandmate_references import mana
from tests.test_rules_controller_tutors import answer
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_ordered_tutor_continuations import cast

cards=gameplay.cards
FIXED='sel = selectors.replace(sel, other=False)' in inspect.getsource(targets._selector_targets)


@pytest.mark.xfail(not FIXED,strict=True,reason='Structured another-selector currently excludes physical source after it became a new object')
def test_full_breaching_hippocamp_old_trigger_retargets_new_source_object_after_ephemerate(cards):
    assert coverage.of_card_data(cards.resolve('Breaching Hippocamp')).level=='FULL'
    s=gameplay.gameplay.setup(cards,'Breaching Hippocamp','Ephemerate','Deflecting Swat')
    bear=put(s,'Grizzly Bears','battlefield')
    source=put(s,'Breaching Hippocamp','hand')
    mana(s,U=1,C=3)
    act(s,'p1',type='cast_spell',card_id=source.id)
    while s.state.rules.decision is None:
        act(s,s.state.rules.priority,type='pass_priority')
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id])
    old=s.state.rules.object_id(source.id)
    original=next(k for k,e in s.state.rules.stack.items() if e.kind=='trigger' and e.source_object==old)
    cast(s,'Ephemerate',targets=[source.id])
    new=s.state.rules.object_id(source.id)
    assert new!=old
    d=s.state.rules.decision
    act(s,d.player,type='choose',decision_id=d.id,option_ids=[bear.id])
    newer=[k for k,e in s.state.rules.stack.items() if e.kind=='trigger' and e.source_object==new]
    while any(k in s.state.rules.stack for k in newer):
        act(s,s.state.rules.priority,type='pass_priority')
    assert original in s.state.rules.stack
    act(s,'p1',type='tap',card_ids=[source.id],tapped=True)
    cast(s,'Deflecting Swat',targets=[original])
    d=s.state.rules.decision
    assert d is not None and d.resume['step']=='choose_new_targets'
    assert source.id in [o.id for o in d.options]
    answer(s,[source.id])
    assert not s.state.cards[source.id].tapped
    roundtrip(s)
