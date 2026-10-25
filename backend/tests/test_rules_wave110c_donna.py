"""Wave 110C: Donna Noble (702.95b, 603.2): damage dealt to her or to the creature she is paired with is dealt to a target opponent as well."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.wave110c_kit import answer, build, cast, check, life, make_db, mana, put, real

TEXT = ("Soulbond (You may pair this creature with another unpaired creature when either enters. They remain paired for as long as you control both of them.)\n"
        "Whenever Donna Noble or a creature it's paired with is dealt damage, Donna Noble deals that much damage to target opponent.\n"
        "Doctor's companion (You can have two commanders if the other is the Doctor.)")
EXTRA = [real("Donna Noble", "{2}{R}", 3, "Legendary Creature — Human", TEXT, ("3", "3"), "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Donna Noble")).level == "FULL"


@pytest.mark.parametrize("victim, loss", [("Courser of Kruphix", 3), ("Foundry Inspector", 0)])
def test_damage_to_the_paired_creature_is_copied_to_an_opponent(cards, victim, loss):
    s = build(cards, ["Donna Noble", "Courser of Kruphix", "Foundry Inspector", "Lightning Bolt"], [])
    put(s, "Foundry Inspector")
    put(s, "Courser of Kruphix")
    mana(s, R=1, C=2)
    cast(s, "Donna Noble")
    answer(s, "yes", [next(c.id for c in s.state.cards.values() if c.name == "Courser of Kruphix")])
    assert len(s.state.rules.pairs) == 2
    mana(s, R=1)
    cast(s, "Lightning Bolt", [next(c.id for c in s.state.cards.values() if c.name == victim)])
    answer(s, "p2")
    assert life(s, "p2") == 40 - loss
    check(s)
