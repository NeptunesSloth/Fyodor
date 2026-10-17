"""Wave 47B: votes for a player (CR 2026-09-25, 701.38), real Oracle text (tests/fixtures/wave47b_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 701.38a: each player, starting with a specified player and proceeding in turn order, votes. Mob Verdict: "another player" (nobody votes for themself,
  ruling 2024-02-02); Círdan: "a player". A secret vote is private to its voter until every ballot is in, then all are revealed at once (rulings).
* Círdan ruling 2023-06-16: after the reveal the player whose turn it is draws a card for each vote they received, then each other player in turn
  order; then each player who received no votes may put a permanent card from their hand onto the battlefield, in the same order.
* Mob Verdict: "For each vote an opponent received, Mob Verdict deals 2 damage to that player and each creature that player controls. For each vote you
  received, draw a card."
"""

from __future__ import annotations

import json

import pytest

from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import card_named, check, mana, put, to_hand
from tests.wave47b_kit import build3, life, open_cards, pin_random


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


def ballot(s, pid, target):
    d = s.state.rules.decision
    assert d is not None and d.player == pid and d.kind == "choose_one", (d.player if d else None, pid)
    act(s, pid, type="choose", decision_id=d.id, option_ids=[target])


def hand(s, pid):
    return len(s.state.zones[f"{pid}:hand"])


def start_mob_verdict(cards):
    s = build3(cards, ["Mob Verdict"], bobs=["Grizzly Bears"])
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Mob Verdict")
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Mob Verdict").id)
    return s


def test_mob_verdict_nobody_votes_for_themself_and_votes_are_secret_until_all_are_in(cards):
    s = start_mob_verdict(cards)
    settle_to_vote(s)
    d = s.state.rules.decision
    assert d.player == "p1" and {o.id for o in d.options} == {"p2", "p3"}  # Alice: another player
    ballot(s, "p1", "p2")
    d = s.state.rules.decision
    assert d.player == "p2" and {o.id for o in d.options} == {"p1", "p3"}  # Bob next, in turn order
    assert "voted" not in json.dumps(s.view("p3")["log"])  # Alice's ballot is hers alone for now
    check(s)  # a save and a load with the vote half done
    ballot(s, "p2", "p1")
    ballot(s, "p3", "p2")
    settle(s)
    log = json.dumps(s.view("p3")["log"])
    assert "The votes are revealed" in log and "Alice voted for Bob" in log and "Bob voted for Alice" in log and "Carol voted for Bob" in log
    check(s)


def test_mob_verdict_hurts_an_opponent_per_vote_received_and_draws_per_vote_you_received(cards):
    s = start_mob_verdict(cards)
    settle_to_vote(s)
    cards_before = hand(s, "p1")
    ballot(s, "p1", "p2")
    ballot(s, "p2", "p1")
    ballot(s, "p3", "p2")  # Bob has two votes, Alice one, Carol none
    settle(s)
    assert life(s, "p2") == 40 - 2 * 2 and life(s, "p3") == 40  # 2 damage for each vote Bob received
    assert s.state.cards[card_named(s, "Grizzly Bears", "p2").id].zone == "p2:graveyard"  # (and to each creature he controls)
    assert hand(s, "p1") == cards_before + 1  # one vote for Alice: one card
    assert life(s, "p1") == 40
    check(s)


def settle_to_vote(s):
    """Pass priority until the first ballot is asked (the spell resolves; nothing else is in the way)."""
    for _ in range(10):
        if s.state.rules.decision is not None:
            return
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no vote was asked")


# -- Círdan the Shipwright -----------------------------------------------------------------------------------------------------------------
def start_cirdan(cards):
    s = build3(cards, ["Círdan the Shipwright"])
    act(s, "p3", type="draw", player="p3", count=3)  # (Carol's hand: Islands)
    to_hand(s, "Círdan the Shipwright")
    mana(s, G=1, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Círdan the Shipwright").id)
    settle_to_vote(s)
    return s


def test_cirdan_draws_a_card_per_vote_received_and_a_player_with_none_may_put_a_permanent(cards):
    s = start_cirdan(cards)
    before = {p: hand(s, p) for p in ("p1", "p2", "p3")}
    ballot(s, "p1", "p2")
    ballot(s, "p2", "p1")
    ballot(s, "p3", "p1")  # Alice two votes, Bob one, Carol none
    d = s.state.rules.decision
    assert d is not None and d.player == "p3" and d.kind == "choose_cards"  # Carol, with no votes: a permanent card from her hand
    assert {p: hand(s, p) - before[p] for p in before} == {"p1": 2, "p2": 1, "p3": 0}
    check(s)
    land = d.options[0].id
    act(s, "p3", type="choose", decision_id=d.id, option_ids=[land])
    settle(s)
    assert s.state.cards[land].zone == "p3:battlefield"
    check(s)


def test_cirdan_a_vote_where_everyone_got_one_gives_everyone_a_card_and_nobody_puts_anything(cards):
    s = start_cirdan(cards)
    before = {p: hand(s, p) for p in ("p1", "p2", "p3")}
    ballot(s, "p1", "p2")
    ballot(s, "p2", "p3")
    ballot(s, "p3", "p1")
    settle(s)
    assert s.state.rules.decision is None
    assert {p: hand(s, p) - before[p] for p in before} == {"p1": 1, "p2": 1, "p3": 1}
    assert not any(c.zone == "p3:battlefield" and c.name == "Island" for c in s.state.cards.values())
    check(s)


def test_cirdan_a_player_may_vote_for_themself(cards):
    s = start_cirdan(cards)
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {"p1", "p2", "p3"}  # (a player: Círdan's wording has no "another")
    ballot(s, "p1", "p1")
    ballot(s, "p2", "p1")
    ballot(s, "p3", "p1")
    settle(s)
    assert hand(s, "p1") >= 3
    check(s)


# -- Truth or Consequences: a secret vote and "choose an opponent at random" ---------------------------------------------------------------
def truth_table(cards, monkeypatch):
    pin_random(monkeypatch)  # Carol
    s = build3(cards, ["Truth or Consequences"])
    to_hand(s, "Truth or Consequences")
    mana(s, U=1, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Truth or Consequences").id)
    settle_to_vote(s)
    return s


def test_truth_or_consequences_draws_per_truth_vote_and_hits_the_opponent_picked_at_random_per_consequences_vote(cards, monkeypatch):
    s = truth_table(cards, monkeypatch)
    cards_before = hand(s, "p1")
    ballot(s, "p1", "truth")
    ballot(s, "p2", "consequences")
    assert "voted" not in json.dumps(s.view("p3")["log"])  # (secret until the last ballot)
    ballot(s, "p3", "consequences")
    settle(s)
    assert hand(s, "p1") == cards_before + 1  # one truth vote
    assert life(s, "p3") == 40 - 3 * 2 and life(s, "p2") == 40  # two consequences votes: 3 damage for each, to the one picked
    assert "Carol is chosen at random" in json.dumps(s.view("p2")["log"])
    check(s)


def test_truth_or_consequences_with_no_consequences_votes_deals_nothing(cards, monkeypatch):
    s = truth_table(cards, monkeypatch)
    for pid in ("p1", "p2", "p3"):
        ballot(s, pid, "truth")
    settle(s)
    assert (life(s, "p2"), life(s, "p3")) == (40, 40)
    check(s)
