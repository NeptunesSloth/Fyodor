"""-- hand size (wave 4J) -- "You have no maximum hand size." (Reliquary Tower, Thought Vessel, Decanter of Endless
Water). Researched against CR 2026-09-25.

* 402.2: each player has a maximum hand size, normally seven; as part of their cleanup step (514.1) the active player
  discards down to it. A static ability of a permanent saying its controller has no maximum hand size removes that
  discard while the permanent is on the battlefield under their control (611.3a: a static ability's effect applies
  while the object is on the battlefield).
* -- static statics (wave 10B) -- "Your maximum hand size is reduced by four." (Thought Devourer), "… is increased by two."
  (Trusted Advisor), "Each opponent's maximum hand size is reduced by seven." (Jin-Gitaxias, Core Augur) and "Players have
  no maximum hand size." (Price of Knowledge): reductions and increases add up (they commute), never below zero; no
  maximum beats them all (402.2: the cleanup discard is down to the maximum). -- static_other sweep (wave 16B) -- A SET
  maximum of a permanent ("Your maximum hand size is eleven.": Cecily, The Ten Rings) is applied with the others in the
  order of the permanents' timestamps (613.7d: the later effect wins). "The chosen player's maximum hand size is four" and
  "for the rest of the game" from a resolving spell stay manual.

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
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12}
_SET = re.compile(r"^Your maximum hand size is (?P<n>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)\.$")
_CHANGE = re.compile(r"^(?P<who>Your|Each opponent's) maximum hand size is (?P<dir>reduced|increased) by "
                     r"(?P<n>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\.$")


def static_definition(text: str) -> dict[str, Any] | None:
    t = text.strip()
    if t == "You have no maximum hand size.":
        return {"kind": "static", "static": NO_MAXIMUM, "effects": []}
    if t == "You have no maximum hand size and don't lose the game for having 0 or less life.":  # -- most-played cards III (wave 46C) -- Marina Vendrell's Grimoire (game_result.zero_life_ok)
        return {"kind": "static", "static": NO_MAXIMUM, "zero_life": True, "effects": []}
    if t == "Players have no maximum hand size.":  # -- static statics (wave 10B) --
        return {"kind": "static", "static": NO_MAXIMUM, "who": "each", "effects": []}
    if (s := _SET.match(t)) is not None:
        return {"kind": "static", "static": MODIFIES, "who": "you", "set": _NUMBERS[s["n"]] if s["n"] in _NUMBERS else int(s["n"]),
                "effects": []}
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
    from app.rules.layers import timestamp
    from app.rules.replace import conditional_lines

    if player in plan.rules.no_max_hand:  # (wave 20C)
        return None
    size = MAX_HAND_SIZE
    for c in sorted(plan.state.cards.values(), key=lambda c: timestamp(plan.state, c.id)):  # (613.7: oldest first, the latest set wins)
        emblem = c.zone.endswith(":command") and c.token is not None and c.token.type_line == "Emblem"  # (wave 20C: 114.4)
        if not (c.zone.endswith(":battlefield") or emblem) or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        skip = conditional_lines(ch)  # (a leveler's / Class's level lines: the level isn't tracked)
        for i, d in scripts.definitions(ch).items():
            if i in skip or d.get("kind") != "static" or not _applies(d, c.controller, player):
                continue
            if d.get("static") == NO_MAXIMUM:
                return None
            if d.get("static") == MODIFIES:
                size = int(d["set"]) if "set" in d else size + int(d["delta"])
    return max(0, size)


def no_maximum(plan: Plan, player: str) -> bool:
    """Whether a permanent gives ``player`` no maximum hand size (402.2)."""
    return maximum(plan, player) is None


# -- ability words (wave 20C) -- "You have no maximum hand size for the rest of the game." (Praetor's Counsel, Ancient Silver Dragon):
# 611.2a: a continuous effect from a resolving ability that changes the rules lasts "for the rest of the game"; it doesn't depend on
# the object (610.3) and works for the player who got it, whatever leaves (``RulesState.no_max_hand``, read by ``maximum``).
TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (re.compile(r"^you have no maximum hand size for the rest of the game$"), lambda m: ([{"do": "no_max_hand"}], None))]


def no_max_hand(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    who = str(ctx["controller"])
    if who not in plan.rules.no_max_hand:
        plan.rules.no_max_hand.append(who)
    plan.note(f"{plan.name(who)} has no maximum hand size for the rest of the game", actor=who)
    return True


PRIMITIVES = {"no_max_hand": no_max_hand}
