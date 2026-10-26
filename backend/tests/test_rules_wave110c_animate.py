"""Wave 110C: Animate Artifact. 613.1d / 613.4b (becomes an artifact creature, base power and toughness = mana value), 613.8 (it depends on whatever else makes the
artifact a creature), 613.6 (what it affects is fixed when it begins to apply)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.wave9c_kit import pt
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, real

ANIMATE = "Enchant artifact\nAs long as enchanted artifact isn't a creature, it's an artifact creature with power and toughness each equal to its mana value."
EXTRA = [real("Animate Artifact", "{3}{U}", 4, "Enchantment — Aura", ANIMATE, None, "U"),
         real("Test Rock", "{3}", 3, "Artifact", "{T}: Add {C}.", None, ""),
         real("Test Golem", "{5}", 5, "Artifact Creature — Golem", "", ("2", "2"), ""),
         real("Test Cart", "{4}", 4, "Artifact — Vehicle", "Crew 1", ("3", "3"), ""),
         real("Test Pilot", "{G}", 1, "Creature — Human", "", ("1", "1"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Animate Artifact")).level == "FULL"


def enchant(cards, target):
    s = build(cards, ["Animate Artifact", target, "Test Pilot"])
    art = put(s, target)
    mana(s, U=1, C=3)
    cast(s, "Animate Artifact", [art.id])
    answer(s)
    return s, art


def test_noncreature_artifact_becomes_a_creature_with_pt_equal_to_its_mana_value(cards):
    s, _ = enchant(cards, "Test Rock")
    assert pt(s, "Test Rock") == (3, 3)
    check(s)


def test_an_artifact_creature_is_left_alone(cards):  # the condition fails: its own 2/2 stays
    s, _ = enchant(cards, "Test Golem")
    assert pt(s, "Test Golem") == (2, 2)


def test_it_stops_when_the_aura_leaves(cards):
    s, art = enchant(cards, "Test Rock")
    from tests.game_helpers import act
    from tests.wave110c_kit import card_named

    act(s, "p1", type="move", card_ids=[card_named(s, "Animate Artifact").id], to={"player": "p1", "zone": "graveyard"})
    from app.rules.plan import Plan

    assert not Plan(s.state, "p1", s.cards, None).ch(s.state.cards[art.id]).is_creature


def test_crewed_vehicle_keeps_its_own_pt_613_8(cards):
    """A Vehicle is a noncreature artifact: the Aura makes it 4/4. Crewed, the crew effect makes it a creature, and Animate Artifact depends on that (613.8a): it
    applies after, finds a creature and does nothing, so the Vehicle is its printed 3/3 until end of turn."""
    from tests.game_helpers import act
    from tests.wave110d_kit import ability

    s, cart = enchant(cards, "Test Cart")
    assert pt(s, "Test Cart") == (4, 4)
    pilot = put(s, "Test Pilot")
    act(s, "p1", type="activate_ability", card_id=cart.id, ability=ability(s, cart, "Crew"))
    answer(s, pilot.id)
    assert pt(s, "Test Cart") == (3, 3)


def test_aura_cast_on_an_already_crewed_vehicle_does_nothing_613_8(cards):
    """The crew effect is older than the Aura, yet Animate Artifact depends on it (613.8a), so the crewed Vehicle is a creature when the Aura applies."""
    from tests.game_helpers import act
    from tests.wave110d_kit import ability

    s = build(cards, ["Animate Artifact", "Test Cart", "Test Pilot"])
    cart, pilot = put(s, "Test Cart"), put(s, "Test Pilot")
    act(s, "p1", type="activate_ability", card_id=cart.id, ability=ability(s, cart, "Crew"))
    answer(s, pilot.id)
    mana(s, U=1, C=3)
    cast(s, "Animate Artifact", [cart.id])
    answer(s)
    assert pt(s, "Test Cart") == (3, 3)
