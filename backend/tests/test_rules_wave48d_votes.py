"""Wave 48D: "Whenever players finish voting" (CR 2026-09-25), real Oracle text (tests/fixtures/wave48d_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 701.38a: each player votes, starting with the controller of the spell, in turn order; the trigger is put on the stack when the spell has finished
  resolving (Grudge Keeper's rulings) and considers only that voting.
* Grudge Keeper: "each opponent who voted for a choice you didn't vote for loses 2 life."
* Erestor of the Council: "each opponent who voted for a choice you voted for creates a Treasure token. You scry X, where X is the number of opponents who
  voted for a choice you didn't vote for. Draw a card." (the draw happens whatever the votes were: ruling 2023-06-16)
* Model of Unity: "you and each opponent who voted for a choice you voted for may scry 2."
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import card_named, check, mana, put, to_hand
from tests.wave47b_kit import build3
from tests.wave48d_kit import life, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


def ballot(s, pid, label):
    d = s.state.rules.decision
    assert d is not None and d.player == pid and d.kind == "choose_one", (d.player if d else None, pid)
    act(s, pid, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == label)])


def vote(s, alice, bob, carol, watcher, extra=()):
    """Alice casts Tyrant's Choice with the watcher on the table; the three ballots are cast in turn order (``extra``: the ballots after Bob's first)."""
    s_ = s
    put(s_, watcher)
    to_hand(s_, "Tyrant's Choice")
    mana(s_, B=1, C=1)
    act(s_, "p1", type="cast_spell", card_id=card_named(s_, "Tyrant's Choice").id)
    for _ in range(10):
        if s_.state.rules.decision is not None:
            break
        act(s_, s_.state.rules.priority, type="pass_priority")
    hand = len(s_.state.zones["p1:hand"])  # (the spell is on the stack; the last ballot resolves it and what it triggers)
    for pid, pick in (("p1", alice), ("p2", bob), *(("p2", x) for x in extra), ("p3", carol)):
        ballot(s_, pid, pick)
    return hand


def answer(s, d):
    """A may-question is answered yes, a scry keeps the cards where they are (in order)."""
    ids = [o.id for o in d.options]
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"] if "yes" in ids else ids if d.kind == "order" else [])


def finish(s):
    """Everything on the stack resolves; the questions of the may-scry are answered; the players asked are returned."""
    asked = []
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            asked.append(d.player)
            answer(s, d)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return asked
    raise AssertionError("never finished")


def treasures(s, pid):
    return len([c for c in s.state.cards.values() if c.name == "Treasure" and c.owner == pid and c.zone.endswith("battlefield")])


def test_grudge_keeper_drains_an_opponent_who_voted_for_a_choice_its_controller_did_not(cards):
    s = build3(cards, ["Grudge Keeper", "Tyrant's Choice"])
    vote(s, "death", "torture", "death", "Grudge Keeper")
    finish(s)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (40, 38, 40)  # Bob's torture vote; Carol voted death like Alice
    check(s)


def test_grudge_keeper_ignores_opponents_who_voted_as_its_controller_did(cards):
    s = build3(cards, ["Grudge Keeper", "Tyrant's Choice"])
    vote(s, "death", "death", "death", "Grudge Keeper")
    finish(s)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (40, 40, 40)
    check(s)


def test_erestor_gives_treasure_to_opponents_who_agreed_scries_for_those_who_did_not_and_draws(cards):
    s = build3(cards, ["Erestor of the Council", "Tyrant's Choice"])
    hand = vote(s, "death", "death", "torture", "Erestor of the Council")
    finish(s)
    assert (treasures(s, "p2"), treasures(s, "p3")) == (1, 0)  # Bob voted death like Alice
    assert len(s.state.zones["p1:hand"]) == hand + 1  # "Draw a card": whatever the votes were
    check(s)


def test_erestor_scries_nothing_and_still_draws_when_everyone_agreed(cards):
    s = build3(cards, ["Erestor of the Council", "Tyrant's Choice"])
    hand = vote(s, "torture", "torture", "torture", "Erestor of the Council")
    finish(s)
    assert (treasures(s, "p2"), treasures(s, "p3")) == (1, 1)
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_model_of_unity_lets_its_controller_and_the_opponents_who_agreed_scry(cards):
    s = build3(cards, ["Model of Unity", "Tyrant's Choice"])
    vote(s, "death", "death", "torture", "Model of Unity")
    scried = finish(s)
    assert "p3" not in scried and "p1" in scried and "p2" in scried  # Carol voted torture
    check(s)


def test_grudge_keeper_drains_an_opponent_with_two_votes_once(cards):
    # Grudge Keeper's ruling: Bob votes death (as Alice did) and torture (a choice Alice didn't vote for): he loses 2 life only once
    s = build3(cards, ["Grudge Keeper", "Tyrant's Choice"], bobs=["Ballot Broker"])
    put(s, "Ballot Broker", "p2")
    vote(s, "death", "death", "death", "Grudge Keeper", extra=["torture"])
    finish(s)
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (40, 38, 40)
    check(s)


def test_erestor_counts_an_opponent_with_two_votes_both_ways(cards):
    # Erestor's ruling (2023-06-16): Bob is an opponent who voted for a choice Alice voted for (a Treasure) and one who voted for a choice she didn't (X is 1)
    s = build3(cards, ["Erestor of the Council", "Tyrant's Choice"], bobs=["Ballot Broker"])
    put(s, "Ballot Broker", "p2")
    hand = vote(s, "death", "death", "death", "Erestor of the Council", extra=["torture"])
    finish(s)
    assert (treasures(s, "p2"), treasures(s, "p3")) == (1, 1)
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_model_of_unity_lets_only_its_controller_scry_when_every_opponent_disagreed(cards):
    s = build3(cards, ["Model of Unity", "Tyrant's Choice"])
    vote(s, "death", "torture", "torture", "Model of Unity")
    assert set(finish(s)) == {"p1"}
    check(s)
