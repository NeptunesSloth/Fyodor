"""Wave 110D: Wall of Stolen Identity, real Oracle text.

* 707.5, 614.1c: enters as a copy of a creature on the battlefield, except it is a Wall as well and has defender (707.9).
* 603.12: "When you do" (it entered as a copy), tap the copied creature; 611.2b it doesn't untap for as long as you control the Wall.
"""

from __future__ import annotations

from app.rules.copying import NONE
from tests.game_helpers import act
from tests.wave110d_kit import (  # noqa: F401
    build,
    card_db,
    ch,
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
)

NAME = "Wall of Stolen Identity"


def test_full():
    assert full(NAME)


def cast(cards, answer):
    s = build(cards, [NAME], ["Grizzly Bears"])
    bears = put_new(s, "Grizzly Bears", "p2")
    c = hand_new(s, NAME)
    mana(s, "p1", **cost(NAME))
    act(s, "p1", type="cast_spell", card_id=c.id)
    settle(s, answers=[bears.id if answer else NONE])
    return s, now(s, c), bears


def test_copies_taps_and_holds_the_copied_creature(cards):
    s, wall, bears = cast(cards, True)
    got = ch(s, wall)
    assert got.name == "Grizzly Bears" and "Wall" in got.subtypes and "defender" in got.keywords
    assert now(s, bears).tapped
    next_turn(s)  # p2's untap step: the Bears stay tapped while p1 controls the Wall
    assert now(s, bears).tapped
    check(s)
    move(s, wall, "graveyard")
    next_turn(s)
    next_turn(s)
    assert not now(s, bears).tapped


def test_declined_copy_taps_nothing(cards):
    s, wall, bears = cast(cards, False)
    assert ch(s, wall).name == NAME and not now(s, bears).tapped
    check(s)
