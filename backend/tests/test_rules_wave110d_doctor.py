"""Wave 110D: The War Doctor, real Oracle text.

* 603.2c, 702.26: one or more OTHER permanents phasing out, and one or more OTHER cards put into exile from anywhere, each batch puts one time counter on it.
* 120.3, 614.1a: it deals damage equal to its time counters when it attacks; a creature dealt damage this way that would die is exiled instead.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave110d_kit import (  # noqa: F401
    build,
    card_db,
    check,
    cost,
    full,
    hand_new,
    mana,
    move,
    next_turn,
    now,
    put_new,
    settle,
    to_phase,
)

NAME = "The War Doctor"


def test_full():
    assert full(NAME)


def time(s, c):
    return now(s, c).counters.get("time", 0)


def swords(s, name, target):
    c = hand_new(s, name)
    mana(s, "p1", **cost(name))
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[target.id])
    settle(s)


def test_counters_from_exile_and_phasing(cards):
    s = build(cards, [NAME, "The Phasing of Zhalfir", "Swords to Plowshares"], ["Grizzly Bears", "Llanowar Elves"])
    doc, bears, elves = put_new(s, NAME), put_new(s, "Grizzly Bears", "p2"), put_new(s, "Llanowar Elves", "p2")
    swords(s, "Swords to Plowshares", elves)  # a card put into exile (from the battlefield): the Swords themselves go to the graveyard
    assert now(s, elves).zone == "p2:exile" and time(s, doc) == 1
    z = hand_new(s, "The Phasing of Zhalfir")
    mana(s, "p1", **cost("The Phasing of Zhalfir"))
    act(s, "p1", type="cast_spell", card_id=z.id)
    settle(s, answers=["1", bears.id])  # chapter I phases the Bears out
    assert now(s, bears).zone == "p2:phased" and time(s, doc) == 2
    check(s)


def test_attack_damage_equals_counters_and_exiles_what_would_die(cards):
    s = build(cards, [NAME, "Swords to Plowshares"], ["Grizzly Bears", "Llanowar Elves"])
    doc, elves = put_new(s, NAME), put_new(s, "Llanowar Elves", "p2")
    swords(s, "Swords to Plowshares", put_new(s, "Grizzly Bears", "p2"))
    assert time(s, doc) == 1
    next_turn(s)
    next_turn(s)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="set_stops", own=["declare_attackers"], smart_pass=False)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": doc.id, "target": "p2"}])
    settle(s, answers=[elves.id])
    assert now(s, elves).zone == "p2:exile"  # 1 damage kills the 1/1 Elves: exiled instead of dying
    check(s)
