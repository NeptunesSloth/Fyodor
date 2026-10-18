"""Wave 53A: a player's zone as the set an instruction acts on (CR 2026-09-25), real Oracle text (tests/fixtures/wave53a_cards.json, from data/cards.sqlite). Every scenario checks the
replay and a save and a load.

* 400.1, 406.3, 608.2c: "Exile all cards from target player's hand and graveyard." (Identity Crisis), "Target player exiles all land cards from their graveyard." (Mudhole),
  "Target player discards two cards. Then exile that player's graveyard." (Go Blank) - the set is read when the instruction is carried out, from the player the target is; the cards go
  to exile face up.
* 401.2, 701.24a: "Exile all cards from target player's library, then that player shuffles their hand into their library." (Jace, the Mind Sculptor), "Exile all but the bottom card of
  target player's library." (Nicol Bolas, the Arisen); "Shuffle all creature cards from target player's graveyard into that player's library." (Repopulate).
* 701.24a: "Look at the top three cards of target player's library, then put them back in any order. You may have that player shuffle." (Portent, Natural Selection, Visions) - the
  controller decides whether that player shuffles; "Then that player shuffles." (Prophecy) is the target player.
* 607.2a: Hypnox exiles every card in the opponent's hand and returns them when it leaves the battlefield.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_wave34b_activated import activate
from tests.wave9c_kit import card_named, check, life, mana, put, to_hand
from tests.wave53a_kit import open_repo, table

BEARS, GIANT = "Grizzly Bears", "Hill Giant"
NAMES = ["Identity Crisis", "Mudhole", "Jace, the Mind Sculptor", "Nicol Bolas, the Ravager // Nicol Bolas, the Arisen", "Go Blank", "Repopulate", "Portent", "Natural Selection", "Visions",
         "Prophecy", "Hypnox"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", NAMES)
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def zone(s, pid, z):
    return sorted(s.state.cards[c].name for c in s.state.zones.get(f"{pid}:{z}", []))


def names(s, pid):
    return [s.state.cards[c].name for c in s.state.zones[f"{pid}:library"]]


def move(s, name, z, pid):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"zone": z, "player": pid} if z == "battlefield" else {"zone": z})
    return c


def three(cards, alice=(), bob=(), carol=()):
    return table(cards, alice, bob, carol)


# -- Identity Crisis / Mudhole / Go Blank ------------------------------------------------------------------------------------------------
def test_identity_crisis_exiles_the_hand_and_graveyard_of_the_target_player_only(cards):
    s = three(cards, ["Identity Crisis"], [BEARS, GIANT, "Mudhole"], [BEARS, GIANT])
    for name in (BEARS, GIANT):
        to_hand(s, name, "p2")
        to_hand(s, name, "p3")
    move(s, "Mudhole", "graveyard", "p2")
    to_hand(s, "Identity Crisis")
    mana(s, "p1", W=2, B=2, C=2)
    before_carol = (zone(s, "p3", "hand"), zone(s, "p3", "graveyard"))
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Identity Crisis").id, targets=["p2"])
    settle(s)
    assert zone(s, "p2", "hand") == [] and zone(s, "p2", "graveyard") == []
    assert zone(s, "p2", "exile") == sorted([BEARS, GIANT, "Mudhole"])
    assert (zone(s, "p3", "hand"), zone(s, "p3", "graveyard")) == before_carol  # Carol's are not Bob's
    check(s)


def test_mudhole_exiles_only_the_land_cards_of_the_graveyard(cards):
    s = three(cards, ["Mudhole"], [BEARS], [])
    move(s, BEARS, "graveyard", "p2")
    for c in list(s.state.zones["p2:library"])[-2:]:  # two Islands go to the graveyard too
        act(s, "p2", type="move", card_ids=[c], to={"zone": "graveyard"})
    to_hand(s, "Mudhole")
    mana(s, "p1", R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Mudhole").id, targets=["p2"])
    settle(s)
    assert zone(s, "p2", "graveyard") == [BEARS]  # the creature card stays
    assert zone(s, "p2", "exile") == ["Island", "Island"]
    check(s)


def test_go_blank_exiles_the_graveyard_the_discards_went_to(cards):
    s = three(cards, ["Go Blank"], [BEARS, GIANT, "Mudhole"], [])
    for name in (BEARS, GIANT):
        to_hand(s, name, "p2")
    move(s, "Mudhole", "graveyard", "p2")
    to_hand(s, "Go Blank")
    mana(s, "p1", B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Go Blank").id, targets=["p2"])
    settle(s)  # Bob discards the two cards in his hand (a choice only when he has more)
    assert zone(s, "p2", "graveyard") == [] and zone(s, "p2", "exile") == sorted([BEARS, GIANT, "Mudhole"])
    check(s)


# -- Repopulate --------------------------------------------------------------------------------------------------------------------------
def test_repopulate_shuffles_the_creature_cards_of_the_graveyard_into_that_players_library(cards):
    s = three(cards, ["Repopulate"], [BEARS, GIANT], [BEARS])
    move(s, BEARS, "graveyard", "p2")
    move(s, GIANT, "graveyard", "p2")
    act(s, "p2", type="move", card_ids=[s.state.zones["p2:library"][-1]], to={"zone": "graveyard"})  # an Island
    move(s, BEARS, "graveyard", "p3")
    library = len(s.state.zones["p2:library"])
    to_hand(s, "Repopulate")
    mana(s, "p1", G=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Repopulate").id, targets=["p2"])
    settle(s)
    assert zone(s, "p2", "graveyard") == ["Island"] and len(s.state.zones["p2:library"]) == library + 2
    assert zone(s, "p3", "graveyard") == [BEARS]  # Carol's graveyard is not Bob's
    check(s)


# -- Jace, the Mind Sculptor -------------------------------------------------------------------------------------------------------------
def test_jace_the_mind_sculptor_ultimate_exiles_the_library_and_shuffles_the_hand_in(cards):
    s = three(cards, ["Jace, the Mind Sculptor"], [BEARS, GIANT], [])
    jace = put(s, "Jace, the Mind Sculptor")
    act(s, "p1", type="counter", card_ids=[jace.id], kind="loyalty", delta=12)
    to_hand(s, BEARS, "p2")
    to_hand(s, GIANT, "p2")
    in_library = sorted(s.state.cards[c].name for c in s.state.zones["p2:library"])
    activate(s, "p1", jace, contains="−12", targets=["p2"])
    settle(s)
    assert zone(s, "p2", "exile") == in_library  # every card the library held
    assert zone(s, "p2", "hand") == [] and zone(s, "p2", "library") == sorted([BEARS, GIANT])  # the hand is the library now
    check(s)


# -- Nicol Bolas, the Arisen ---------------------------------------------------------------------------------------------------------------
def test_nicol_bolas_the_arisen_exiles_all_but_the_bottom_card(cards):
    s = three(cards, ["Nicol Bolas, the Ravager // Nicol Bolas, the Arisen"], [], [BEARS, GIANT])
    bolas = put(s, "Nicol Bolas, the Ravager // Nicol Bolas, the Arisen")
    mana(s, "p1", U=1, B=1, R=1, C=4)
    activate(s, "p1", bolas, contains="Exile Nicol Bolas")
    settle(s)
    bolas = s.state.cards[bolas.id]
    assert bolas.zone == "p1:battlefield"
    act(s, "p1", type="counter", card_ids=[bolas.id], kind="loyalty", delta=12)
    library = list(s.state.zones["p3:library"])
    bottom = library[-1]
    activate(s, "p1", bolas, contains="−12", targets=["p3"])
    settle(s)
    assert list(s.state.zones["p3:library"]) == [bottom] and sorted(s.state.cards[c].name for c in s.state.zones["p3:exile"]) == sorted(s.state.cards[c].name for c in library[:-1])
    check(s)


# -- Portent / Visions / Prophecy ---------------------------------------------------------------------------------------------------------
def answer(s, option):
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])


def test_portent_you_decide_whether_that_player_shuffles(cards):
    s = three(cards, ["Portent"], [BEARS, GIANT, "Mudhole"], [])
    to_hand(s, "Portent")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Portent").id, targets=["p2"])
    settle_to_shuffle = 0
    while (d := s.state.rules.decision) is None or d.kind != "confirm":
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
        settle_to_shuffle += 1
        assert settle_to_shuffle < 20
    assert d.player == "p1" and "Bob" in d.prompt  # Alice is asked, about Bob's library
    arranged = list(s.state.zones["p2:library"])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    settle(s)
    assert list(s.state.zones["p2:library"]) == arranged  # not shuffled: the same cards in the same order, the same objects
    check(s)


def test_portent_shuffled(cards):
    s = three(cards, ["Portent"], [BEARS, GIANT, "Mudhole"], [])
    to_hand(s, "Portent")
    mana(s, "p1", U=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Portent").id, targets=["p2"])
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "confirm":
            break
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    arranged = names(s, "p2")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    settle(s)
    assert sorted(names(s, "p2")) == sorted(arranged) and names(s, "p2") != arranged  # the same cards, in another order (the library is re-keyed by a shuffle)
    check(s)


def test_prophecy_reveals_the_top_card_gains_for_a_land_and_shuffles_their_library(cards):
    s = three(cards, ["Prophecy"], [GIANT], [])
    # Bob's top card is the Giant: not a land, no life; then Bob's library is shuffled
    to_hand(s, "Prophecy")
    mana(s, "p1", W=1)
    before = names(s, "p2")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Prophecy").id, targets=["p2"])
    settle(s)
    assert life(s, "p1") == 40 and sorted(names(s, "p2")) == sorted(before) and names(s, "p2") != before
    check(s)


def test_prophecy_a_land_on_top_gains_one_life(cards):
    s = three(cards, ["Prophecy"], [], [])
    to_hand(s, "Prophecy")
    mana(s, "p1", W=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Prophecy").id, targets=["p2"])
    settle(s)
    assert life(s, "p1") == 41
    check(s)


# -- Hypnox ------------------------------------------------------------------------------------------------------------------------------
def test_hypnox_returns_the_hand_it_exiled_when_it_leaves(cards):
    s = three(cards, ["Hypnox", "Murder"], [BEARS, GIANT], [BEARS])
    for name in (BEARS, GIANT):
        to_hand(s, name, "p2")
    to_hand(s, BEARS, "p3")
    to_hand(s, "Hypnox")
    mana(s, "p1", B=3, C=8)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Hypnox").id)
    settle(s)  # the creature spell resolves, its enter trigger asks for a target opponent (first option: Bob)
    assert zone(s, "p2", "hand") == [] and zone(s, "p2", "exile") == sorted([BEARS, GIANT]) and zone(s, "p3", "hand") == [BEARS]
    to_hand(s, "Murder")
    mana(s, "p1", B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Murder").id, targets=[card_named(s, "Hypnox").id])
    settle(s)
    assert zone(s, "p2", "hand") == sorted([BEARS, GIANT]) and zone(s, "p2", "exile") == []
    check(s)
