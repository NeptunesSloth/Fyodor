"""-- as long as (wave 20B) -- conditional statics that change the source's own types, read against CR 604.2, 611.3a, 613.1d, 613.4b:
"As long as there are fewer than eight cards in your graveyard, ~ isn't a creature." (Warring Triad), "As long as ~ has a slumber counter on it,
it's a land." (Arixmethes), "… it's a 0/0 creature in addition to its other types and it has annihilator 2." (Idol of False Gods), "… it's an
artifact creature." (War Balloon), "~ has indestructible as long as it attacked this turn." (Agent Frank Horrigan), "Each land gets +2/+2 as long
as it's a creature." (Earth Surge), "~ has trample as long as it has two or fewer oil counters on it. Otherwise, it has hexproof." (Evolved
Spinoderm). Oracle text from the card database."""

from __future__ import annotations

from tests.game_helpers import act
from tests.test_rules_combat import attack, automate, creature, table
from tests.test_rules_effects import replay_matches
from tests.test_rules_statics import ch, token
from tests.test_rules_wave4h_activation_costs import roundtrip, set_counters

TRIAD = "As long as there are fewer than eight cards in your graveyard, ~ isn't a creature."
ARIXMETHES = "As long as ~ has a slumber counter on it, it's a land."
IDOL = "As long as ~ has eight or more +1/+1 counters on it, it's a 0/0 creature in addition to its other types and it has annihilator 2."
BALLOON = "As long as ~ has three or more fire counters on it, it's an artifact creature."
FRANK = "~ has indestructible as long as it attacked this turn."
SURGE = "Each land gets +2/+2 as long as it's a creature."
SPINODERM = "~ has trample as long as it has two or fewer oil counters on it. Otherwise, it has hexproof."


def test_not_a_creature_while_fewer_than_eight_cards_in_the_graveyard(cards):
    s = table(cards)
    god = token(s, "p1", "Triad", "Legendary Artifact Creature — God", TRIAD, "3/3")
    automate(s)
    assert "Creature" not in ch(s, cards, god).types and "Artifact" in ch(s, cards, god).types
    act(s, "p1", type="move", card_ids=list(s.state.zones["p1:library"])[:8], to={"zone": "graveyard"})
    assert "Creature" in ch(s, cards, god).types
    roundtrip(s)


def test_it_is_a_land_while_it_has_a_counter(cards):
    s = table(cards)
    kraken = token(s, "p1", "Arixmethes", "Legendary Creature — Kraken", ARIXMETHES, "12/12")
    set_counters(s, kraken, "slumber", 2)
    automate(s)
    got = ch(s, cards, kraken)
    assert got.types == frozenset({"Land"}) and "Kraken" not in got.subtypes and "Legendary" in got.supertypes  # 205.1a
    set_counters(s, kraken, "slumber", 0)
    assert ch(s, cards, kraken).types == frozenset({"Creature"})
    roundtrip(s)


def test_creature_in_addition_with_base_power_and_keyword(cards):
    s = table(cards)
    idol = token(s, "p1", "Idol", "Kindred Artifact — Eldrazi", IDOL)
    set_counters(s, idol, "+1/+1", 7)
    automate(s)
    assert "Creature" not in ch(s, cards, idol).types
    set_counters(s, idol, "+1/+1", 8)
    got = ch(s, cards, idol)
    assert {"Artifact", "Creature"} <= got.types and "Eldrazi" in got.subtypes and got.pt == (8, 8)  # 205.1b, 613.4b: 0/0 plus counters
    assert any("Annihilator 2" in a.text for a in got.abilities)
    roundtrip(s)


def test_vehicle_becomes_an_artifact_creature_with_counters(cards):
    s = table(cards)
    van = token(s, "p1", "Balloon", "Artifact — Vehicle", BALLOON, "1/4")
    set_counters(s, van, "fire", 2)
    automate(s)
    assert "Creature" not in ch(s, cards, van).types
    set_counters(s, van, "fire", 3)
    assert ch(s, cards, van).types == frozenset({"Artifact", "Creature"}) and "Vehicle" in ch(s, cards, van).subtypes
    roundtrip(s)


def test_indestructible_once_it_attacked_this_turn(cards):
    s = table(cards)
    frank = creature(s, "p1", "Frank", "2/2", FRANK)
    automate(s)
    assert "indestructible" not in ch(s, cards, frank).keywords
    attack(s, (frank, "p2"))
    assert "indestructible" in ch(s, cards, frank).keywords  # 508.1: declared as an attacker this turn
    replay_matches(s)


def test_each_land_that_is_a_creature_gets_the_bonus(cards):
    s = table(cards)
    token(s, "p1", "Earth Surge", "Enchantment", SURGE)
    dryad = token(s, "p2", "Dryad Land", "Land Creature — Dryad", "", "1/1")
    plain = token(s, "p2", "Plain Land", "Land", "")
    automate(s)
    assert ch(s, cards, dryad).pt == (3, 3) and ch(s, cards, plain).pt is None
    roundtrip(s)


def test_trample_with_few_oil_counters_otherwise_hexproof(cards):
    s = table(cards)
    beast = creature(s, "p1", "Spinoderm", "5/5", SPINODERM)
    set_counters(s, beast, "oil", 2)
    automate(s)
    assert "trample" in ch(s, cards, beast).keywords and "hexproof" not in ch(s, cards, beast).keywords
    set_counters(s, beast, "oil", 3)
    assert "hexproof" in ch(s, cards, beast).keywords and "trample" not in ch(s, cards, beast).keywords
    roundtrip(s)
