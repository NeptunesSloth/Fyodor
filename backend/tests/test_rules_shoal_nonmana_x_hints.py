"""The actual native hand hints expose the positive-MV nonmana-X alternative."""
from __future__ import annotations

from app.rules import view
from tests.test_rules_bandmate_references import wait_priority
from tests.test_rules_designations import put
from tests.test_rules_shoal_nonmana_x import cards as cards
from tests.test_rules_shoal_nonmana_x import game


def test_native_hand_hint_only_positive_white_card_zero_mana(cards):
    s = game(cards)
    shoal = put(s, 'Shining Shoal', 'hand')
    wait_priority(s, 'p1')
    assert shoal.id not in view.hints(s.state, 'p1', cards).get('alt_castable', {})
    put(s, 'Selfless Squire', 'hand')
    alternatives = view.hints(s.state, 'p1', cards)['alt_castable'][shoal.id]
    assert len(alternatives) == 1 and alternatives[0]['x'] is True
    assert set(alternatives[0]) == {'id', 'label', 'x'}
    assert not s.state.players['p1'].mana
