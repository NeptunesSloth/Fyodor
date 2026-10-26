"""Wave 110C Oubliette: 702.26 phasing, 610.3 until-leaves duration, the creature is tapped as it phases in (702.26d)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, real, zone

EXTRA = [real("Oubliette", "{1}{B}{B}", 3, "Enchantment",
              "When this enchantment enters, target creature phases out until this enchantment leaves the battlefield. Tap that creature as it phases in this way.", None, "B"),
         real("Naturalize", "{1}{G}", 2, "Instant", "Destroy target artifact or enchantment.", None, "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Oubliette")).level == "FULL"


def test_oubliette_phases_out_until_it_leaves_then_returns_tapped(cards):
    s = build(cards, ["Oubliette", "Naturalize"], ["Grizzly Bears"])
    bear = put(s, "Grizzly Bears", "p2")
    mana(s, B=2, C=1)
    o = cast(s, "Oubliette")
    answer(s, bear.id)
    assert zone(s, bear) == "p2:phased" and zone(s, o) == "p1:battlefield"
    check(s)
    mana(s, G=1, C=1)
    cast(s, "Naturalize", [o.id])
    answer(s)
    assert zone(s, bear) == "p2:battlefield" and s.state.cards[bear.id].tapped
    check(s)
