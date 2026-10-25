"""Wave 110C: Spatial Binding (702.26a/b: a permanent that "can't phase out" stays in the untap step, until your next upkeep)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110c_kit import build, check, make_db, put, real

EXTRA = [real("Spatial Binding", "{3}{W}", 4, "Enchantment", "Pay 1 life: Until your next upkeep, target permanent can't phase out.", None, "W"),
         real("Test Phantom", "{1}{U}", 2, "Creature — Illusion", "Phasing", ("2", "2"), "U")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Spatial Binding")).level == "FULL"


@pytest.mark.parametrize("bound", [True, False])
def test_phasing_creature_stays_only_when_bound(cards, bound):
    s = build(cards, ["Spatial Binding", "Test Phantom"])
    b, p = put(s, "Spatial Binding"), put(s, "Test Phantom")
    if bound:
        act(s, "p1", type="activate_ability", card_id=b.id, ability=0, targets=[p.id])
        assert s.state.players["p1"].life == 39
    to_phase(s, "main1", 3)  # p1's next turn: untap step phasing
    assert s.state.cards[p.id].zone == ("p1:battlefield" if bound else "p1:phased")
    check(s)
