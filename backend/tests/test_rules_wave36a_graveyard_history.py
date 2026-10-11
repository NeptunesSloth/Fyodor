"""Wave 36A: "a card in a graveyard that was put there this turn": the graveyard history selectors, researched against CR 2026-09-25, real
Oracle text (tests/fixtures/wave36a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 400.7: a card that changes zones becomes a new object, so "a card in your graveyard that was put there from the battlefield this turn" is
  read of the object that is there now: one that left and came back is a new object, put there from wherever it came from then.
* 700.4, 603.10a: "dies" / "put there from the battlefield": from the battlefield; a milled card came from a library (701.17a), a
  discarded one from a hand (701.9a), a spell that resolved or was countered from the stack: "from anywhere" is every one of them.
* 608.2b: a target is checked again as the ability resolves (still in that graveyard, still the card that was put there this turn).
* 506.1: "this combat" is the current combat phase (a turn may have several, 500.8): a creature put there in an earlier phase wasn't.
* 111.1: a token is no card, so it is never "put there" (the log records cards only).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.rules_state import Arrival, TurnFact
from app.rules import coverage, selectors
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle, until
from tests.wave9c_kit import build, card_named, cast, check, mana, put, to_hand
from tests.wave36a_kit import attack, finish_turn, mill, next_own_turn, offered, pick, to_gy, zone

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave36a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w36a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Garna, the Bloodflame", "Moira, Urborg Haunt", "Samwise the Stouthearted", "Night Nurse, Healer of Heroes", "Captain N'ghathrod",
        "Storrev, Devkarin Lich", "Ghost of Ramirez DePietro", "Gleancrawler", "Twilight Shepherd", "Fell Shepherd", "Wreck Hunter"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


# -- coverage ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", FULL)
def test_the_graveyard_history_cards_are_full(name):
    from tests.test_rules_scripts import ch as characteristics

    c = next(c for c in DATA if c["name"] == name)
    chs = characteristics(c["name"], c["type_line"], c["oracle_text"])
    assert coverage.of_characteristics(chs).level == "FULL", (name, coverage.of_characteristics(chs).manual_parts)


# -- the selectors ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("phrase, extra", [
    ("permanent card in your graveyard that was put there from the battlefield this turn", "put_there:battlefield"),
    ("creature cards in your graveyard that were put there from anywhere this turn", "put_there:any"),
    ("creature cards that were put into your graveyard from the battlefield this turn", "put_there:battlefield"),
    ("artifact or creature card in an opponent's graveyard that was put there from their library this turn", "put_there:library"),
    ("card in a graveyard that was discarded or put there from a library this turn", "put_there:discard_or_library"),
    ("creature or planeswalker card in your graveyard that wasn't put there this combat", "not_put_there_combat"),
])
def test_the_put_there_phrases_are_selectors(phrase, extra):
    sel = selectors.parse(phrase)
    assert sel is not None and sel.zones == ("graveyard",) and sel.card and extra in sel.extras


@pytest.mark.parametrize("phrase", [
    "creature card in your graveyard that was discarded or put there from the battlefield this turn",  # (not a wording that exists: refused)
    "creature card in your graveyard that was put there from exile this turn",  # (a zone the log doesn't name for this: refused)
])
def test_other_put_there_wordings_stay_unread(phrase):
    assert selectors.parse(phrase) is None


def test_an_old_save_has_no_origin_for_its_arrivals():
    """New fields need defaults so old saves load: an arrival recorded before this wave has no object and no origin, and so is never
    read as "put there from the battlefield" (the card stays in the graveyard, untouched by such a trigger)."""
    old = Arrival.model_validate({"card": "c1", "owner": "p1"})
    assert (old.object_id, old.from_zone, old.combat) == (None, None, 0)
    assert TurnFact.model_validate({"kind": "discard", "player": "p1"}).batch == 0  # (and a discard fact of an older save has no batch: "first time each turn" skips it)


# -- Garna: "return to your hand all creature cards in your graveyard that were put there from anywhere this turn" ---------
def garna_table(cards):
    s = build(cards, ["Garna, the Bloodflame", "Grizzly Bears", "Llanowar Elves", "Young Wolf", "Kitchen Finks", "Murder", "Opt"], forests=20,
              theirs=["Grizzly Bears"])
    to_gy(s, "Kitchen Finks")  # (an earlier turn)
    to_hand(s, "Garna, the Bloodflame")
    next_own_turn(s)
    return s


def test_garna_returns_every_creature_card_put_into_the_graveyard_this_turn(cards):
    """Garna's trigger reads each object: a creature that died (from the battlefield) and one that was discarded (from a hand) count, one
    that was put there on an earlier turn does not, nor does a noncreature card put there this turn, nor another player's graveyard."""
    s = garna_table(cards)
    put(s, "Grizzly Bears")
    to_gy(s, "Grizzly Bears")  # died this turn
    to_hand(s, "Young Wolf")
    to_gy(s, "Young Wolf")  # discarded this turn (from a hand)
    to_hand(s, "Opt")
    to_gy(s, "Opt")  # a noncreature card put there this turn
    put(s, "Grizzly Bears", "p2")
    to_gy(s, "Grizzly Bears", "p2")  # an opponent's creature, in an opponent's graveyard
    assert zone(s, "Kitchen Finks") == "p1:graveyard"
    mana(s, B=1, R=1, G=3)
    cast(s, "Garna, the Bloodflame")
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:hand" and zone(s, "Young Wolf") == "p1:hand"
    assert zone(s, "Kitchen Finks") == "p1:graveyard" and zone(s, "Opt") == "p1:graveyard" and zone(s, "Grizzly Bears", "p2") == "p2:graveyard"
    check(s)


def test_garna_leaves_a_card_that_left_and_came_back_to_the_graveyard_alone(cards):
    """400.7: the Bears that was reanimated and died again this turn is a new object, put there from the battlefield: it comes back; but
    one that was put into the graveyard this turn and returned to the battlefield and stays there is not in the graveyard at all."""
    s = garna_table(cards)
    put(s, "Llanowar Elves")
    to_gy(s, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[card_named(s, "Llanowar Elves").id], to={"player": "p1", "zone": "battlefield"})
    mana(s, B=1, R=1, G=3)
    cast(s, "Garna, the Bloodflame")
    settle(s)
    assert zone(s, "Llanowar Elves") == "p1:battlefield"
    check(s)


def test_arrivals_of_an_older_save_are_never_read_as_put_there_this_turn(cards):
    """An arrival recorded before this wave has no object and no origin: nothing is returned on a guess (the card stays where it is)."""
    s = garna_table(cards)
    put(s, "Grizzly Bears")
    to_gy(s, "Grizzly Bears")
    for arrival in s.state.rules.turn_log.entered_graveyard:
        arrival.object_id = arrival.from_zone = None
    mana(s, B=1, R=1, G=3)
    cast(s, "Garna, the Bloodflame")
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:graveyard"


# -- Moira: "return to the battlefield target creature card in your graveyard that was put there from the battlefield this turn" -------
def moira_table(cards):
    s = build(cards, ["Moira, Urborg Haunt", "Grizzly Bears", "Llanowar Elves", "Young Wolf", "Kitchen Finks", "Opt"], forests=20)
    to_gy(s, "Young Wolf")  # (an earlier turn)
    put(s, "Moira, Urborg Haunt")  # (and no longer summoning sick)
    next_own_turn(s)
    return s


def test_moira_only_targets_creatures_that_died_this_turn(cards):
    """700.4 / 400.7: the Bears died this turn (put there from the battlefield); the Wolf was put there last turn; the Elves died too, but was
    then exiled and put back into the graveyard (a new object, put there from exile); the Finks was milled (from a library)."""
    s = moira_table(cards)
    moira = card_named(s, "Moira, Urborg Haunt")
    put(s, "Grizzly Bears")
    to_gy(s, "Grizzly Bears")
    put(s, "Llanowar Elves")
    to_gy(s, "Llanowar Elves")
    elves = card_named(s, "Llanowar Elves")
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "exile"})
    act(s, "p1", type="move", card_ids=[elves.id], to={"zone": "graveyard"})
    mill(s, "Kitchen Finks")  # (from the library)
    attack(s, moira)
    assert offered(s) == ["Grizzly Bears"]  # (the Bears alone: the other three were not put there from the battlefield this turn)
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:battlefield"
    assert zone(s, "Llanowar Elves") == "p1:graveyard" and zone(s, "Young Wolf") == "p1:graveyard" and zone(s, "Kitchen Finks") == "p1:graveyard"
    check(s)


def test_moira_does_nothing_when_nothing_died_this_turn(cards):
    s = moira_table(cards)
    attack(s, card_named(s, "Moira, Urborg Haunt"))
    until(s, lambda s: s.state.turn.phase == "main2")
    assert s.state.rules.decision is None and zone(s, "Young Wolf") == "p1:graveyard"  # (no legal target: the trigger is removed, 603.3d)
    check(s)


def test_moira_target_is_checked_again_as_the_trigger_resolves(cards):
    """608.2b: the Bears the trigger targeted is exiled in response: the ability does nothing (it left the graveyard)."""
    s = moira_table(cards)
    put(s, "Grizzly Bears")
    to_gy(s, "Grizzly Bears")
    attack(s, card_named(s, "Moira, Urborg Haunt"))
    assert offered(s) == ["Grizzly Bears"]
    pick(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[card_named(s, "Grizzly Bears").id], to={"zone": "exile"})  # (in response)
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:exile"
    check(s)


# -- Samwise: "choose up to one target permanent card in your graveyard that was put there from the battlefield this turn" -----------
def samwise_table(cards):
    s = build(cards, ["Samwise the Stouthearted", "Grizzly Bears", "Sol Ring", "Opt", "Kitchen Finks"], forests=20)
    to_gy(s, "Sol Ring")  # (an earlier turn)
    next_own_turn(s)
    to_hand(s, "Samwise the Stouthearted")
    mana(s, W=1, G=1)
    return s


def test_samwise_returns_a_permanent_that_was_put_there_from_the_battlefield_and_the_ring_tempts_you(cards):
    """The Bears died (a permanent card, from the battlefield); the Opt was discarded (not a permanent card), the Finks was milled (a permanent
    card, from a library) and the Sol Ring was put there last turn: only the Bears is a legal target."""
    s = samwise_table(cards)
    put(s, "Grizzly Bears")
    to_gy(s, "Grizzly Bears")
    to_hand(s, "Opt")
    to_gy(s, "Opt")
    mill(s, "Kitchen Finks")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Samwise the Stouthearted").id)
    assert offered(s) == ["Grizzly Bears"]
    pick(s, "Grizzly Bears")
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:hand" and zone(s, "Sol Ring") == "p1:graveyard" and zone(s, "Opt") == "p1:graveyard"
    assert zone(s, "Kitchen Finks") == "p1:graveyard"
    assert s.state.rules.ring_tempted["p1"] == 1
    check(s)


def test_samwise_with_nothing_to_return_still_tempts_you(cards):
    """"Up to one target": with no legal target the ability still goes on the stack with none (601.2c), and the Ring tempts you."""
    s = samwise_table(cards)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Samwise the Stouthearted").id)
    settle(s)
    assert zone(s, "Sol Ring") == "p1:graveyard" and s.state.rules.ring_tempted["p1"] == 1
    check(s)


# -- Night Nurse: "choose target permanent card in your graveyard that was put there from anywhere this turn" -----------------------
def test_night_nurse_returns_a_permanent_card_put_there_from_anywhere_this_turn(cards):
    s = build(cards, ["Night Nurse, Healer of Heroes", "Grizzly Bears", "Sol Ring", "Opt", "Kitchen Finks", "Young Wolf"], forests=20)
    to_gy(s, "Sol Ring")  # (an earlier turn)
    next_own_turn(s)
    to_hand(s, "Night Nurse, Healer of Heroes")
    mana(s, W=1, G=1)
    mill(s, "Kitchen Finks")  # (milled: from a library)
    to_hand(s, "Young Wolf")
    to_gy(s, "Young Wolf")  # (discarded: from a hand)
    to_hand(s, "Opt")
    to_gy(s, "Opt")  # (not a permanent card)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Night Nurse, Healer of Heroes").id)
    assert offered(s) == ["Kitchen Finks", "Young Wolf"]
    pick(s, "Young Wolf")
    settle(s)
    assert zone(s, "Young Wolf") == "p1:hand" and zone(s, "Kitchen Finks") == "p1:graveyard" and zone(s, "Sol Ring") == "p1:graveyard"
    check(s)


def test_night_nurse_has_no_target_when_nothing_was_put_there_this_turn(cards):
    s = build(cards, ["Night Nurse, Healer of Heroes", "Sol Ring"], forests=20)
    to_gy(s, "Sol Ring")
    next_own_turn(s)
    to_hand(s, "Night Nurse, Healer of Heroes")
    mana(s, W=1, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Night Nurse, Healer of Heroes").id)
    settle(s)
    assert zone(s, "Sol Ring") == "p1:graveyard" and zone(s, "Night Nurse, Healer of Heroes") == "p1:battlefield"
    check(s)


# -- Ghost of Ramirez DePietro: "… target card in a graveyard that was discarded or put there from a library this turn" -------------
def test_ghost_of_ramirez_depietro_returns_a_card_to_its_owners_hand(cards):
    """Discarded or milled cards of either graveyard count; a creature that died (from the battlefield) or was put there earlier does not.
    The card goes to its owner's hand (400.3): the opponent's, if it was theirs."""
    s = build(cards, ["Ghost of Ramirez DePietro", "Llanowar Elves", "Kitchen Finks"], theirs=["Grizzly Bears", "Young Wolf", "Opt", "Sol Ring"],
              forests=20)
    put(s, "Ghost of Ramirez DePietro")
    to_gy(s, "Sol Ring", "p2")  # (an earlier turn)
    next_own_turn(s)
    mill(s, "Grizzly Bears", "p2")  # milled (from the library)
    put(s, "Young Wolf", "p2")
    to_gy(s, "Young Wolf", "p2")  # died (from the battlefield)
    to_hand(s, "Opt", "p2")
    to_gy(s, "Opt", "p2")  # discarded (from a hand)
    mill(s, "Kitchen Finks")  # milled, own
    put(s, "Llanowar Elves")
    to_gy(s, "Llanowar Elves")  # died, own
    attack(s, card_named(s, "Ghost of Ramirez DePietro"))
    assert offered(s) == ["Grizzly Bears", "Kitchen Finks", "Opt"]
    pick(s, "Grizzly Bears")
    settle(s)
    assert zone(s, "Grizzly Bears", "p2") == "p2:hand"
    assert zone(s, "Young Wolf", "p2") == "p2:graveyard" and zone(s, "Sol Ring", "p2") == "p2:graveyard"
    check(s)


# -- Captain N'ghathrod: "choose target artifact or creature card in an opponent's graveyard that was put there from their library" ---
def test_captain_nghathrod_steals_a_card_that_was_milled_this_turn(cards):
    s = build(cards, ["Captain N'ghathrod", "Kitchen Finks"], theirs=["Grizzly Bears", "Young Wolf", "Sol Ring", "Opt", "Llanowar Elves"], forests=20)
    put(s, "Captain N'ghathrod")
    to_gy(s, "Llanowar Elves", "p2")  # (an earlier turn)
    next_own_turn(s)
    mill(s, "Grizzly Bears", "p2")  # milled
    mill(s, "Sol Ring", "p2")  # milled (an artifact)
    mill(s, "Opt", "p2")  # milled, but neither an artifact nor a creature
    put(s, "Young Wolf", "p2")
    to_gy(s, "Young Wolf", "p2")  # died (from the battlefield)
    mill(s, "Kitchen Finks")  # milled, but in your own graveyard
    assert offered(s) == ["Grizzly Bears", "Sol Ring"]  # (at the beginning of the end step)
    pick(s, "Grizzly Bears")
    settle(s)
    bears = card_named(s, "Grizzly Bears", "p2")
    assert bears.zone == "p1:battlefield" and bears.controller == "p1" and bears.owner == "p2"
    assert zone(s, "Young Wolf", "p2") == "p2:graveyard" and zone(s, "Kitchen Finks") == "p1:graveyard"
    check(s)


# -- Storrev: "return to your hand target creature or planeswalker card in your graveyard that wasn't put there this combat" ----------
def test_storrev_cannot_return_a_creature_that_died_in_this_combat(cards):
    """506.1: the Elves died in the combat damage step of this combat; the Bears died in the first main phase, the Wolf last turn."""
    s = build(cards, ["Storrev, Devkarin Lich", "Llanowar Elves", "Young Wolf", "Kitchen Finks"], theirs=["Grizzly Bears"], forests=20)
    put(s, "Storrev, Devkarin Lich")
    put(s, "Llanowar Elves")
    put(s, "Young Wolf")
    to_gy(s, "Young Wolf")  # (an earlier turn)
    next_own_turn(s)
    put(s, "Kitchen Finks")
    to_gy(s, "Kitchen Finks")  # died in the first main phase
    put(s, "Grizzly Bears", "p2")
    attack(s, card_named(s, "Storrev, Devkarin Lich"), card_named(s, "Llanowar Elves"))
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_blockers")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": card_named(s, "Grizzly Bears", "p2").id,
                                                   "attacker_id": card_named(s, "Llanowar Elves").id}])
    assert offered(s) == ["Kitchen Finks", "Young Wolf"]  # (the Elves died in this combat: not offered)
    pick(s, "Young Wolf")
    settle(s)
    assert zone(s, "Young Wolf") == "p1:hand" and zone(s, "Llanowar Elves") == "p1:graveyard" and zone(s, "Kitchen Finks") == "p1:graveyard"
    check(s)


# -- the group wordings: Gleancrawler, Twilight Shepherd, Fell Shepherd, Wreck Hunter ---------------------------------------------
def table_with_dead(cards, mine, **kw):
    s = build(cards, [*mine, "Grizzly Bears", "Llanowar Elves", "Young Wolf", "Kitchen Finks", "Sol Ring", "Opt"], **kw)
    to_gy(s, "Young Wolf")  # (an earlier turn)
    return s


def test_gleancrawler_returns_creatures_that_died_this_turn_at_the_end_step(cards):
    s = table_with_dead(cards, ["Gleancrawler"], forests=20)
    put(s, "Gleancrawler")
    next_own_turn(s)
    put(s, "Grizzly Bears")
    to_gy(s, "Grizzly Bears")  # died
    mill(s, "Kitchen Finks")  # milled: not from the battlefield
    put(s, "Sol Ring")
    to_gy(s, "Sol Ring")  # died as a permanent, but not a creature card
    finish_turn(s)  # (its end step trigger resolves on the way)
    assert zone(s, "Grizzly Bears") == "p1:hand" and zone(s, "Kitchen Finks") == "p1:graveyard" and zone(s, "Sol Ring") == "p1:graveyard"
    assert zone(s, "Young Wolf") == "p1:graveyard"
    check(s)


def test_twilight_shepherd_returns_every_card_put_there_from_the_battlefield(cards):
    s = table_with_dead(cards, ["Twilight Shepherd"], forests=20)
    next_own_turn(s)
    put(s, "Grizzly Bears")
    to_gy(s, "Grizzly Bears")
    put(s, "Sol Ring")
    to_gy(s, "Sol Ring")
    mill(s, "Kitchen Finks")  # milled
    to_hand(s, "Opt")
    to_gy(s, "Opt")  # discarded
    to_hand(s, "Twilight Shepherd")
    mana(s, W=3, G=3)
    cast(s, "Twilight Shepherd")
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:hand" and zone(s, "Sol Ring") == "p1:hand"
    assert zone(s, "Kitchen Finks") == "p1:graveyard" and zone(s, "Opt") == "p1:graveyard" and zone(s, "Young Wolf") == "p1:graveyard"
    check(s)


def test_fell_shepherd_may_return_the_creatures_that_died_this_turn(cards):
    s = table_with_dead(cards, ["Fell Shepherd"], forests=20)
    put(s, "Fell Shepherd")
    next_own_turn(s)
    put(s, "Grizzly Bears")
    to_gy(s, "Grizzly Bears")
    put(s, "Llanowar Elves")
    to_gy(s, "Llanowar Elves")
    mill(s, "Kitchen Finks")
    attack(s, card_named(s, "Fell Shepherd"))
    offered(s)
    assert s.state.rules.decision.kind == "confirm"  # (a "may": yes or no)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["yes"])
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:hand" and zone(s, "Llanowar Elves") == "p1:hand"
    assert zone(s, "Kitchen Finks") == "p1:graveyard" and zone(s, "Young Wolf") == "p1:graveyard"
    check(s)


def test_fell_shepherd_may_leave_them_there(cards):
    s = table_with_dead(cards, ["Fell Shepherd"], forests=20)
    put(s, "Fell Shepherd")
    next_own_turn(s)
    put(s, "Grizzly Bears")
    to_gy(s, "Grizzly Bears")
    attack(s, card_named(s, "Fell Shepherd"))
    offered(s)
    act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["no"])
    settle(s)
    assert zone(s, "Grizzly Bears") == "p1:graveyard"
    check(s)


def test_wreck_hunter_makes_a_powerstone_for_each_nonland_card_that_died_in_that_players_graveyard(cards):
    s = build(cards, ["Wreck Hunter"], theirs=["Grizzly Bears", "Llanowar Elves", "Young Wolf", "Sol Ring", "Opt"], forests=20)
    put(s, "Young Wolf", "p2")
    to_gy(s, "Young Wolf", "p2")  # (an earlier turn)
    next_own_turn(s)
    put(s, "Grizzly Bears", "p2")
    to_gy(s, "Grizzly Bears", "p2")
    put(s, "Sol Ring", "p2")
    to_gy(s, "Sol Ring", "p2")
    put(s, "Llanowar Elves", "p2")
    to_gy(s, "Llanowar Elves", "p2")
    mill(s, "Opt", "p2")  # milled: not from the battlefield
    to_hand(s, "Wreck Hunter")
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Wreck Hunter").id)
    until(s, lambda s: s.state.rules.decision is not None)
    pick(s, "Bob")
    settle(s)
    stones = [c for c in s.state.cards.values() if c.name == "Powerstone" and c.zone == "p1:battlefield"]
    assert len(stones) == 3 and all(c.tapped for c in stones)  # (the Bears, the Sol Ring and the Elves)
    check(s)
