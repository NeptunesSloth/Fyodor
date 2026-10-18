"""Wave 51D: a token whose power and toughness come from the creature or card an earlier instruction took (CR 2026-09-25), real Oracle text
(tests/fixtures/wave51d_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 608.2c / 608.2h / 111.3: Kalitas, Ritual of the Returned, Broken Visage - "Create a black Vampire creature token. Its power is equal to that creature's power and its
  toughness is equal to that creature's toughness." The numbers are worked out as the token is created, from the creature as it last existed (ruling 2009-10-01);
  a printed P/T from then on. No token when the destroyed creature did not die (ruling 2013-07-01).
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, next_turn, settle, stops, to_phase
from tests.test_rules_wave51d_if_you_do import KALITAS, RITUAL, VISAGE, cards  # noqa: F401
from tests.wave9c_kit import build, cast, check, mana, pt, put, reloaded, to_hand, zone_of


def tokens(s, name, pid="p1"):
    return [c for c in s.state.cards.values() if c.is_token and c.name == name and c.zone == f"{pid}:battlefield"]


def kalitas(cards, counters=0, shield=False):
    s = build(cards, [KALITAS], ["Hill Giant"], forests=30)
    k = put(s, KALITAS)
    giant = put(s, "Hill Giant", "p2")
    if counters:
        act(s, "p1", type="counter", card_ids=[giant.id], kind="+1/+1", delta=counters)
    if shield:
        act(s, "p1", type="counter", card_ids=[giant.id], kind="shield", delta=1)  # the destruction is replaced (122.1c): it does not die
    next_turn(s)
    mana(s, "p1", B=3)
    activate(s, "p1", k, targets=[giant.id])
    settle(s)
    return s, k, giant


def test_kalitas_makes_a_vampire_with_the_power_and_toughness_the_destroyed_creature_had(cards):
    s, k, giant = kalitas(cards, counters=2)
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard"
    assert len(tokens(s, "Vampire")) == 1 and not tokens(s, "Vampire", "p2")  # yours, not its controller's (ruling 2009-10-01)
    assert pt(s, "Vampire") == (5, 5)  # 3/3 with two +1/+1 counters as it last existed (608.2h)
    check(s)
    assert len(tokens(reloaded(s), "Vampire")) == 1


def test_kalitas_makes_no_vampire_when_the_creature_does_not_die(cards):
    s, k, giant = kalitas(cards, shield=True)
    assert zone_of(s, "Hill Giant", "p2") == "p2:battlefield" and not tokens(s, "Vampire")
    check(s)


def test_ritual_of_the_returned_makes_a_zombie_the_size_of_the_exiled_card(cards):
    s = build(cards, [RITUAL, "Hill Giant"], forests=30)
    giant = put(s, "Hill Giant")
    act(s, "p1", type="move", card_ids=[giant.id], to={"player": "p1", "zone": "graveyard"})
    to_hand(s, RITUAL)
    mana(s, "p1", B=4)
    cast(s, RITUAL, targets=[giant.id])
    settle(s)
    assert zone_of(s, "Hill Giant") == "p1:exile"
    assert len(tokens(s, "Zombie")) == 1 and pt(s, "Zombie") == (3, 3)
    check(s)


def test_broken_visage_destroys_an_attacker_and_makes_a_spirit_of_its_size(cards):
    s = build(cards, [VISAGE], ["Hill Giant"], forests=30)
    giant = put(s, "Hill Giant", "p2")
    to_hand(s, VISAGE)
    stops(s)
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": giant.id, "target": "p1"}])
    act(s, "p2", type="pass_priority")  # (Bob, the active player, passes first)
    mana(s, "p1", B=6)
    cast(s, VISAGE, targets=[giant.id])
    settle(s)
    assert zone_of(s, "Hill Giant", "p2") == "p2:graveyard"
    assert len(tokens(s, "Spirit")) == 1 and pt(s, "Spirit") == (3, 3)
    check(s)
