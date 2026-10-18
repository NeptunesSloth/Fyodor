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
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, to_hand, zone_of
from tests.wave52d_kit import open_repo

NAMES = ["Tinder Wall", "Wall of Corpses", "Acorn Catapult", "Magewright's Stone", "Cleaver Skaab", "Doubling Cube", "Tainted Sigil", "Assembly-Worker", "Witch Engine", "Skyship Weatherlight", "Folio of Fancies", "Overgrown Arch", "Patron of the Orochi", "Cauldron of Souls", "Silent Gravestone", "Phyrexian Furnace", "Grenzo, Dungeon Warden", "Cellar Door",
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


# ---- Doubling Cube ------------------------------------------------------------------------------------------------------------------------------
def test_doubling_cube_doubles_each_type_of_unspent_mana_left_after_paying(cards):
    s = build(cards, ["Doubling Cube"])
    cube = put(s, "Doubling Cube")
    mana(s, "p1", R=4, G=2)  # {3} of it pays for the ability: R=3 and G=0 are left... the payer takes what it likes, so only the total is checked
    activate(s, "p1", cube)
    settle(s)
    pool = s.state.players["p1"].mana
    assert sum(pool.values()) == 6  # 6 - 3 paid = 3 left, doubled
    check(s)


# ---- Tainted Sigil ------------------------------------------------------------------------------------------------------------------------------
def test_tainted_sigil_gains_the_life_every_player_lost_this_turn(cards):
    s = build(cards, ["Tainted Sigil", "Lightning Bolt", "Lightning Bolt"])
    sigil = put(s, "Tainted Sigil")
    bolts = [c for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1"]
    for bolt, target in zip(bolts, ("p2", "p1"), strict=True):
        act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "hand"})
        mana(s, "p1", R=1)
        act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[target])
        settle(s)
    before = life(s)  # 40 - 3
    assert before == 37 and life(s, "p2") == 37
    activate(s, "p1", sigil)
    settle(s)
    assert life(s) == 43 and zone_of(s, "Tainted Sigil") == "p1:graveyard"  # 3 + 3 lost
    check(s)


# ---- Assembly-Worker (the name is also the creature type) ----------------------------------------------------------------------------------------------
def test_assembly_worker_pumps_an_assembly_worker_creature(cards):
    s = build(cards, ["Assembly-Worker"])
    worker = put(s, "Assembly-Worker")
    next_turn(s)
    assert pt(s, "Assembly-Worker") == (2, 2)
    activate(s, "p1", worker, targets=[worker.id])
    settle(s)
    assert pt(s, "Assembly-Worker") == (3, 3)
    check(s)


def test_assembly_worker_cannot_target_another_kind_of_creature(cards):
    s = build(cards, ["Assembly-Worker", "Llanowar Elves"])
    worker, elves = put(s, "Assembly-Worker"), put(s, "Llanowar Elves")
    next_turn(s)
    with pytest.raises(ActionError):
        activate(s, "p1", worker, targets=[elves.id])


# ---- Witch Engine -------------------------------------------------------------------------------------------------------------------------------
def test_witch_engine_adds_the_mana_then_the_opponent_gains_control(cards):
    s = build(cards, ["Witch Engine"])
    engine = put(s, "Witch Engine")
    next_turn(s)
    activate(s, "p1", engine, targets=["p2"])  # it has a target: not a mana ability, it uses the stack (605.1a)
    settle(s)
    assert s.state.players["p1"].mana == {"B": 4} and s.state.cards[engine.id].controller == "p2"
    check(s)


# ---- Skyship Weatherlight -----------------------------------------------------------------------------------------------------------------------
def test_weatherlight_returns_one_of_its_exiled_cards_to_hand(cards):
    s = build(cards, ["Skyship Weatherlight", "Llanowar Elves"])
    mana(s, "p1", C=5)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Skyship Weatherlight").id)
    settle(s)  # it enters: search for any number of artifact and/or creature cards, exile them, then shuffle
    exiled = list(s.state.zones["p1:exile"])
    assert [s.state.cards[c].name for c in exiled] == ["Llanowar Elves"]
    next_turn(s)
    mana(s, "p1", C=4)
    activate(s, "p1", card_named(s, "Skyship Weatherlight"), "random")
    settle(s)
    assert s.state.cards[exiled[0]].zone == "p1:hand" or "Llanowar Elves" in hand(s)
    check(s)


# ---- Cleaver Skaab ------------------------------------------------------------------------------------------------------------------------------
def test_cleaver_skaab_makes_two_copies_of_the_sacrificed_zombie(cards):
    s = build(cards, ["Cleaver Skaab", "Dregscape Zombie"])
    skaab = put(s, "Cleaver Skaab")
    put(s, "Dregscape Zombie")
    next_turn(s)
    mana(s, "p1", C=3)
    activate(s, "p1", skaab)
    settle(s)
    zombies = [c for c in s.state.cards.values() if c.name == "Dregscape Zombie" and c.zone == "p1:battlefield"]
    assert len(zombies) == 2 and all(c.is_token for c in zombies)  # the card itself was sacrificed
    assert zone_of(s, "Dregscape Zombie") == "p1:graveyard"
    check(s)


# ---- Tinder Wall, Wall of Corpses (the source is sacrificed as a cost; what it was blocking is its last known information, 608.2b) -------------------
def blocked_table(cards, wall):
    from tests.test_rules_wave34b_activated import attack, block, priority_to, stops

    s = build(cards, ["Hill Giant"], [wall])
    giant = put(s, "Hill Giant")
    blocker = put(s, wall, "p2")
    stops(s)
    next_turn(s)
    attack(s, giant)
    block(s, (blocker, giant))
    priority_to(s, "p2")
    return s, giant, blocker


def test_wall_of_corpses_sacrifices_itself_and_destroys_the_creature_it_blocks(cards):
    s, giant, wall = blocked_table(cards, "Wall of Corpses")
    mana(s, "p2", B=1)
    activate(s, "p2", wall, "Destroy", targets=[giant.id])
    settle(s)
    assert zone_of(s, "Wall of Corpses", "p2") == "p2:graveyard" and zone_of(s, "Hill Giant") == "p1:graveyard"
    check(s)


def test_tinder_wall_deals_two_damage_to_the_creature_it_blocks(cards):
    s, giant, wall = blocked_table(cards, "Tinder Wall")
    mana(s, "p2", R=1)
    activate(s, "p2", wall, "damage", targets=[giant.id])
    settle(s)
    assert zone_of(s, "Tinder Wall", "p2") == "p2:graveyard" and s.state.cards[giant.id].damage == 2
    check(s)


def test_tinder_wall_cannot_target_a_creature_it_is_not_blocking(cards):
    from tests.test_rules_wave34b_activated import attack, block, priority_to, stops

    s = build(cards, ["Hill Giant", "Grizzly Bears"], ["Tinder Wall"])
    giant, bears = put(s, "Hill Giant"), put(s, "Grizzly Bears")
    wall = put(s, "Tinder Wall", "p2")
    stops(s)
    next_turn(s)
    attack(s, giant, bears)
    block(s, (wall, giant))
    priority_to(s, "p2")
    mana(s, "p2", R=1)
    with pytest.raises(ActionError):
        activate(s, "p2", wall, "damage", targets=[bears.id])  # the Wall blocks the Giant, not the Bears
    assert zone_of(s, "Tinder Wall", "p2") == "p2:battlefield"
    check(s)


# ---- Acorn Catapult -----------------------------------------------------------------------------------------------------------------------------
def test_acorn_catapult_gives_the_damaged_players_a_squirrel(cards):
    s = build(cards, ["Acorn Catapult"])
    cat = put(s, "Acorn Catapult")
    next_turn(s)
    mana(s, "p1", C=1)
    activate(s, "p1", cat, targets=["p2"])
    settle(s)
    squirrels = [c for c in s.state.cards.values() if c.name == "Squirrel"]
    assert life(s, "p2") == 39 and [c.controller for c in squirrels] == ["p2"]
    check(s)


def test_acorn_catapult_gives_a_damaged_creatures_controller_a_squirrel(cards):
    s = build(cards, ["Acorn Catapult"], ["Grizzly Bears"])
    cat = put(s, "Acorn Catapult")
    bears = put(s, "Grizzly Bears", "p2")
    next_turn(s)
    mana(s, "p1", C=1)
    activate(s, "p1", cat, targets=[bears.id])
    settle(s)
    assert s.state.cards[bears.id].damage == 1 and [c.controller for c in s.state.cards.values() if c.name == "Squirrel"] == ["p2"]
    check(s)


# ---- Magewright's Stone -------------------------------------------------------------------------------------------------------------------------
def test_magewrights_stone_untaps_a_creature_with_a_tap_ability_only(cards):
    s = build(cards, ["Magewright's Stone", "Llanowar Elves", "Grizzly Bears"])
    stone = put(s, "Magewright's Stone")
    elves, bears = put(s, "Llanowar Elves"), put(s, "Grizzly Bears")
    next_turn(s)
    act(s, "p1", type="tap", card_ids=[elves.id, bears.id], tapped=True)
    mana(s, "p1", C=1)
    with pytest.raises(ActionError):
        activate(s, "p1", stone, targets=[bears.id])  # no activated ability with {T} in its cost
    activate(s, "p1", stone, targets=[elves.id])
    settle(s)
    assert not s.state.cards[elves.id].tapped and s.state.cards[bears.id].tapped
    check(s)
