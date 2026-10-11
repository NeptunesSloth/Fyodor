"""Wave 35C: keyword actions replaced by other instructions (CR 614.1a, 614.5, 616.1, 701.22, 701.44, 701.50), real Oracle text
(tests/fixtures/wave35c_cards.json). Every scenario checks the replay and a save and a load.

* "If you would scry a number of cards, draw that many cards instead." (Eligeth, Crossroads Augur): the scry never happens (614.6), they draw.
* "If a creature you control would explore, instead it explores, then it explores again." (Topography Tracker) and "… instead you scry 1, then that creature
  explores." (Twists and Turns): the action is the event; what the replacement makes is not replaced by it again (614.5), so two Trackers explore four times
  and two Twists scry twice (the Gatherer rulings).
* "If a creature you control would connive, instead you draw a card, then that creature connives." (Leader, Super-Genius).
* 616.1: a Tracker and Twists and Turns on one explore make different results in different orders (two scries, or one): the creature's controller is asked.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, check, mana, put, reloaded, to_hand
from tests.wave35c_kit import cast_from_hand, repository

FULL = ["Topography Tracker", "Twists and Turns // Mycoid Maze", "Leader, Super-Genius", "Eligeth, Crossroads Augur"]


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", FULL)
def test_the_promoted_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def hand(s, pid="p1"):
    return len(s.state.zones[f"{pid}:hand"])


def play_on(s, picks=(), limit=40):
    """Resolve everything; a decision is answered by label (a pick that is a substring of an option), else with its first options. Returns the decisions' prompts."""
    asked, picks = [], list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            asked.append(d.prompt)
            want = picks.pop(0) if picks else None
            ids = [o.id for o in d.options if want and want in o.label] or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return asked
    raise AssertionError("never settled")


def branchwalker(s):
    """Cast Merfolk Branchwalker ({1}{G}): "When this creature enters, it explores." with a Forest on top of the library each time (a land: to the hand)."""
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Merfolk Branchwalker" and c.owner == "p1"))
    return play_on(s)


def with_branchwalker_in_hand(s):
    to_hand(s, "Merfolk Branchwalker")


@pytest.mark.parametrize("trackers, explores", [(0, 1), (1, 2), (2, 4)])
def test_topography_tracker_explores_again_and_each_tracker_multiplies(cards, trackers, explores):
    """A land is revealed each time (the library is Forests): one card to the hand per explore. Two Trackers: each applies once to every explore the other made."""
    s = build(cards, ["Merfolk Branchwalker", *["Topography Tracker"] * trackers], [], forests=9)
    for c in [c for c in s.state.cards.values() if c.name == "Topography Tracker" and c.owner == "p1"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    with_branchwalker_in_hand(s)
    before = hand(s)
    branchwalker(s)
    assert hand(s) == before - 1 + explores and s.state.rules.decision is None  # (the Branchwalker left the hand)
    s = reloaded(s)
    check(s)


def test_twists_and_turns_scries_first(cards):
    s = build(cards, ["Merfolk Branchwalker", "Twists and Turns // Mycoid Maze"], [], forests=9)
    put(s, "Twists and Turns // Mycoid Maze")
    with_branchwalker_in_hand(s)
    before = hand(s)
    mana(s, "p1", G=2)
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Merfolk Branchwalker"))
    asked = play_on(s)
    assert sum(p.startswith("Scry") for p in asked) == 1 and hand(s) == before - 1 + 1
    s = reloaded(s)
    check(s)


def test_a_tracker_and_twists_and_turns_ask_the_order(cards):
    """616.1: Tracker first: two explores, each replaced by Twists and Turns: scry, explore, scry, explore (2 scries). Twists first: scry, then the explore is
    replaced by the Tracker: explore, explore (1 scry). Either way two lands come to the hand."""
    for first, scries in (("Topography Tracker first", 2), ("Twists and Turns first", 1)):
        s = build(cards, ["Merfolk Branchwalker", "Topography Tracker", "Twists and Turns // Mycoid Maze"], [], forests=9)
        put(s, "Topography Tracker")
        put(s, "Twists and Turns // Mycoid Maze")
        with_branchwalker_in_hand(s)
        before = hand(s)
        mana(s, "p1", G=2)
        act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Merfolk Branchwalker"))
        for _ in range(8):
            if s.state.rules.decision is not None:
                break
            act(s, s.state.rules.priority, type="pass_priority")
        d = s.state.rules.decision
        assert d is not None and d.player == "p1" and any(first in o.label for o in d.options), d
        s = reloaded(s)  # the question survives a save and a load
        d = s.state.rules.decision
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if first in o.label)])
        asked = play_on(s)
        assert sum(p.startswith("Scry") for p in asked) == scries and hand(s) == before - 1 + 2
        check(s)


@pytest.mark.parametrize("leaders, net", [(0, -1), (1, 0)])
def test_leader_draws_a_card_before_the_connive(cards, leaders, net):
    """Raffine's Informant connives when it enters (draw, discard): cast (-1 card in hand), the connive's draw and discard cancel; Leader adds a draw
    before it."""
    s = build(cards, ["Raffine's Informant", *["Leader, Super-Genius"] * leaders], [], forests=9)
    for c in [c for c in s.state.cards.values() if c.name == "Leader, Super-Genius" and c.owner == "p1"]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    to_hand(s, "Raffine's Informant")
    before = hand(s)  # includes the Informant
    mana(s, "p1", W=2)
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == "Raffine's Informant"))
    play_on(s)
    assert hand(s) == before + net
    s = reloaded(s)
    check(s)


def test_eligeth_draws_instead_of_scrying(cards):
    s = build(cards, ["Eligeth, Crossroads Augur", "Preordain"], [], forests=9)
    put(s, "Eligeth, Crossroads Augur")
    mana(s, "p1", U=1)
    before = hand(s)
    cast_from_hand(s, "Preordain")  # "Scry 2, then draw a card": draw 2 instead of the scry, then the card
    assert hand(s) == before + 3
    s = reloaded(s)
    check(s)
