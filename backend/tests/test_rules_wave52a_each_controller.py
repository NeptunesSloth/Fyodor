"""Wave 52A: "For each [object] exiled / died this way, its controller [does a thing]" (CR 2026-09-25), real Oracle text (tests/fixtures/wave52a_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 608.2c / 608.2h / 109.4: the instruction is done once for each object the earlier instruction acted on, by the controller that object last had: Martyr's Cry and King
  Solomon's Frogs ("its controller draws a card"), Unexplained Absence ("its controller cloaks the top card of their library"), Declaration in Stone ("That player
  investigates for each nontoken creature exiled this way": the target's controller, who controlled every one of them), Mogg Infestation ("that player creates two 1/1 red
  Goblin creature tokens" for each creature that died: the target player controlled them all).
* 608.2c: Warren Weirding - "If a Goblin is sacrificed this way, that player creates two 1/1 black Goblin Rogue creature tokens, and those tokens gain haste until end of turn."
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, cast, check, mana, put, to_hand, zone_of
from tests.wave52a_kit import build_n, open_repo, put_all

CRY, FROGS, ABSENCE, DECLARATION, INFESTATION, WEIRDING = (
    "Martyr's Cry", "King Solomon's Frogs", "Unexplained Absence", "Declaration in Stone", "Mogg Infestation", "Warren Weirding")


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [CRY, FROGS, ABSENCE, DECLARATION, INFESTATION, WEIRDING])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def hand(s, pid):
    return sum(1 for c in s.state.cards.values() if c.zone == f"{pid}:hand")


def tokens(s, name, pid):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.zone == f"{pid}:battlefield"]


# -- Martyr's Cry ------------------------------------------------------------------------------------------------------------------------
def test_martyrs_cry_each_controller_draws_a_card_for_each_creature_of_theirs_exiled(cards):
    s = build(cards, [CRY, "Soul Warden"], ["Soul Warden", "Kitchen Finks", "Grizzly Bears"])
    put(s, "Soul Warden")
    put(s, "Soul Warden", "p2")
    put(s, "Kitchen Finks", "p2")  # green-white: a white creature
    put(s, "Grizzly Bears", "p2")
    to_hand(s, CRY)
    mana(s, "p1", W=2)
    mine, theirs = hand(s, "p1") - 1, hand(s, "p2")  # (the spell leaves the hand as it is cast)
    cast(s, CRY)
    assert zone_of(s, "Soul Warden") == "p1:exile" and zone_of(s, "Soul Warden", "p2") == "p2:exile" and zone_of(s, "Kitchen Finks", "p2") == "p2:exile"
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:battlefield"  # not white
    assert hand(s, "p1") == mine + 1 and hand(s, "p2") == theirs + 2  # one for Alice's creature, two for Bob's: each controller's own count
    check(s)


# -- Unexplained Absence -----------------------------------------------------------------------------------------------------------------
def test_unexplained_absence_each_controller_cloaks_the_top_card_of_their_library(cards):
    s = build(cards, [ABSENCE, "Grizzly Bears"], ["Hill Giant"])
    bears = put(s, "Grizzly Bears")
    giant = put(s, "Hill Giant", "p2")
    to_hand(s, ABSENCE)
    mana(s, "p1", W=1, C=3)
    lib = {p: len([c for c in s.state.cards.values() if c.zone == f"{p}:library"]) for p in ("p1", "p2")}
    act(s, "p1", type="cast_spell", card_id=card_named(s, ABSENCE).id, targets=[bears.id, giant.id], target_counts=[1, 1])
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:exile" and zone_of(s, "Hill Giant", "p2") == "p2:exile"
    for p in ("p1", "p2"):  # each controller cloaked the top card of their own library: a face-down 2/2 creature (701.58a)
        cloaked = [c for c in s.state.cards.values() if c.zone == f"{p}:battlefield" and c.face_down_kind == "cloak"]
        assert len(cloaked) == 1 and cloaked[0].controller == p
        assert len([c for c in s.state.cards.values() if c.zone == f"{p}:library"]) == lib[p] - 1
    check(s)


# -- King Solomon's Frogs ----------------------------------------------------------------------------------------------------------------
def test_frogs_exiles_a_permanent_of_each_opponent_and_its_controller_draws(cards):
    s = build(cards, [FROGS], ["Hill Giant", "Grizzly Bears"])
    put(s, "Hill Giant", "p2")  # mana value 4: legal
    put(s, "Grizzly Bears", "p2")  # mana value 2: not
    to_hand(s, FROGS)
    mana(s, "p1", W=1, C=3)
    mine, theirs = hand(s, "p1"), hand(s, "p2")
    act(s, "p1", type="cast_spell", card_id=card_named(s, FROGS).id)
    settle(s)  # (the spell resolves; its enters trigger asks for the target)
    assert zone_of(s, FROGS) == "p1:battlefield"
    assert zone_of(s, "Hill Giant", "p2") == "p2:exile" and zone_of(s, "Grizzly Bears", "p2") == "p2:battlefield"
    assert hand(s, "p2") == theirs + 1 and hand(s, "p1") == mine - 1  # the exiled permanent's controller draws, not Alice (who only cast the Frogs)
    check(s)


# -- Declaration in Stone ----------------------------------------------------------------------------------------------------------------
def test_declaration_in_stone_investigates_once_for_each_nontoken_creature_exiled(cards):
    s = build_n(cards, [DECLARATION], [(2, "Grizzly Bears"), "Hill Giant"])
    bears = put_all(s, "Grizzly Bears", "p2")
    put(s, "Hill Giant", "p2")
    to_hand(s, DECLARATION)
    mana(s, "p1", W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, DECLARATION).id, targets=[bears[0].id])
    settle(s)
    assert all(zone_of(s, "Grizzly Bears", "p2") == "p2:exile" for _ in bears) and {c.zone for c in bears} == {"p2:exile"}
    assert zone_of(s, "Hill Giant", "p2") == "p2:battlefield"
    clues = tokens(s, "Clue", "p2")
    assert len(clues) == 2 and not tokens(s, "Clue", "p1")  # that player investigates: twice, for the two Bears exiled
    check(s)


# -- Mogg Infestation --------------------------------------------------------------------------------------------------------------------
def test_mogg_infestation_the_target_player_gets_two_goblins_for_each_creature_that_died(cards):
    s = build(cards, [INFESTATION, "Goblin Piker"], ["Hill Giant", "Grizzly Bears"])
    put(s, "Goblin Piker")
    put(s, "Hill Giant", "p2")
    put(s, "Grizzly Bears", "p2")
    to_hand(s, INFESTATION)
    mana(s, "p1", R=2, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, INFESTATION).id, targets=["p2"])
    settle(s)
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard" and zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    assert zone_of(s, "Goblin Piker") == "p1:battlefield"  # Alice's creature is not the target player's
    assert len(tokens(s, "Goblin", "p2")) == 4 and not tokens(s, "Goblin", "p1")
    check(s)


# -- Warren Weirding ---------------------------------------------------------------------------------------------------------------------
def test_warren_weirding_a_goblin_sacrificed_gives_two_hasty_goblin_rogues(cards):
    s = build(cards, [WEIRDING], ["Goblin Piker"])
    put(s, "Goblin Piker", "p2")
    to_hand(s, WEIRDING)
    mana(s, "p1", B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, WEIRDING).id, targets=["p2"])
    settle(s)
    assert zone_of(s, "Goblin Piker", "p2") == "p2:graveyard"
    rogues = tokens(s, "Goblin Rogue", "p2")
    assert len(rogues) == 2 and not tokens(s, "Goblin Rogue", "p1")
    assert all("haste" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).keywords for c in rogues)  # "those tokens gain haste until end of turn"
    check(s)


def test_warren_weirding_no_goblin_sacrificed_no_tokens(cards):
    s = build(cards, [WEIRDING], ["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    to_hand(s, WEIRDING)
    mana(s, "p1", B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, WEIRDING).id, targets=["p2"])
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard" and not tokens(s, "Goblin Rogue", "p2")
    check(s)
