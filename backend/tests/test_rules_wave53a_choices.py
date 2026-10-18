"""Wave 53A: a choice made for each player among the cards of their graveyard (CR 2026-09-25), real Oracle text (tests/fixtures/wave53a_cards.json, from data/cards.sqlite). Every
scenario checks the replay and a save and a load.

* 101.4, 101.4b: every player makes their choice in turn order, the active player first, each knowing the earlier ones; "For each player, choose ..." (Breach the Multiverse) is the
  controller's choice for each player, "Each player puts ... from their graveyard" (Exhume, Crypt Champion, Fall of the Thran) each player's own.
* 608.2c, 110.2a: nothing moves until every choice is made, then all at once; "Put those cards onto the battlefield under your control" takes them to the controller, "Each player
  puts ... onto the battlefield" each to its owner.
* 608.2d: "may" and "up to" always ask (Enslaved Horror); with one card to choose from no question is asked (a graveyard is public, 404.2).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import card_named, check, mana, put, to_hand
from tests.wave53a_kit import open_repo, table, until_asked

BEARS, GIANT, ANGEL, GRAIL = "Grizzly Bears", "Hill Giant", "Serra Angel", "Sol Grail"
NAMES = ["Breach the Multiverse", "Exhume", "Crypt Champion", "Fall of the Thran", "Dredge the Mire", "Scrounge", "Enslaved Horror"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", NAMES)
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def to_gy(s, name, pid):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone.endswith((":library", ":hand")))
    act(s, pid, type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def where(s, c):
    return s.state.cards[c.id].zone, s.state.cards[c.id].controller


def answer(s, c, who):
    d = until_asked(s)
    assert d.player == who, (d.player, who)
    act(s, who, type="choose", decision_id=d.id, option_ids=[c.id])
    return d


# -- Breach the Multiverse ---------------------------------------------------------------------------------------------------------------
def test_breach_the_multiverse_you_choose_a_card_in_each_graveyard_and_they_all_become_phyrexians(cards):
    s = table(cards, ["Breach the Multiverse", GIANT], [BEARS, ANGEL], [])
    giant, bears, angel = to_gy(s, GIANT, "p1"), to_gy(s, BEARS, "p2"), to_gy(s, ANGEL, "p2")
    to_hand(s, "Breach the Multiverse")
    mana(s, "p1", B=2, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Breach the Multiverse").id)
    d = answer(s, angel, "p1")  # Alice's own graveyard has one card (no question); Bob's has two: Alice picks, knowing it's her choice for him
    assert {o.id for o in d.options} == {bears.id, angel.id}
    settle(s)
    assert where(s, giant) == ("p1:battlefield", "p1") and where(s, angel) == ("p1:battlefield", "p1") and s.state.cards[angel.id].owner == "p2"
    assert s.state.cards[bears.id].zone == "p2:graveyard"  # the card she didn't choose stays
    plan = Plan(s.state, "p1", s.cards, None)
    assert "Phyrexian" in plan.ch(s.state.cards[giant.id]).subtypes and "Phyrexian" in plan.ch(s.state.cards[angel.id]).subtypes  # "each creature you control", the new ones too
    check(s)


def test_breach_the_multiverse_a_player_with_no_such_card_is_skipped(cards):
    s = table(cards, ["Breach the Multiverse"], [], [BEARS])
    bears = to_gy(s, BEARS, "p3")
    to_hand(s, "Breach the Multiverse")
    mana(s, "p1", B=2, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Breach the Multiverse").id)
    settle(s)  # the ten cards each milled are lands: Carol's Bears are the only card to choose, no question
    assert where(s, bears) == ("p1:battlefield", "p1")
    check(s)


# -- Exhume / Crypt Champion ---------------------------------------------------------------------------------------------------------------
def test_exhume_each_player_puts_their_own_card_onto_the_battlefield_at_once(cards):
    s = table(cards, ["Exhume", GIANT], [BEARS, ANGEL], [BEARS])
    giant, bears, angel, carols = to_gy(s, GIANT, "p1"), to_gy(s, BEARS, "p2"), to_gy(s, ANGEL, "p2"), to_gy(s, BEARS, "p3")
    to_hand(s, "Exhume")
    mana(s, "p1", B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Exhume").id)
    d = answer(s, angel, "p2")  # Bob chooses from his own graveyard: Alice's and Carol's single cards need no question
    assert {o.id for o in d.options} == {bears.id, angel.id}
    settle(s)
    assert where(s, giant) == ("p1:battlefield", "p1") and where(s, angel) == ("p2:battlefield", "p2") and where(s, carols) == ("p3:battlefield", "p3")
    assert s.state.cards[bears.id].zone == "p2:graveyard"
    check(s)


def test_crypt_champion_only_cards_with_mana_value_three_or_less(cards):
    s = table(cards, ["Crypt Champion"], [BEARS, ANGEL], [])
    bears, angel = to_gy(s, BEARS, "p2"), to_gy(s, ANGEL, "p2")
    to_hand(s, "Crypt Champion")
    mana(s, "p1", B=1, R=1, C=2)  # {R} spent: it isn't sacrificed
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Crypt Champion").id)
    settle(s)  # the Angel (mana value 5) isn't one to choose; the Bears are the only card: no question
    assert where(s, bears) == ("p2:battlefield", "p2") and s.state.cards[angel.id].zone == "p2:graveyard"
    check(s)


# -- Fall of the Thran --------------------------------------------------------------------------------------------------------------------
def test_fall_of_the_thran_chapter_two_each_player_returns_two_lands(cards):
    s = table(cards, ["Fall of the Thran"], [], [], lands=10)
    lands = [to_gy(s, "Forest", "p1") for _ in range(3)]
    bobs = [to_gy(s, "Island", "p2") for _ in range(2)]
    saga = put(s, "Fall of the Thran")
    settle(s)  # chapter I: destroy all lands (none on the table)
    act(s, "p1", type="counter", card_ids=[saga.id], kind="lore", delta=1)
    d = until_asked(s)
    assert d.player == "p1" and {o.id for o in d.options} == {c.id for c in lands}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[lands[0].id, lands[2].id])
    settle(s)  # Bob has exactly two: no question; Carol none
    assert [where(s, c)[0] for c in lands] == ["p1:battlefield", "p1:graveyard", "p1:battlefield"]
    assert all(where(s, c) == ("p2:battlefield", "p2") for c in bobs)
    check(s)


# -- Dredge the Mire / Scrounge ---------------------------------------------------------------------------------------------------------
def test_dredge_the_mire_each_opponent_chooses_and_you_get_the_cards(cards):
    s = table(cards, ["Dredge the Mire", GIANT], [BEARS, ANGEL], [BEARS])
    mine, bears, angel, carols = to_gy(s, GIANT, "p1"), to_gy(s, BEARS, "p2"), to_gy(s, ANGEL, "p2"), to_gy(s, BEARS, "p3")
    to_hand(s, "Dredge the Mire")
    mana(s, "p1", B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Dredge the Mire").id)
    d = answer(s, bears, "p2")  # Bob picks which of his cards Alice gets
    assert {o.id for o in d.options} == {bears.id, angel.id}
    settle(s)
    assert where(s, bears) == ("p1:battlefield", "p1") and where(s, carols) == ("p1:battlefield", "p1")
    assert s.state.cards[angel.id].zone == "p2:graveyard" and s.state.cards[mine.id].zone == "p1:graveyard"  # Alice's own graveyard isn't asked
    assert s.state.cards[bears.id].owner == "p2"
    check(s)


def test_scrounge_the_target_opponent_chooses_an_artifact_card(cards):
    s = table(cards, ["Scrounge"], [(2, GRAIL)], [GRAIL])
    one = to_gy(s, GRAIL, "p2")
    two = to_gy(s, GRAIL, "p2")
    carols = to_gy(s, GRAIL, "p3")
    to_hand(s, "Scrounge")
    mana(s, "p1", B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Scrounge").id, targets=["p2"])
    d = answer(s, two, "p2")
    assert {o.id for o in d.options} == {one.id, two.id}
    settle(s)
    assert where(s, two) == ("p1:battlefield", "p1") and s.state.cards[one.id].zone == "p2:graveyard" and s.state.cards[carols.id].zone == "p3:graveyard"
    check(s)


# -- Enslaved Horror -----------------------------------------------------------------------------------------------------------------------
def horror(cards, take):
    s = table(cards, ["Enslaved Horror", GIANT], [BEARS], [BEARS])
    mine, bears, carols = to_gy(s, GIANT, "p1"), to_gy(s, BEARS, "p2"), to_gy(s, BEARS, "p3")
    to_hand(s, "Enslaved Horror")
    mana(s, "p1", B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Enslaved Horror").id)
    for who, c in (("p2", bears), ("p3", carols)):
        d = until_asked(s)  # "each other player may": always asked, in turn order (Alice's own graveyard is not part of it)
        assert d.player == who and d.min_choices == 0 and {o.id for o in d.options} == {c.id}
        act(s, who, type="choose", decision_id=d.id, option_ids=[c.id] if take[who] else [])
    settle(s)
    return s, mine, bears, carols


def test_enslaved_horror_other_players_may_return_a_creature_card(cards):
    s, mine, bears, carols = horror(cards, {"p2": True, "p3": False})
    assert where(s, bears) == ("p2:battlefield", "p2") and s.state.cards[carols.id].zone == "p3:graveyard" and s.state.cards[mine.id].zone == "p1:graveyard"
    check(s)
