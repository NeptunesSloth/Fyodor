"""The pod's Disa the Restless deck (tests/fixtures/soak_decks/disa_the_restless_disa_eldrazo.txt): its plan, with real Oracle text.

Maskwood Nexus or Conspiracy (naming Lhurgoyf) makes every creature card its owner has outside the battlefield a Lhurgoyf, so Disa puts
each creature card that goes to the graveyard from the library or the hand onto the battlefield (Entomb, Buried Alive, Tortured
Existence's discard). 603.10: a card put into a graveyard is checked as it is right after the event, with the continuous effects that
exist then (it isn't one of 603.10a's look-back triggers). Before this the trigger read the card's printed types and never saw the
Nexus. A creature that dies from the battlefield doesn't count ("from anywhere other than the battlefield").
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of

EXTRA = [
    real("Disa the Restless", "{2}{B}{R}{G}", 5, "Legendary Creature — Human Scout",
         "Whenever a Lhurgoyf permanent card is put into your graveyard from anywhere other than the battlefield, put it onto the "
         "battlefield.\nWhenever one or more creatures you control deal combat damage to a player, create a Tarmogoyf token.", ("5", "6"), "BGR"),
    real("Maskwood Nexus", "{4}", 4, "Artifact",
         "Creatures you control are every creature type. The same is true for creature spells you control and creature cards you own "
         "that aren't on the battlefield.\n{3}, {T}: Create a 2/2 blue Shapeshifter creature token with changeling. (It is every "
         "creature type.)"),
    real("Conspiracy", "{3}{B}{B}", 5, "Enchantment",
         "As this enchantment enters, choose a creature type.\nCreatures you control are the chosen type. The same is true for creature "
         "spells you control and creature cards you own that aren't on the battlefield.", None, "B"),
    real("Entomb", "{B}", 1, "Instant", "Search your library for a card, put that card into your graveyard, then shuffle.", None, "B"),
    real("Buried Alive", "{2}{B}", 3, "Sorcery",
         "Search your library for up to three creature cards, put them into your graveyard, then shuffle.", None, "B"),
    real("Tortured Existence", "{B}", 1, "Enchantment",
         "{B}, Discard a creature card: Return target creature card from your graveyard to your hand.", None, "B"),
    real("Ghalta, Primal Hunger", "{10}{G}{G}", 12, "Legendary Creature — Elder Dinosaur",
         "This spell costs {X} less to cast, where X is the total power of creatures you control.\nTrample (This creature can deal "
         "excess combat damage to the player or planeswalker it's attacking.)", ("12", "12"), "G"),
    real("Aggressive Mammoth", "{3}{G}{G}{G}", 6, "Creature — Elephant",
         "Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)\nOther creatures you "
         "control have trample.", ("8", "8"), "G"),
    real("Old Gnawbone", "{5}{G}{G}", 7, "Legendary Creature — Dragon",
         "Flying\nWhenever a creature you control deals combat damage to a player, create that many Treasure tokens.", ("7", "7"), "G"),
    real("Terminate", "{B}{R}", 2, "Instant", "Destroy target creature. It can't be regenerated.", None, "BR"),
]
NAMES = [c["name"] for c in EXTRA]
CREATURES = ["Ghalta, Primal Hunger", "Aggressive Mammoth", "Old Gnawbone"]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def settle(s, *names, limit=60):
    """Resolve everything. A card search or choice is answered with the options labelled ``names`` (as many as it takes), else its
    first options; a creature type is answered Lhurgoyf."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            labels = {o.id: (getattr(o, "label", "") or "") for o in d.options}
            want = [i for i, label in labels.items() if label == "Lhurgoyf" or any(label.startswith(n) for n in names)]
            want = list(dict.fromkeys(want))[: max(d.max_choices or 1, 1)] if want else [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=want)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, *picks, targets=()):
    c = to_hand(s, name)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=list(targets))
    settle(s, *picks)


def table(cards, *, nexus=True):
    s = build(cards, [*NAMES])
    put(s, "Disa the Restless")
    if nexus:
        put(s, "Maskwood Nexus")
    return s


@pytest.mark.parametrize("nexus", [True, False])
def test_entomb_puts_a_creature_onto_the_battlefield_only_with_the_nexus(cards, nexus):
    s = table(cards, nexus=nexus)
    mana(s, B=1)
    cast(s, "Entomb", "Ghalta, Primal Hunger")
    assert zone_of(s, "Ghalta, Primal Hunger") == ("p1:battlefield" if nexus else "p1:graveyard")
    check(s)


def test_buried_alive_puts_all_three_onto_the_battlefield(cards):
    s = table(cards)
    mana(s, B=1, C=2)
    cast(s, "Buried Alive", *CREATURES)
    assert [zone_of(s, n) for n in CREATURES] == ["p1:battlefield"] * 3
    check(s)


def test_conspiracy_naming_lhurgoyf_does_the_same(cards):
    s = table(cards, nexus=False)
    mana(s, B=3, C=3)
    cast(s, "Conspiracy")
    assert zone_of(s, "Conspiracy") == "p1:battlefield"
    cast(s, "Entomb", "Old Gnawbone")
    assert zone_of(s, "Old Gnawbone") == "p1:battlefield"
    check(s)


def test_a_discarded_creature_card_comes_back_too(cards):
    """Tortured Existence's cost: the discarded creature card goes from the hand to the graveyard (not from the battlefield), so Disa puts
    it onto the battlefield; the target is a creature that died (it stayed in the graveyard: from the battlefield)."""
    s = table(cards)
    existence = put(s, "Tortured Existence")
    ghalta = put(s, "Ghalta, Primal Hunger")
    mana(s, B=1, R=1)
    cast(s, "Terminate", targets=[ghalta.id])
    assert zone_of(s, "Ghalta, Primal Hunger") == "p1:graveyard"
    to_hand(s, "Aggressive Mammoth")
    mana(s, B=1)
    act(s, "p1", type="activate_ability", card_id=existence.id, ability=0, targets=[ghalta.id], sources=[])
    settle(s, "Aggressive Mammoth")
    assert zone_of(s, "Aggressive Mammoth") == "p1:battlefield"
    assert zone_of(s, "Ghalta, Primal Hunger") == "p1:hand"
    check(s)


def test_a_creature_that_dies_stays_in_the_graveyard(cards):
    s = table(cards)
    put(s, "Ghalta, Primal Hunger")
    ghalta = card_named(s, "Ghalta, Primal Hunger")
    mana(s, B=1, R=1)
    cast(s, "Terminate", targets=[ghalta.id])
    assert zone_of(s, "Ghalta, Primal Hunger") == "p1:graveyard"
    check(s)
