"""-- hand size (wave 4J) -- "You have no maximum hand size." (Reliquary Tower, Thought Vessel, Decanter of Endless
Water). Researched against CR 2026-09-25.

* 402.2: each player has a maximum hand size, normally seven; as part of their cleanup step (514.1) the active player
  discards down to it. A static ability of a permanent saying its controller has no maximum hand size removes that
  discard while the permanent is on the battlefield under their control (611.3a: a static ability's effect applies
  while the object is on the battlefield).
* -- static statics (wave 10B) -- "Your maximum hand size is reduced by four." (Thought Devourer), "… is increased by two."
  (Trusted Advisor), "Each opponent's maximum hand size is reduced by seven." (Jin-Gitaxias, Core Augur) and "Players have
  no maximum hand size." (Price of Knowledge): reductions and increases add up (they commute), never below zero; no
  maximum beats them all (402.2: the cleanup discard is down to the maximum). A SET maximum ("Your maximum hand size is
  eleven", "The chosen player's maximum hand size is four": its order against the others is by timestamp) and "for the
  rest of the game" from a resolving spell stay manual.

Read by the cleanup step (app/rules/engine.cleanup_step).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

NO_MAXIMUM = "no_max_hand"
MAX_HAND_SIZE = 7  # 402.2


MODIFIES = "max_hand_size"
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_CHANGE = re.compile(r"^(?P<who>Your|Each opponent's) maximum hand size is (?P<dir>reduced|increased) by "
                     r"(?P<n>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\.$")


def static_definition(text: str) -> dict[str, Any] | None:
    t = text.strip()
    if t == "You have no maximum hand size.":
        return {"kind": "static", "static": NO_MAXIMUM, "effects": []}
    if t == "Players have no maximum hand size.":  # -- static statics (wave 10B) --
        return {"kind": "static", "static": NO_MAXIMUM, "who": "each", "effects": []}
    m = _CHANGE.match(t)
    if m is None:
        return None
    n = _NUMBERS[m["n"]] if m["n"] in _NUMBERS else int(m["n"])
    return {"kind": "static", "static": MODIFIES, "who": "you" if m["who"] == "Your" else "opponents",
            "delta": -n if m["dir"] == "reduced" else n, "effects": []}


def _applies(d: dict[str, Any], controller: str, player: str) -> bool:
    who = d.get("who", "you")
    return who == "each" or (who == "you" and controller == player) or (who == "opponents" and controller != player)


def maximum(plan: Plan, player: str) -> int | None:
    """-- static statics (wave 10B) -- ``player``'s maximum hand size (402.2): None when they have none, else seven
    changed by the reductions and increases of the permanents on the battlefield (611.3a), never below zero."""
    from app.rules import scripts
    from app.rules.replace import conditional_lines

    size = MAX_HAND_SIZE
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        skip = conditional_lines(ch)  # (a leveler's / Class's level lines: the level isn't tracked)
        for i, d in scripts.definitions(ch).items():
            if i in skip or d.get("kind") != "static" or not _applies(d, c.controller, player):
                continue
            if d.get("static") == NO_MAXIMUM:
                return None
            if d.get("static") == MODIFIES:
                size += int(d["delta"])
    return max(0, size)


def no_maximum(plan: Plan, player: str) -> bool:
    """Whether a permanent gives ``player`` no maximum hand size (402.2)."""
    return maximum(plan, player) is None
