"""Wave 52D: activated abilities one clause short of FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave52d_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 701.17a / 107.1: Folio of Fancies - each opponent mills as many cards as are in their own hand (608.2h: counted before any of them mills).
* 701.48a: Overgrown Arch - learn is the rummage in a game with no cards outside it.
* 608.2c: Patron of the Orochi (two groups untapped), Cauldron of Souls (any number of targets gain persist), Silent Gravestone (exiles itself and every graveyard).
* 404.2: Phyrexian Furnace - the bottom card of a graveyard (the first one in it).
* 701.17a: Grenzo, Dungeon Warden / Cellar Door - the bottom card of a library is put into its owner's graveyard (no mill), then "if it's a creature card".
* 701.20a: Druidic Satchel - the revealed card decides which of the three things happens.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, next_turn, settle
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of
from tests.wave52d_kit import open_repo

NAMES = ["Folio of Fancies", "Overgrown Arch", "Patron of the Orochi", "Cauldron of Souls", "Silent Gravestone", "Phyrexian Furnace", "Grenzo, Dungeon Warden", "Cellar Door",
         "Druidic Satchel"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", NAMES)
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def hand(s, pid="p1"):
    return [s.state.cards[c].name for c in s.state.zones[f"{pid}:hand"]]


def yard(s, pid="p1"):
    return [s.state.cards[c].name for c in s.state.zones[f"{pid}:graveyard"]]


def keywords(s, name, pid="p1"):
    return Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id]).keywords


def to_library(s, name, position, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position=position)
    return c


def to_yard(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


# ---- Folio of Fancies ---------------------------------------------------------------------------------------------------------------------------
def test_folio_mills_each_opponent_as_many_cards_as_their_own_hand(cards):
    s = build(cards, ["Folio of Fancies"], ["Counterspell", "Mana Leak"])
    folio = put(s, "Folio of Fancies")
    mana(s, "p1", U=1, C=2)
    before_hand, before_lib = len(hand(s, "p2")), len(s.state.zones["p2:library"])
    activate(s, "p1", folio, "mills")
    settle(s)
    assert len(s.state.zones["p2:library"]) == before_lib - before_hand and len(yard(s, "p2")) == before_hand
    assert len(hand(s, "p2")) == before_hand  # the hand is only counted
    check(s)


def test_folio_mills_nothing_from_an_empty_hand(cards):
    s = build(cards, ["Folio of Fancies"])
    folio = put(s, "Folio of Fancies")
    for c in list(s.state.zones["p2:hand"]):
        act(s, "p2", type="move", card_ids=[c], to={"zone": "library"})
    mana(s, "p1", U=1, C=2)
    activate(s, "p1", folio, "mills")
    settle(s)
    assert yard(s, "p2") == []
    check(s)


# ---- Overgrown Arch -----------------------------------------------------------------------------------------------------------------------------
def test_overgrown_arch_sacrifices_itself_and_learns_by_rummaging(cards):
    s = build(cards, ["Overgrown Arch"])
    arch = put(s, "Overgrown Arch")
    mana(s, "p1", C=2)
    to_hand(s, "Forest")
    discarded = "Forest"
    size = len(hand(s))
    activate(s, "p1", arch, "Learn")
    settle(s)  # "You may discard a card. If you do, draw a card."
    assert zone_of(s, "Overgrown Arch") == "p1:graveyard" and len(hand(s)) == size and discarded in yard(s)
    check(s)


# ---- Patron of the Orochi -----------------------------------------------------------------------------------------------------------------------
def test_patron_untaps_forests_and_green_creatures_only_once_each_turn(cards):
    s = build(cards, ["Patron of the Orochi", "Llanowar Elves", "Perilous Myr"])
    patron = put(s, "Patron of the Orochi")
    elves, myr, forest = put(s, "Llanowar Elves"), put(s, "Perilous Myr"), put(s, "Forest")
    act(s, "p1", type="tap", card_ids=[elves.id, myr.id, forest.id], tapped=True)
    next_turn(s)  # summoning sickness over; the untap step untapped them: tap again
    act(s, "p1", type="tap", card_ids=[elves.id, myr.id, forest.id], tapped=True)
    activate(s, "p1", patron)
    settle(s)
    tapped = lambda c: s.state.cards[c.id].tapped  # noqa: E731
    assert not tapped(elves) and not tapped(forest) and tapped(myr)  # Perilous Myr is colorless
    with pytest.raises(ActionError):
        activate(s, "p1", patron)  # once each turn (the Patron untapped itself: it is a green creature too, so it could pay {T} again)
    check(s)


# ---- Cauldron of Souls --------------------------------------------------------------------------------------------------------------------------
def test_cauldron_gives_persist_to_any_number_of_targets_until_end_of_turn(cards):
    s = build(cards, ["Cauldron of Souls", "Llanowar Elves", "Perilous Myr"])
    cauldron = put(s, "Cauldron of Souls")
    put(s, "Llanowar Elves")
    put(s, "Perilous Myr")
    next_turn(s)
    activate(s, "p1", cauldron, targets=[card_named(s, "Llanowar Elves").id, card_named(s, "Perilous Myr").id], target_counts=[2])
    settle(s)
    assert "persist" in keywords(s, "Llanowar Elves") and "persist" in keywords(s, "Perilous Myr")
    check(s)


def test_cauldron_may_target_no_creature(cards):
    s = build(cards, ["Cauldron of Souls"])
    cauldron = put(s, "Cauldron of Souls")
    next_turn(s)
    activate(s, "p1", cauldron, targets=[], target_counts=[0])
    settle(s)
    assert s.state.cards[cauldron.id].tapped
    check(s)


# ---- Silent Gravestone --------------------------------------------------------------------------------------------------------------------------
def test_gravestone_exiles_itself_and_every_graveyard_then_draws(cards):
    s = build(cards, ["Silent Gravestone", "Llanowar Elves"], ["Counterspell"])
    stone = put(s, "Silent Gravestone")
    to_yard(s, "Llanowar Elves")
    to_yard(s, "Counterspell", "p2")
    mana(s, "p1", C=4)
    next_turn(s)
    mana(s, "p1", C=4)
    size = len(hand(s))
    activate(s, "p1", stone)
    settle(s)
    assert yard(s) == [] and yard(s, "p2") == [] and zone_of(s, "Silent Gravestone") == "p1:exile"
    assert zone_of(s, "Llanowar Elves") == "p1:exile" and zone_of(s, "Counterspell", "p2") == "p2:exile" and len(hand(s)) == size + 1
    check(s)


# ---- Phyrexian Furnace --------------------------------------------------------------------------------------------------------------------------
def test_furnace_exiles_the_bottom_card_of_the_targeted_graveyard(cards):
    s = build(cards, ["Phyrexian Furnace"], ["Counterspell", "Mana Leak", "Opt"])
    furnace = put(s, "Phyrexian Furnace")
    for n in ("Counterspell", "Mana Leak", "Opt"):  # Counterspell went in first: it is the bottom
        to_yard(s, n, "p2")
    next_turn(s)
    activate(s, "p1", furnace, targets=["p2"])
    settle(s)
    assert yard(s, "p2") == ["Mana Leak", "Opt"] and zone_of(s, "Counterspell", "p2") == "p2:exile"
    check(s)


def test_furnace_does_nothing_to_an_empty_graveyard(cards):
    s = build(cards, ["Phyrexian Furnace"])
    furnace = put(s, "Phyrexian Furnace")
    next_turn(s)
    activate(s, "p1", furnace, targets=["p2"])
    settle(s)
    assert yard(s, "p2") == [] and s.state.cards[furnace.id].tapped
    check(s)


# ---- Grenzo, Dungeon Warden ---------------------------------------------------------------------------------------------------------------------
def test_grenzo_puts_a_small_enough_creature_from_the_bottom_onto_the_battlefield(cards):
    s = build(cards, ["Grenzo, Dungeon Warden", "Llanowar Elves"])
    grenzo = put(s, "Grenzo, Dungeon Warden")
    elves = to_library(s, "Llanowar Elves", "bottom")  # power 1 <= Grenzo's power 2
    mana(s, "p1", C=2)
    activate(s, "p1", grenzo)
    settle(s)
    assert zone_of(s, "Llanowar Elves") == "p1:battlefield" and s.state.cards[elves.id].controller == "p1"
    check(s)


def test_grenzo_leaves_a_creature_with_too_much_power_in_the_graveyard(cards):
    s = build(cards, ["Grenzo, Dungeon Warden", "Twisted Abomination"])
    grenzo = put(s, "Grenzo, Dungeon Warden")
    to_library(s, "Twisted Abomination", "bottom")  # power 5 > 2
    mana(s, "p1", C=2)
    activate(s, "p1", grenzo)
    settle(s)
    assert zone_of(s, "Twisted Abomination") == "p1:graveyard"
    check(s)


def test_grenzo_leaves_a_land_in_the_graveyard(cards):
    s = build(cards, ["Grenzo, Dungeon Warden"])
    grenzo = put(s, "Grenzo, Dungeon Warden")
    forest = s.state.zones["p1:library"][-1]
    mana(s, "p1", C=2)
    activate(s, "p1", grenzo)
    settle(s)
    assert s.state.cards[forest].zone == "p1:graveyard"
    check(s)


# ---- Cellar Door --------------------------------------------------------------------------------------------------------------------------------
def test_cellar_door_makes_a_zombie_when_the_bottom_card_is_a_creature(cards):
    s = build(cards, ["Cellar Door"], ["Grizzly Bears"])
    door = put(s, "Cellar Door")
    to_library(s, "Grizzly Bears", "bottom", "p2")
    mana(s, "p1", C=3)
    next_turn(s)
    mana(s, "p1", C=3)
    activate(s, "p1", door, targets=["p2"])
    settle(s)
    assert "Grizzly Bears" in yard(s, "p2")
    zombies = [c for c in s.state.cards.values() if c.name == "Zombie" and c.zone == "p1:battlefield"]
    assert len(zombies) == 1
    check(s)


def test_cellar_door_makes_no_zombie_for_a_land(cards):
    s = build(cards, ["Cellar Door"])
    door = put(s, "Cellar Door")
    mana(s, "p1", C=3)
    next_turn(s)
    mana(s, "p1", C=3)
    bottom = s.state.zones["p2:library"][-1]
    activate(s, "p1", door, targets=["p2"])
    settle(s)
    assert s.state.cards[bottom].zone == "p2:graveyard"
    assert not [c for c in s.state.cards.values() if c.name == "Zombie"]
    check(s)


# ---- Druidic Satchel ----------------------------------------------------------------------------------------------------------------------------
def satchel_table(cards, top):
    s = build(cards, ["Druidic Satchel", top])
    satchel = put(s, "Druidic Satchel")
    if top != "Forest":
        to_library(s, top, "top")
    else:
        act(s, "p1", type="move", card_ids=[s.state.zones["p1:library"][0]], to={"player": "p1", "zone": "library"}, position="top")
    mana(s, "p1", C=2)
    next_turn(s)
    mana(s, "p1", C=2)
    return s, satchel


def test_satchel_makes_a_saproling_for_a_creature_card(cards):
    s, satchel = satchel_table(cards, "Llanowar Elves")
    to_library(s, "Llanowar Elves", "top")
    activate(s, "p1", satchel)
    settle(s)
    assert len([c for c in s.state.cards.values() if c.name == "Saproling"]) == 1 and zone_of(s, "Llanowar Elves") == "p1:library"
    check(s)


def test_satchel_puts_a_land_onto_the_battlefield(cards):
    s, satchel = satchel_table(cards, "Forest")
    top = s.state.zones["p1:library"][0]
    assert s.state.cards[top].name == "Forest"
    activate(s, "p1", satchel)
    settle(s)
    assert s.state.cards[top].zone == "p1:battlefield"
    check(s)


def test_satchel_gains_two_life_for_a_noncreature_nonland_card(cards):
    s, satchel = satchel_table(cards, "Folio of Fancies")
    to_library(s, "Folio of Fancies", "top")
    before = life(s)
    activate(s, "p1", satchel)
    settle(s)
    assert life(s) == before + 2
    check(s)
