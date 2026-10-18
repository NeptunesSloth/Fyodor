"""Wave 45A: "attacking one of your opponents" (CR 2026-09-25), real Oracle text (tests/fixtures/wave45a_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 506.2, 508.1: Oviya, Automech Artisan [3172] - "Each creature that's attacking one of your opponents has trample." A creature attacking a player who is an opponent of
  Oviya's controller, whoever controls it (Blast-Furnace Hellkite's ruling 2022-10-14, same wording); a creature attacking its own controller's opponent's planeswalker
  or attacking Oviya's controller has none. Martial Impetus [3817] reads the same group.
* 608.2c: Oviya's "{G}, {T}: You may put a creature or Vehicle card from your hand onto the battlefield. If you put an artifact onto the battlefield this way, put two
  +1/+1 counters on it." - two counters only on an artifact (the Oviya ruling 2025-02-07: judged on the battlefield).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, next_turn, settle, stops
from tests.test_rules_wave45a_attacked import until_decision
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand
from tests.wave45a_kit import FULL, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def has(s, name, keyword, pid="p1"):
    return keyword in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card_named(s, name, pid).id]).keywords


def test_oviya_gives_trample_to_a_creature_attacking_an_opponent(cards):
    s = build(cards, ["Oviya, Automech Artisan", "Hill Giant"], [])
    stops(s)
    put(s, "Oviya, Automech Artisan")
    giant = put(s, "Hill Giant")
    next_turn(s)
    assert not has(s, "Hill Giant", "trample")  # (not attacking)
    until_decision(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": giant.id, "target": "p2"}])
    assert has(s, "Hill Giant", "trample")
    check(s)


def test_oviya_gives_no_trample_to_a_creature_attacking_her_controller(cards):
    s = build(cards, ["Oviya, Automech Artisan"], ["Grizzly Bears"])
    stops(s)
    put(s, "Oviya, Automech Artisan")
    bears = put(s, "Grizzly Bears", "p2")
    d = until_decision(s, "declare_attackers")  # (Alice has nothing that can attack on turn 1: Bob's turn is next)
    assert d.player == "p2"
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    assert not has(s, "Grizzly Bears", "trample", "p2")  # attacking Alice, not one of her opponents
    check(s)


@pytest.mark.parametrize("card, counters", [("Chrome Courier", 2), ("Hill Giant", 0)])
def test_oviya_puts_two_counters_on_an_artifact_put_onto_the_battlefield(cards, card, counters):
    s = build(cards, ["Oviya, Automech Artisan", card], [])
    oviya = put(s, "Oviya, Automech Artisan")
    next_turn(s)
    c = to_hand(s, card)
    mana(s, G=1)
    activate(s, "p1", oviya, "put a creature")
    settle(s, answer="yes")
    now = s.state.cards[c.id]
    assert now.zone == "p1:battlefield" and now.counters.get("+1/+1", 0) == counters
    check(s)
