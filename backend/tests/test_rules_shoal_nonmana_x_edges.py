"""Native tax, additional-cost and cold continuation edges for Shoal."""
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import alt_costs
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put, roundtrip
from tests.test_rules_shoal_nonmana_x import begin, game
from tests.test_rules_shoal_nonmana_x import cards as cards


@pytest.mark.parametrize('paid', [False, True])
def test_native_thalia_tax_still_has_to_be_paid(cards, paid):
    s = game(cards)
    put(s, 'Thalia, Guardian of Thraben', 'battlefield', 'p2')
    white = put(s, 'Selfless Squire', 'hand')
    if paid:
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
        shoal = begin(s, 4)
        receipt = s.state.rules.payments[s.state.rules.object_id(shoal.id)]
        assert receipt.mana_spent == {'C': 1} and receipt.exiled == [white.id]
    else:
        with pytest.raises(ActionError):
            begin(s, 4)
        assert s.state.cards[white.id].zone == 'p1:hand' and not s.state.zones.get('stack')


@pytest.mark.parametrize('paid', [False, True])
def test_splice_additional_mana_cost_remains_real_and_atomic(cards, paid):
    s = game(cards)
    white = put(s, 'Selfless Squire', 'hand')
    ritual = put(s, 'Desperate Ritual', 'hand')
    shoal = put(s, 'Shining Shoal', 'hand')
    if paid:
        act(s, 'p1', type='add_mana', player='p1', mana={'C': 1, 'R': 1})
    wait_priority(s, 'p1')
    plan = Plan(s.state, 'p1', cards, None)
    offer = alt_costs.offers(plan.state, 'p1', plan.state.cards[shoal.id], plan.ch(plan.state.cards[shoal.id]), plan.info)[0]
    data = dict(type='cast_spell', card_id=shoal.id, targets=['p2'], x_value=4, alt_cost=offer.key, splice=[ritual.id], sources=[])
    if paid:
        act(s, 'p1', **data)
        receipt = s.state.rules.payments[s.state.rules.object_id(shoal.id)]
        assert receipt.mana_spent == {'C': 1, 'R': 1} and receipt.exiled == [white.id]
        assert receipt.spliced_names == ['Desperate Ritual']
        assert s.state.cards[ritual.id].zone == 'p1:hand'
    else:
        with pytest.raises(ActionError):
            act(s, 'p1', **data)
        assert all(s.state.cards[c.id].zone == 'p1:hand' for c in (white, ritual, shoal))
        assert not s.state.zones.get('stack')


def test_saved_private_choice_revalidates_x_and_old_hand_object(cards):
    s = game(cards)
    first = put(s, "Acolyte's Reward", 'hand')
    other = put(s, 'Samite Ministration', 'hand')
    shoal = begin(s, 2)
    roundtrip(s)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[other.id])
    receipt = s.state.rules.payments[s.state.rules.object_id(shoal.id)]
    assert receipt.x == 2 and receipt.exiled == [other.id]
    assert receipt.exiled_facts[0].mana_value == 2 and receipt.exiled_facts[0].colors == ['W']
    assert s.state.cards[first.id].zone == 'p1:hand'


def test_positive_high_x_comes_from_real_multicolor_white_card(cards):
    s = game(cards)
    white = put(s, 'Progenitus', 'hand')
    shoal = begin(s, 10)
    receipt = s.state.rules.payments[s.state.rules.object_id(shoal.id)]
    assert receipt.x == 10 and not receipt.mana_spent and receipt.exiled == [white.id]
    assert receipt.exiled_facts[0].mana_value == 10 and 'W' in receipt.exiled_facts[0].colors


def test_wrong_selected_card_and_departed_hand_card_cannot_pay(cards):
    s = game(cards)
    first = put(s, "Acolyte's Reward", 'hand')
    other = put(s, 'Samite Ministration', 'hand')
    wrong = put(s, 'Selfless Squire', 'hand')
    shoal = begin(s, 2)
    d = s.state.rules.decision
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[wrong.id])
    assert not s.state.zones.get('stack') and s.state.cards[shoal.id].zone == 'p1:hand'
    act(s, 'p1', type='move', card_ids=[first.id], to={'player': 'p1', 'zone': 'graveyard'})
    d = s.state.rules.decision
    with pytest.raises(ActionError):
        act(s, 'p1', type='choose', decision_id=d.id, option_ids=[first.id])
    assert s.state.cards[other.id].zone == 'p1:hand' and not s.state.zones.get('stack')


def test_tax_is_not_spent_when_private_payment_is_cancelled(cards):
    s = game(cards)
    put(s, 'Thalia, Guardian of Thraben', 'battlefield', 'p2')
    first = put(s, "Acolyte's Reward", 'hand')
    other = put(s, 'Samite Ministration', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': 1})
    shoal = begin(s, 2)
    d = s.state.rules.decision
    act(s, 'p1', type='choose', decision_id=d.id, option_ids=[])
    assert all(s.state.cards[c.id].zone == 'p1:hand' for c in (shoal, first, other))
    assert s.state.players['p1'].mana.get('C') == 1 and not s.state.zones.get('stack')


@pytest.mark.parametrize('x', [0, 4])
def test_ordinary_cast_keeps_native_x_mana_cost(cards, x):
    s = game(cards)
    shoal = put(s, 'Shining Shoal', 'hand')
    act(s, 'p1', type='add_mana', player='p1', mana={'C': x, 'W': 2})
    wait_priority(s, 'p1')
    act(s, 'p1', type='cast_spell', card_id=shoal.id, targets=['p2'], x_value=x, sources=[])
    receipt = s.state.rules.payments[s.state.rules.object_id(shoal.id)]
    assert receipt.x == x and sum(receipt.mana_spent.values()) == x + 2 and not receipt.exiled


@pytest.mark.parametrize('x', [0, 4])
def test_free_cast_remains_zero_x_and_cannot_use_nonzero_marker(cards, x):
    s = game(cards)
    put(s, 'Omniscience', 'battlefield')
    shoal = put(s, 'Shining Shoal', 'hand')
    wait_priority(s, 'p1')
    if x:
        with pytest.raises(ActionError):
            act(s, 'p1', type='cast_spell', card_id=shoal.id, targets=['p2'], x_value=x, free=True, sources=[])
        assert not s.state.zones.get('stack')
    else:
        act(s, 'p1', type='cast_spell', card_id=shoal.id, targets=['p2'], x_value=0, free=True, sources=[])
        receipt = s.state.rules.payments[s.state.rules.object_id(shoal.id)]
        assert receipt.x == 0 and not receipt.mana_spent and not receipt.exiled
