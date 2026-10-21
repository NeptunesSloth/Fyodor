"""Native stack-copy X and alternative-cost exclusivity for Shoal's cost."""
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import alt_costs
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_copy import resolve_top
from tests.test_rules_designations import put
from tests.test_rules_prevention_outcomes import activate
from tests.test_rules_shoal_nonmana_x import begin, game
from tests.test_rules_shoal_nonmana_x import cards as cards


def test_native_stack_copy_keeps_announced_x_without_another_exile(cards):
    s = game(cards)
    act(s, 'p1', type='set_prefs', hold_priority=True)
    copier = put(s, 'Lithoform Engine', 'battlefield')
    white = put(s, 'Selfless Squire', 'hand')
    shoal = begin(s, 4)
    original_oid = s.state.rules.object_id(shoal.id)
    activate(s, copier, 'Copy target instant', [shoal.id], resolve=False)
    resolve_top(s)
    d = s.state.rules.decision
    assert d and 'keep' in {o.id for o in d.options}
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=['keep'])
    copy_id = s.state.zones['stack'][-1]
    assert copy_id != shoal.id and s.state.rules.stack[copy_id].x == 4
    assert s.state.rules.stack[shoal.id].x == 4
    assert s.state.rules.payments[original_oid].exiled == [white.id]
    # Copies retain historical receipts; no second card was actually exiled.
    assert [c.id for c in s.state.cards.values() if c.zone.endswith(':exile')] == [white.id]


def test_cannot_combine_free_cast_and_the_exile_alternative(cards):
    s = game(cards)
    put(s, 'Omniscience', 'battlefield')
    white = put(s, 'Restore Balance', 'hand')
    shoal = put(s, 'Shining Shoal', 'hand')
    wait_priority(s, 'p1')
    plan = Plan(s.state, 'p1', cards, None)
    offer = alt_costs.offers(plan.state, 'p1', plan.state.cards[shoal.id], plan.ch(plan.state.cards[shoal.id]), plan.info)[0]
    with pytest.raises(ActionError, match='Only one alternative'):
        act(s, 'p1', type='cast_spell', card_id=shoal.id, targets=['p2'], x_value=0,
            alt_cost=offer.key, free=True, sources=[])
    assert s.state.cards[white.id].zone == 'p1:hand' and not s.state.zones.get('stack')
