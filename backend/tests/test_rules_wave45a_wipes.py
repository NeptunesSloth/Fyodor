"""Wave 45A: a wrath measured by one target's power (CR 2026-09-25), real Oracle text (tests/fixtures/wave45a_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 608.2b, 115.1: "Destroy all creatures with power greater than target creature's power." (Fell the Mighty [1490]), "Choose target creature you control. Destroy all
  creatures with power less than that creature's power." (Mandate of Abaddon [4836]) - the target's power as the spell resolves; the creatures destroyed aren't
  targeted (a hexproof one is destroyed too: Fell the Mighty's ruling 2014-11-07), and the target itself is never destroyed.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of
from tests.wave45a_kit import cast, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", ["Fell the Mighty", "Mandate of Abaddon"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def table(cards, spell):
    s = build(cards, [spell, "Grizzly Bears", "Hill Giant"], ["Shivan Dragon", "Goblin Piker"])
    for name, pid in (("Grizzly Bears", "p1"), ("Hill Giant", "p1"), ("Shivan Dragon", "p2"), ("Goblin Piker", "p2")):
        put(s, name, pid)
    to_hand(s, spell)
    return s


def test_fell_the_mighty_destroys_the_creatures_with_more_power_than_the_target(cards):
    s = table(cards, "Fell the Mighty")
    mana(s, W=1, C=4)
    cast(s, "Fell the Mighty", targets=[card_named(s, "Grizzly Bears").id])
    # power 2 is the target's: the 3/3 and the 5/5 go, the 2/2 itself and the 2/1 stay
    assert zone_of(s, "Hill Giant") == "p1:graveyard" and zone_of(s, "Shivan Dragon", "p2") == "p2:graveyard"
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and zone_of(s, "Goblin Piker", "p2") == "p2:battlefield"
    check(s)


def test_fell_the_mighty_destroys_nothing_when_the_target_has_the_most_power(cards):
    s = table(cards, "Fell the Mighty")
    mana(s, W=1, C=4)
    cast(s, "Fell the Mighty", targets=[card_named(s, "Shivan Dragon", "p2").id])
    assert all(zone_of(s, n, p).endswith("battlefield") for n, p in (("Grizzly Bears", "p1"), ("Hill Giant", "p1"), ("Shivan Dragon", "p2"), ("Goblin Piker", "p2")))
    check(s)


def test_fell_the_mighty_cannot_be_cast_with_no_creature_to_target(cards):
    s = build(cards, ["Fell the Mighty"], [])
    to_hand(s, "Fell the Mighty")
    mana(s, W=1, C=4)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Fell the Mighty").id)  # 601.2c
    check(s)


def test_mandate_of_abaddon_destroys_the_creatures_with_less_power_than_the_chosen_one(cards):
    s = table(cards, "Mandate of Abaddon")
    mana(s, B=1, C=3)
    cast(s, "Mandate of Abaddon", targets=[card_named(s, "Hill Giant").id])
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard" and zone_of(s, "Goblin Piker", "p2") == "p2:graveyard"
    assert zone_of(s, "Hill Giant") == "p1:battlefield" and zone_of(s, "Shivan Dragon", "p2") == "p2:battlefield"
    check(s)


def test_that_creatures_power_with_no_chosen_target_stays_manual():
    from tests.test_rules_scripts import ch as characteristics

    # (which creature is "that creature" in a trigger with no target? the attacker, maybe - not read)
    chs = characteristics("Test Card", "Enchantment", "Whenever a creature attacks, destroy all creatures with power less than that creature's power.")
    assert coverage.of_characteristics(chs).level != "FULL"


# ---- Parting Gust [1644] ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("gift", [False, True])
def test_parting_gust_returns_the_creature_at_the_next_end_step_only_when_the_gift_was_not_promised(cards, gift):
    from tests.test_rules_wave34b_activated import settle, stops, to_phase

    s = build(cards, ["Parting Gust"], ["Grizzly Bears"])
    stops(s)
    bears = put(s, "Grizzly Bears", "p2")
    c = to_hand(s, "Parting Gust")
    mana(s, W=2)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bears.id], optional_costs=[f"{c.id}:gift"] if gift else [])
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:exile"
    to_phase(s, "end")
    settle(s)
    if gift:  # 702.174: the gift was promised: Bob got a tapped Fish and his Bears stay exiled
        assert zone_of(s, "Grizzly Bears", "p2") == "p2:exile"
        assert any(c.is_token and c.name == "Fish" and c.controller == "p2" for c in s.state.cards.values())
    else:  # a new object, with a +1/+1 counter (the ruling 2024-07-26: it returns as a new object)
        now = card_named(s, "Grizzly Bears", "p2")
        assert now.zone == "p2:battlefield" and now.counters.get("+1/+1") == 1
    check(s)
