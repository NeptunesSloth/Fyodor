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

* (wave 45D) "Flip a coin until you lose a flip." (Okaun, Zndrsplt): the flips follow one another, each recorded; "Whenever a player wins a coin
  flip" (``win_flip`` event) triggers for each flip its flipper wins. 705.2: an effect that cares about heads or tails (``ht``) has no winner or
  loser; any other flip is called by the flipper, who wins or loses it (rulings of 2018-06-08, 2018-07-13: only the flipper wins).

Refused (manual): flipping several coins, "each player flips", ignoring flips (Krark's Thumb, Edgar) and flipping at a later time
("at the beginning of the next end step").
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import emit

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

_FLIP = re.compile(r"^flip a coin$")
_COND = re.compile(r"^(?:you (?P<w>win|lose) the flip|(?:it|the coin) comes up (?P<f>heads|tails)|(?P<c>you win))$")


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "coin_flip"}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (_FLIP, _build),
    (re.compile(r"^flip a coin until you lose a flip$"), lambda m: ([{"do": "coin_flip", "until": "lose"}], None)),  # (wave 45D)
]


def condition(text: str) -> dict[str, Any] | None:
    """"you win the flip" / "it comes up tails" → ``{"coin": "win" | "lose"}`` (heads is a win, 705.2), else None."""
    m = _COND.fullmatch(text)
    if m is None:
        return None
    if m["c"]:  # -- clash (wave 12A) -- "If you win" (701.30d), judged from this resolution's own clash (app/rules/clash.py)
        return {"coin": "win", "of": "clash"}
    return {"coin": "win" if (m["w"] == "win" or m["f"] == "heads") else "lose", **({"ht": True} if m["f"] else {})}


def holds(ctx: Context, cond: dict[str, Any]) -> bool:
    flipped = ctx.get("clash" if cond.get("of") else "coin")
    return flipped is not None and bool(flipped) == (cond["coin"] == "win")


def coin_flip(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    import secrets

    if plan.rng is None:
        plan.rng = secrets.SystemRandom()  # (the result is recorded on the step: the history replays it, not the generator)
    while True:  # (wave 45D: "until you lose a flip" goes on after each win)
        done = plan.do({"type": "coin", "count": 1}, actor=ctx["controller"])
        ctx["coin"] = bool(done.r.results[0])  # type: ignore[union-attr]
        if not e.get("ht") and ctx["coin"]:  # 705.2: the flipper won (a lost flip has no winner)
            emit(plan.state, "designation", counter="win_flip", player=ctx["controller"])
        if e.get("until") != "lose" or not ctx["coin"]:
            return True


def _mark_heads_tails(x: Any) -> None:
    if isinstance(x, dict):
        if x.get("do") == "coin_flip":
            x["ht"] = True
        for v in x.values():
            _mark_heads_tails(v)
    elif isinstance(x, list):
        for v in x:
            _mark_heads_tails(v)


def refs_ok(effects: list[dict[str, Any]]) -> bool:
    """A condition about a flip only after a flip of the same ability. (wave 45D) An ability that speaks of heads or tails marks its flips (705.2)."""
    if "'ht': True" in str(effects):
        _mark_heads_tails(effects)
    flipped = False
    for e in effects:  # (-- review (wave 7R) -- any nesting: a condition read before any flip would be false both ways)
        text = str(e)
        if "'coin_flip'" in text or "'do': 'clash'" in text:
            flipped = True
        elif "'coin':" in text and not flipped:
            return False
    return True


PRIMITIVES = {"coin_flip": coin_flip}
