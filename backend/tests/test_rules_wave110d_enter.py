"""Wave 110D: "enters with" counter statics and a damage record, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 614.1c, 122.6: "each Human creature you control enters with an additional +1/+1 counter" works from the graveyard while the source is there
  (Dearly Departed, 113.6b); "each other creature you control enters with a number of additional +1/+1 counters equal to this creature's power and as a
  Mutant in addition to its other types" (Master Biomancer); "for each kind of counter on Blue, Loyal Raptor, each other Dinosaur you control enters with a
  counter of that kind" (Blue); "enters with a loyalty counter for each time you've cast a commander from the command zone" (Jeska, 903.8) and her 0
  (614.1a, 609.7a: the chosen creature's combat damage to an opponent is tripled until your next turn).
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import (  # noqa: F401
    EXTRA,
    card_db,
    cast_on,
    ch,
    check,
    full,
    hand_new,
    life,
    mana,
    move,
    next_turn,
    now,
    put,
    put_new,
    settle,
    to_hand,
    to_phase,
)

CARDS = ["Dearly Departed", "Master Biomancer", "Blue, Loyal Raptor", "Jeska, Thrice Reborn"]


@pytest.mark.parametrize("name", CARDS)
def test_the_cards_are_full(name):
    assert full(name)


def test_dearly_departed_helps_humans_only_from_the_graveyard(cards):
    s = build(cards, ["Dearly Departed", "Templar Knight", "Templar Knight", "Dromosaur"])
    first = cast_on(s, "Templar Knight")
    assert now(s, first).counters == {}  # the source is not in the graveyard yet
    dead = to_hand(s, "Dearly Departed")
    move(s, dead, "graveyard")
    saur = cast_on(s, "Dromosaur")
    assert now(s, saur).counters == {}  # not a Human
    knight = hand_new(s, "Templar Knight")
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=knight.id)
    settle(s)
    assert now(s, knight).counters == {"+1/+1": 1} and ch(s, knight).pt == (4, 2)
    move(s, dead, "hand")  # the source leaves the graveyard: no more counters
    move(s, now(s, first), "hand")
    mana(s, W=1, C=1)
    act(s, "p1", type="cast_spell", card_id=first.id)
    settle(s)
    assert now(s, first).counters == {}
    check(s)


def test_master_biomancer_gives_counters_by_power_and_the_type(cards):
    s = build(cards, ["Master Biomancer", "Dromosaur"])
    bio = put(s, "Master Biomancer")
    saur = cast_on(s, "Dromosaur")
    assert now(s, saur).counters == {"+1/+1": ch(s, bio).pt[0]}  # 2 = Master Biomancer's power
    assert "Mutant" in ch(s, saur).subtypes and "Dinosaur" in ch(s, saur).subtypes
    assert "Mutant" not in ch(s, bio).subtypes  # "other"
    check(s)


def test_blue_gives_a_counter_of_each_kind_it_has_to_other_dinosaurs(cards):
    s = build(cards, ["Blue, Loyal Raptor", "Dromosaur"])
    blue = put(s, "Blue, Loyal Raptor")
    for kind, n in (("+1/+1", 2), ("shield", 1)):
        act(s, "p1", type="counter", card_ids=[blue.id], kind=kind, delta=n)
    saur = cast_on(s, "Dromosaur")
    assert now(s, saur).counters == {"+1/+1": 1, "shield": 1}  # one of each kind, however many Blue has
    check(s)


def test_blue_with_no_counters_gives_none(cards):
    s = build(cards, ["Blue, Loyal Raptor", "Dromosaur"])
    put(s, "Blue, Loyal Raptor")
    assert now(s, cast_on(s, "Dromosaur")).counters == {}
    check(s)


def test_jeska_enters_with_a_loyalty_counter_per_commander_cast(cards):
    s = build(cards, ["Jeska, Thrice Reborn"])
    krenko = next(c for c in s.state.cards.values() if c.owner == "p1" and c.commander_key)
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=krenko.id)
    settle(s)
    assert s.state.players["p1"].commander_casts[krenko.commander_key] == 1
    jeska = cast_on(s, "Jeska, Thrice Reborn")
    assert now(s, jeska).zone == "p1:battlefield" and now(s, jeska).counters == {"loyalty": 1}
    check(s)


def test_jeska_without_a_commander_cast_dies_with_no_loyalty(cards):
    s = build(cards, ["Jeska, Thrice Reborn"])
    jeska = cast_on(s, "Jeska, Thrice Reborn")
    assert now(s, jeska).zone == "p1:graveyard"  # 0 loyalty counters: 704.5i
    check(s)




def jeska_turn_three(cards, activate):
    s = build(cards, ["Jeska, Thrice Reborn", "Templar Knight"])
    krenko = next(c for c in s.state.cards.values() if c.owner == "p1" and c.commander_key)
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=krenko.id)
    settle(s)
    jeska = cast_on(s, "Jeska, Thrice Reborn")
    knight = put_new(s, "Templar Knight")
    next_turn(s)
    next_turn(s)
    to_phase(s, "main1", turn=3)
    if activate:
        index = next(a.index for a in ch(s, jeska).abilities if a.text.startswith("0:"))
        act(s, "p1", type="activate_ability", card_id=jeska.id, ability=index, targets=[knight.id])
        settle(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="set_stops", own=["declare_attackers"], smart_pass=False)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": knight.id, "target": "p2"}])
    to_phase(s, "end", turn=3)
    return s


@pytest.mark.parametrize(("used", "lost"), [(False, 3), (True, 9)])
def test_jeska_zero_triples_combat_damage_to_an_opponent(cards, used, lost):
    s = jeska_turn_three(cards, used)
    assert life(s, "p2") == 40 - lost  # 3 power, tripled if she used her 0
    check(s)


def kill(s, victim):
    """Lightning Bolt the creature."""
    cast_on(s, "Lightning Bolt", victim)


@pytest.mark.parametrize("name", ["Reins of the Vinesteed", "Traveling Plague"])
def test_the_auras_are_full(name):
    assert full(name)


def test_reins_returns_to_a_creature_sharing_a_type_with_the_dead_one(cards):
    s = build(cards, ["Reins of the Vinesteed", "Templar Knight", "Templar Knight", "Dromosaur", "Lightning Bolt"])
    a = put_new(s, "Templar Knight")
    saur = put(s, "Dromosaur")
    reins = cast_on(s, "Reins of the Vinesteed", a)
    assert now(s, reins).attached_to == a.id
    b = put_new(s, "Templar Knight")
    kill(s, a)
    assert now(s, a).zone == "p1:graveyard"
    settle(s)
    assert now(s, reins).zone == "p1:battlefield" and now(s, reins).attached_to == b.id  # the Dinosaur shares no type with the Knight
    assert saur.id != now(s, reins).attached_to
    check(s)


def test_reins_stays_if_no_creature_shares_a_type(cards):
    s = build(cards, ["Reins of the Vinesteed", "Templar Knight", "Dromosaur", "Lightning Bolt"])
    a = put(s, "Templar Knight")
    put(s, "Dromosaur")
    reins = cast_on(s, "Reins of the Vinesteed", a)
    kill(s, a)
    settle(s)
    assert now(s, reins).zone == "p1:graveyard"
    check(s)


def test_traveling_plague_comes_back_under_the_creatures_controller(cards):
    s = build(cards, ["Traveling Plague", "Lightning Bolt"], ["Dromosaur", "Templar Knight"])
    saur = put(s, "Dromosaur", "p2")
    knight = put(s, "Templar Knight", "p2")
    plague = cast_on(s, "Traveling Plague", saur)
    kill(s, saur)
    settle(s)
    got = now(s, plague)
    assert got.zone == "p2:battlefield" and got.controller == "p2" and got.owner == "p1"  # 110.2a: p2 returned it
    assert got.attached_to == knight.id  # the only creature it can enchant
    check(s)
