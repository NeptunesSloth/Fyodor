"""-- coin flips (wave 7E) -- "Flip a coin. If you win the flip, create a Treasure token." (The Gold Saucer), "Flip a coin. If you
win the flip, …. If you lose the flip, …." (Goblin Bangchuckers, Winter Sky, Orcish Captain), "Flip a coin. If it comes up
heads, …" (Odds // Ends). Researched against CR 2026-09-25, 705.

* 705.1: the flip is made with any two-outcome randomizer of equal likelihood; the table's recorded "coin" action is one
  (app/game/actions.py ``Coin``: the result is recorded in the history, so a replay or a reload reproduces it).
* 705.2: the player who flips calls heads or tails; a match wins the flip. Both outcomes are equally likely whatever is
  called, so the call is not asked: heads is a win, tails a loss. Only the flipper wins or loses (the ability's controller
  here: "you").
* 608.2c: the instruction after the flip is followed in order, so "If you win the flip" is judged from this resolution's
  own flip (``ctx["coin"]``). A condition about a flip needs a flip earlier in the same ability (``refs_ok``).

Refused (manual): flipping several coins or "until you lose a flip", "each player flips", ignoring flips (Krark's Thumb,
Edgar), flipping at a later time ("at the beginning of the next end step") and "whenever you win a coin flip" triggers.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

_FLIP = re.compile(r"^flip a coin$")
_COND = re.compile(r"^(?:you (?P<w>win|lose) the flip|(?:it|the coin) comes up (?P<f>heads|tails))$")


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "coin_flip"}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_FLIP, _build)]


def condition(text: str) -> dict[str, Any] | None:
    """"you win the flip" / "it comes up tails" → ``{"coin": "win" | "lose"}`` (heads is a win, 705.2), else None."""
    m = _COND.fullmatch(text)
    if m is None:
        return None
    return {"coin": "win" if (m["w"] == "win" or m["f"] == "heads") else "lose"}


def holds(ctx: Context, cond: dict[str, Any]) -> bool:
    flipped = ctx.get("coin")
    return flipped is not None and bool(flipped) == (cond["coin"] == "win")


def coin_flip(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    import secrets

    if plan.rng is None:
        plan.rng = secrets.SystemRandom()  # (the result is recorded on the step: the history replays it, not the generator)
    done = plan.do({"type": "coin", "count": 1}, actor=ctx["controller"])
    ctx["coin"] = bool(done.r.results[0])  # type: ignore[union-attr]
    return True


def refs_ok(effects: list[dict[str, Any]]) -> bool:
    """A condition about a flip only after a flip of the same ability."""
    flipped = False
    for e in effects:
        if e["do"] == "coin_flip":
            flipped = True
        elif e["do"] == "only_if" and "coin" in str(e.get("cond")) and not flipped:
            return False
    return True


PRIMITIVES = {"coin_flip": coin_flip}
