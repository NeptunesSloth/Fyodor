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


def test_granted_annihilator_works_when_it_attacks(cards):
    s = table(cards)
    idol = token(s, "p1", "Idol", "Kindred Artifact — Eldrazi", IDOL)
    set_counters(s, idol, "+1/+1", 8)
    for i in range(4):
        token(s, "p2", f"Rock{i}", "Token Artifact — Rock")
    automate(s)
    before = len(s.state.zones["p2:battlefield"])
    attack(s, (idol, "p2"))
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.player == "p2":
            act(s, "p2", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: d.min_choices])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    for _ in range(6):
        if s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    assert len(s.state.zones["p2:battlefield"]) == before - 2  # 702.86a: annihilator 2
    replay_matches(s)


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


NEWSIE = "As long as there are five or more mana values among cards in your graveyard, this creature gets +1/+1 and has lifelink."
DJINN = "~ gets -2/-2 as long as blue is the most common color among all permanents or is tied for most common."
SECRETKEEPER = "As long as you have more cards in hand than each opponent, this creature gets +2/+2 and has flying."


def test_five_mana_values_among_cards_in_your_graveyard(cards):
    s = table(cards)
    act(s, "p1", type="configure", allow_test_objects=True)
    newsie = token(s, "p1", "Newsie", "Creature — Human Rogue", NEWSIE, "1/1")
    automate(s)
    for name in ("Sol Ring", "Counterspell", "Murder", "Wrath of God"):  # mana values 1, 2, 3, 4
        act(s, "p1", type="spawn_card", card_id=cards.resolve(name)["id"])
    spawned = [c.id for c in s.state.cards.values() if c.test_object]
    act(s, "p1", type="move", card_ids=spawned[:3], to={"zone": "graveyard"})
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "graveyard"})  # mana values 0, 1, 2, 3: four of them
    assert ch(s, cards, newsie).pt == (1, 1)
    act(s, "p1", type="move", card_ids=spawned[3:], to={"zone": "graveyard"})  # 0, 1, 2, 3, 4
    assert ch(s, cards, newsie).pt == (2, 2) and "lifelink" in ch(s, cards, newsie).keywords
    roundtrip(s)


def test_most_common_color_among_all_permanents(cards):
    s = table(cards)
    djinn = creature(s, "p1", "Djinn", "4/5", DJINN)
    automate(s)
    assert ch(s, cards, djinn).pt == (4, 5)  # (a colorless token: nothing is blue yet)
    for who, name, color in (("p2", "Fish", "U"), ("p2", "Imp", "B"), ("p2", "Imp 2", "B")):
        act(s, who, type="create_token", player=who, token={"name": name, "type_line": "Token Creature — Test", "power": "1",
                                                            "toughness": "1", "colors": [color]})
        if name == "Fish":
            assert ch(s, cards, djinn).pt == (2, 3)  # 105.2: one blue permanent, no other color has more
    assert ch(s, cards, djinn).pt == (4, 5)  # black is now the most common
    roundtrip(s)


def test_more_cards_in_hand_than_each_opponent(cards):
    s = table(cards)
    keeper = creature(s, "p1", "Secretkeeper", "1/1", SECRETKEEPER)
    automate(s)
    assert len(s.state.zones["p1:hand"]) == len(s.state.zones["p2:hand"]) and ch(s, cards, keeper).pt == (1, 1)
    act(s, "p1", type="move", card_ids=[s.state.zones["p1:library"][0]], to={"zone": "hand"})
    assert ch(s, cards, keeper).pt == (3, 3) and "flying" in ch(s, cards, keeper).keywords
    roundtrip(s)
