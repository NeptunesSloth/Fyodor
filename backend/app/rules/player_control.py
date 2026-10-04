"""-- controlling another player (wave 18H) -- "You control target player during that player's next turn." (Mindslaver,
Worst Fears, Sorin Markov's -7, The Dominion Bracelet, Construct a Cosmic Cube) and Emrakul, the Promised End's "you gain
control of target opponent during that player's next turn. After that turn, that player takes an extra turn."
Researched against CR 2026-09-25 (723).

* 723.1: the effect applies to the next turn the affected player actually takes (so a skipped turn, 723.1b, waits) and
  lasts the whole turn, ending as the next turn begins. 723.1a: effects on the same player overwrite each other, the last
  created one wins (a pending effect is replaced; Emrakul's extra turn is kept, as it is a separate instruction).
* 723.3: only the player is controlled: objects stay with their controllers; the controlled player is still the active
  player. 723.5: the controller makes every choice (``game/control.py`` routes the intents and ``rules/view.py`` the
  prompts); 723.4: they see what the controlled player sees (``game/visibility.can_see``, never a sideboard); 723.6: only
  a player concedes for themselves; 723.9: controlling yourself changes nothing.
* Refused (manual): Word of Command, Cruel Entertainment, Secret of Bloodbending (a combat phase / waterbend) and
  Opposition Agent are not read here.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import PlayerControl

if TYPE_CHECKING:
    from app.rules.plan import Plan

_HEAD = r"(?:you control|you gain control of) target (?P<who>player|opponent) during (?:that player's|their) next turn"


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "control_player", "who": "target"}], m["who"]


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (re.compile(f"^{_HEAD}$"), _build),
    # Emrakul's second sentence: the same player (the target of the first) takes an extra turn after the controlled one
    (re.compile(r"^after that turn, that player takes an extra turn$"), lambda m: ([{"do": "control_extra"}], None)),
]


def control_player(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.effects import _players

    name = ctx.get("name") or "An effect"
    me = ctx["controller"]
    r = plan.rules
    ctx["controlled_now"] = []
    for pid in _players(plan, ctx, e["who"]):
        ctx["controlled_now"].append(pid)
        old = [c for c in r.player_control if c.controlled == pid and c.status == "pending"]  # 723.1a: the last one works
        r.player_control = [c for c in r.player_control if c not in old]
        r.player_control.append(PlayerControl(controlled=pid, controller=me, label=name,
                                              extra_after=sum(c.extra_after for c in old)))
        plan.note(f"{plan.name(me)} will control {plan.name(pid)} during their next turn ({name}, 723.1)", actor=me)
    return True


def control_extra(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"After that turn, that player takes an extra turn.": noted on the effect this resolution just made (kept if a later
    effect overwrites it, 723.1a: it is a separate instruction)."""
    for pid in ctx.get("controlled_now", []):
        mine = [c for c in plan.rules.player_control if c.controlled == pid and c.controller == ctx["controller"] and c.status == "pending"]
        if mine:
            mine[-1].extra_after += 1
    return True


def turn_began(plan: Plan) -> None:
    """723.1: the effect that applied to the turn that just ended is over; a pending one for the player whose turn this is
    begins (the others wait, 723.1b)."""
    r = plan.rules
    if not r.player_control:
        return
    live = plan.live()
    r.player_control = [c for c in r.player_control if c.status == "pending" and c.controlled in live]
    for c in r.player_control:
        if c.controlled != plan.active:
            continue
        c.status = "active"
        for _ in range(c.extra_after):  # 500.7: "after that turn" (the latest created is taken first)
            r.extra_turns.append({"player": c.controlled, "label": c.label})
        if c.controller in live:
            plan.note(f"{plan.name(c.controller)} controls {plan.name(c.controlled)} this turn ({c.label}, 723.1)", actor=plan.active)


PRIMITIVES = {"control_player": control_player, "control_extra": control_extra}
