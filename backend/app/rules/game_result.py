"""-- game result statics (wave 10B) -- "You can't lose the game and your opponents can't win the game." (Platinum Angel,
Herald of Eternal Dawn) and "You can't win the game and your opponents can't lose the game." (Abyssal Persecutor).
Researched against CR 2026-09-25.

* 104.3: a player loses when a state-based action says so (704.5a: 0 or less life, 704.5b: a draw from an empty library,
  704.5c: ten poison counters, 903.10a: commander damage) or an effect says so; a player who "can't lose the game" stays in
  it: the state-based action does nothing to them, and as nothing is checked again until something changes (704.3), a
  draw from an empty library is no longer pending once the check has passed (704.5b: "since the last time state-based
  actions were checked"), while a life total of 0 or less, or the poison counters, are still there when the permanent
  leaves and the player then loses at the next check. A player who concedes still leaves the game (104.3a).
* 104.2: a player who "can't win the game" doesn't win by an effect (104.2b); being the last player left (104.2a)
  overrides it: they win at once.
* Both statics apply while their source is on the battlefield (611.3a): "you" is its controller, "your opponents" the
  other players. Not read: the same effect from a spell ("players can't lose the game this turn": Everybody Lives!).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

KIND = "game_result"
_TEXT = re.compile(r"^You can't (?P<a>lose|win) the game and your opponents can't (?P<b>win|lose) the game\.$")


def static_definition(text: str) -> dict[str, Any] | None:
    m = _TEXT.match(text.strip())
    if m is None or m["a"] == m["b"]:
        return None
    return {"kind": "static", "static": KIND, "you": m["a"], "opponents": m["b"], "effects": []}


def _stops(plan: Plan, player: str, what: str) -> bool:
    from app.rules import scripts
    from app.rules.replace import conditional_lines

    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or c.face_down or not plan.in_game(c) or plan.manual(c):
            continue
        ch = plan.ch(c)
        skip = conditional_lines(ch)  # (a leveler's / Class's level lines: the level isn't tracked)
        for i, d in scripts.definitions(ch).items():
            if i in skip or d.get("kind") != "static" or d.get("static") != KIND:
                continue
            if d["you" if c.controller == player else "opponents"] == what:
                return True
    return False


def cannot_lose(plan: Plan, player: str) -> bool:
    return _stops(plan, player, "lose")


def cannot_win(plan: Plan, player: str) -> bool:
    return _stops(plan, player, "win")
