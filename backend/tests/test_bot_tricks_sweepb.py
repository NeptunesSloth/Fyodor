"""Sweep B (nov 18): the bot's combat tricks (bot._tricks) read a fight with the combat maths (bot._clash), first strike and trample counted,
as its attacks and blocks do."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.game import bot


@dataclass
class C:
    id: str
    power: int
    toughness: int
    kw: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)
    text: str = ""

    def has(self, k: str) -> bool:
        return k in self.kw


def test_a_pump_that_lets_a_first_striker_kill_first_is_worth_it():
    """A 2/2 first striker blocked by a 3/3: it dies. +1/+1: it deals 3 first and the 3/3 deals nothing (510.4). The old reading (all the
    blocker's damage on it) called it dead either way."""
    fs = C("fs", 2, 2, ("first strike",), {"attacking": {"id": "p1"}})
    ogre = C("ogre", 3, 3, extra={"blocking": "fs"})
    assert bot._trick_fight(fs, [ogre]) == (True, False, 0)
    assert bot._trick_fight(fs, [ogre], 1, 1) == (False, True, 0)
    assert bot._outcome(fs, [ogre], 1, 1) == (True, True)  # (the old reading)


def test_a_blocker_against_a_first_striker():
    """A 4/1 blocking a 2/2 first striker dies before it strikes; +2/+2 and it survives the first strike and kills it."""
    fs = C("fs", 2, 2, ("first strike",), {"attacking": {"id": "p2"}})
    wall = C("wall", 4, 1, extra={"blocking": "fs"})
    assert bot._trick_fight(wall, [fs]) == (True, False, 0)  # dead before it strikes
    assert bot._trick_fight(wall, [fs], 2, 2) == (False, True, 0)


def test_a_blocked_trampler_counts_what_it_gets_through():
    trampler = C("t", 5, 5, ("trample",), {"attacking": {"id": "p1"}})
    chump = C("c", 1, 1, extra={"blocking": "t"})
    assert bot._trick_fight(trampler, [chump]) == (False, True, 4)
    assert bot._trick_fight(trampler, [chump], 3, 3)[2] == 7
