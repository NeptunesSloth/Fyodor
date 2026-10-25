"""Wave 110C group picks and entry answers: SOLDIER Military Program (608.2d, 122.1: up to two Soldiers chosen as it resolves), Nexus Mentality (122.8: cards
for the counters actually removed), Szat's Will (608.2h: the greatest power among the cards exiled), Meathook Massacre II (the paid return, 400.7),
Scorched Ruins / Lotus Vale (614.12, 118.12: sacrifice two untapped lands instead of entering)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import card_named, life
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, real, to_hand, zone

SOLDIER = ("At the beginning of combat on your turn, choose one. If you control a commander, you may choose both instead.\n"
           "• Create a 1/1 white Soldier creature token.\n• Put a +1/+1 counter on each of up to two Soldiers you control.")
NEXUS = ("Choose one. If you control a commander as you cast this spell, you may choose both instead.\n"
         "• Move all counters from target nonland permanent you control onto another target nonland permanent you control.\n"
         "• Remove all counters from target nonland permanent you control. Draw a card for each counter removed this way.")
SZAT = ("Choose one. If you control a commander as you cast this spell, you may choose both instead.\n"
        "• Each opponent sacrifices a creature they control with the greatest power.\n"
        "• Exile all opponents' graveyards, then create X 0/1 black Thrull creature tokens, where X is the greatest power among creature cards exiled this way.")
ENTER = ("If this land would enter, sacrifice two untapped lands instead. If you do, put this land onto the battlefield. "
         "If you don't, put it into its owner's graveyard.")
EXTRA = [real("SOLDIER Military Program", "{2}{W}", 3, "Enchantment", SOLDIER, None, "W"),
         real("Nexus Mentality", "{3}{U}", 4, "Instant", NEXUS, None, "U"),
         real("Szat's Will", "{4}{B}", 5, "Instant", SZAT, None, "B"),
         real("Meathook Massacre II", "{X}{X}{B}{B}{B}{B}", 4, "Legendary Enchantment",
              "Whenever a creature you control dies, you may pay 3 life. If you do, return that card under your control with a finality counter on it.\n"
              "Whenever a creature an opponent controls dies, they may pay 3 life. If they don't, return that card under your control with a finality counter on it.", None, "B"),
         real("Scorched Ruins", "", 0, "Land", ENTER, None),
         real("Lotus Vale", "", 0, "Land", ENTER + "\n{T}: Add three mana of any one color.", None),
         *[real(f"Soldier {x}", "{W}", 1, "Creature — Human Soldier", "", ("1", "1"), "W") for x in "ABC"],
         real("Big Zombie", "{3}{B}", 4, "Creature — Zombie", "", ("5", "5"), "B"),
         real("Little Zombie", "{B}", 1, "Creature — Zombie", "", ("2", "1"), "B")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["SOLDIER Military Program", "Nexus Mentality", "Szat's Will", "Meathook Massacre II", "Scorched Ruins", "Lotus Vale"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def counters(s, c):
    return s.state.cards[c.id].counters.get("+1/+1", 0)


def test_soldier_program_counters_on_up_to_two_chosen_soldiers(cards):
    """608.2d: the Soldiers are chosen as it resolves (not targeted); only the chosen two get a counter."""
    s = build(cards, ["SOLDIER Military Program", "Soldier A", "Soldier B", "Soldier C"])
    a, b, c = (put(s, f"Soldier {x}") for x in "ABC")
    mana(s, W=1, C=2)
    cast(s, "SOLDIER Military Program")
    answer(s)
    act(s, "p1", type="pass_priority")
    answer(s, "1:0", [a.id, c.id])
    assert (counters(s, a), counters(s, b), counters(s, c)) == (1, 0, 1)
    check(s)


def test_soldier_program_chooses_none_when_it_wants(cards):
    s = build(cards, ["SOLDIER Military Program", "Soldier A"])
    a = put(s, "Soldier A")
    put(s, "SOLDIER Military Program")
    act(s, "p1", type="pass_priority")
    answer(s, "1:0", [])
    assert counters(s, a) == 0
    check(s)


def two_counters_then_nexus(cards, mode):
    s = build(cards, ["Nexus Mentality", "Soldier A", "Soldier B"])
    a, b = put(s, "Soldier A"), put(s, "Soldier B")
    act(s, "p1", type="counter", card_ids=[a.id], kind="+1/+1", delta=3)
    act(s, "p1", type="counter", card_ids=[a.id], kind="charge", delta=1)
    mana(s, U=1, C=3)
    return s, a, b


def test_nexus_mentality_draws_a_card_for_each_counter_removed(cards):
    """122.8, 608.2c: every kind of counter is removed from the target; one card is drawn for each one actually removed."""
    s, a, b = two_counters_then_nexus(cards, 1)
    cast(s, "Nexus Mentality", [a.id], modes=[1])
    answer(s)
    assert s.state.cards[a.id].counters.get("+1/+1", 0) == 0 and s.state.cards[a.id].counters.get("charge", 0) == 0
    assert len(s.state.zones["p1:hand"]) == 4
    check(s)


def test_nexus_mentality_move_mode_keeps_counters(cards):
    s, a, b = two_counters_then_nexus(cards, 0)
    cast(s, "Nexus Mentality", [a.id, b.id], modes=[0], target_counts=[1, 1])
    answer(s)
    assert counters(s, b) == 3 and counters(s, a) == 0
    check(s)


def graveyard_zombies(s):
    act(s, "p2", type="move", card_ids=[card_named(s, "Big Zombie", "p2").id, card_named(s, "Little Zombie", "p2").id],
        to={"player": "p2", "zone": "graveyard"})


def test_szats_will_exiles_graveyards_and_makes_thrulls_for_the_greatest_power(cards):
    """608.2h: X is the greatest power among the creature cards exiled this way (5), not their number or total."""
    s = build(cards, ["Szat's Will"], ["Big Zombie", "Little Zombie"])
    graveyard_zombies(s)
    mana(s, B=1, C=4)
    cast(s, "Szat's Will", [], modes=[1])
    answer(s)
    assert not [c for c in s.state.zones["p2:graveyard"] if s.state.cards[c].name.endswith("Zombie")]
    assert sum(1 for c in s.state.cards.values() if c.name == "Thrull" and c.zone == "p1:battlefield") == 5
    check(s)


def test_szats_will_opponent_sacrifices_their_greatest_power_creature(cards):
    s = build(cards, ["Szat's Will"], ["Big Zombie", "Little Zombie"])
    big, little = put(s, "Big Zombie", "p2"), put(s, "Little Zombie", "p2")
    mana(s, B=1, C=4)
    cast(s, "Szat's Will", [], modes=[0])
    answer(s)
    assert zone(s, big) == "p2:graveyard" and zone(s, little) == "p2:battlefield"
    check(s)


def test_szats_will_both_modes_with_a_commander(cards):
    s = build(cards, ["Szat's Will"], ["Big Zombie", "Little Zombie"])
    put(s, "Krenko, Mob Boss")
    big = put(s, "Big Zombie", "p2")
    mana(s, B=1, C=4)
    cast(s, "Szat's Will", [], modes=[0, 1])
    answer(s)
    assert zone(s, big) == "p2:exile"  # sacrificed first, then its graveyard is exiled: it is among the cards exiled
    assert sum(1 for c in s.state.cards.values() if c.name == "Thrull" and c.zone == "p1:battlefield") == 5
    check(s)


@pytest.mark.parametrize("who,pays", [("p1", True), ("p1", False), ("p2", True), ("p2", False)])
def test_meathook_returns_the_dead_creature_under_your_control_with_a_finality_counter(cards, who, pays):
    """400.7: the returned creature is a new object under Meathook's controller with a finality counter (122.1c); the payer is the creature's controller."""
    s = build(cards, ["Meathook Massacre II", "Soldier A", "Lightning Bolt"], ["Soldier B"])
    put(s, "Meathook Massacre II")
    victim = put(s, "Soldier A" if who == "p1" else "Soldier B", who)
    mana(s, R=1)
    cast(s, "Lightning Bolt", [victim.id])
    answer(s, "pay" if pays else "decline")
    back = (who == "p1") == pays  # your own creature returns when you pay; an opponent's when they don't
    c = s.state.cards[victim.id]
    assert (c.zone, c.controller, c.counters.get("finality", 0)) == (("p1:battlefield", "p1", 1) if back else (f"{who}:graveyard", who, 0))
    assert life(s, who) == 40 - (3 if pays else 0) - (0 if who == "p1" else 0)
    check(s)


def lands_on_field(s, n):
    ids = [c.id for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library"][:n]
    act(s, "p1", type="move", card_ids=ids, to={"player": "p1", "zone": "battlefield"})
    return ids


@pytest.mark.parametrize("name", ["Scorched Ruins", "Lotus Vale"])
def test_sacrifice_two_untapped_lands_as_it_would_enter(cards, name):
    """614.12, 118.12: two picks are asked one after the other (not the entering land, none twice); both are sacrificed, then the land enters."""
    s = build(cards, [name])
    ids = lands_on_field(s, 3)
    land = to_hand(s, name)
    act(s, "p1", type="play_land", card_id=land.id)
    answer(s, ids[0], ids[2])
    assert zone(s, land) == "p1:battlefield"
    assert [zone(s, s.state.cards[i]) for i in ids] == ["p1:graveyard", "p1:battlefield", "p1:graveyard"]
    check(s)


def test_sacrifice_two_untapped_lands_second_pick_excludes_the_first(cards):
    s = build(cards, ["Scorched Ruins"])
    ids = lands_on_field(s, 3)
    act(s, "p1", type="play_land", card_id=to_hand(s, "Scorched Ruins").id)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[ids[1]])
    assert ids[1] not in [o.id for o in s.state.rules.decision.options]
    check(s)


def test_scorched_ruins_with_one_untapped_land_goes_to_the_graveyard(cards):
    """614.6, 118.3: it can't pay, so it never enters: it is put into its owner's graveyard (still the land played)."""
    s = build(cards, ["Scorched Ruins"])
    (one,) = lands_on_field(s, 1)
    ruins = to_hand(s, "Scorched Ruins")
    act(s, "p1", type="play_land", card_id=ruins.id)
    assert s.state.rules.decision is None and zone(s, ruins) == "p1:graveyard" and zone(s, s.state.cards[one]) == "p1:battlefield"
    check(s)
