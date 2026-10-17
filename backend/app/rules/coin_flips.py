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

* -- coin events (wave 45C) -- 705.2: a flip the effect reads as won or lost (or reads neither: "Flip a coin.") has a winner or loser, only the
  player who flipped; a flip it reads as heads or tails ("If it comes up heads") has none ("Whenever you win a coin flip" doesn't see it,
  Setzer's ruling). Each such flip is one ``designation`` event (counter "coin_flip", ``amount`` 1 won / 0 lost, ``player`` the flipper):
  "Whenever you / a player win(s) / lose(s) a coin flip" (Setzer, Zndrsplt, Okaun).
* "Flip a coin until you lose a flip" (Zndrsplt, Okaun): one flip at a time, each its own flip and event, until one is lost.

Refused (manual): flipping several coins, "each player flips", ignoring flips (Krark's Thumb, Edgar), flipping at a later time
("at the beginning of the next end step") and the number of flips won as an amount ("for each flip you won").
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import emit

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

_FLIP = re.compile(r"^flip a coin(?P<until> until you lose a flip)?$")
_COND = re.compile(r"^(?:you (?P<w>win|lose) the flip|(?:it|the coin) comes up (?P<f>heads|tails)|(?P<c>you win))$")


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "coin_flip", **({"until_lose": True} if m["until"] else {})}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_FLIP, _build)]


def condition(text: str) -> dict[str, Any] | None:
    """"you win the flip" / "it comes up tails" → ``{"coin": "win" | "lose"}`` (heads is a win, 705.2), else None."""
    m = _COND.fullmatch(text)
    if m is None:
        return None
    if m["c"]:  # -- clash (wave 12A) -- "If you win" (701.30d), judged from this resolution's own clash (app/rules/clash.py)
        return {"coin": "win", "of": "clash"}
    return {"coin": "win" if (m["w"] == "win" or m["f"] == "heads") else "lose", **({"face": True} if m["f"] else {})}


_EVENT = re.compile(r"(?P<p>you|a player|an opponent) (?P<v>win|lose|wins|loses) a coin flip")


def event_condition(text: str) -> dict[str, Any] | None:
    """-- coin events (wave 45C) -- "you win a coin flip" / "a player loses a coin flip" → the trigger event (705.2: the flipper alone)."""
    m = _EVENT.fullmatch(text)
    if m is None:
        return None
    return {"event": "coin_flip", "subject": "player", "player": {"you": "you", "a player": "any", "an opponent": "opponent"}[m["p"]],
            "won": m["v"].startswith("win")}


def holds(ctx: Context, cond: dict[str, Any]) -> bool:
    flipped = ctx.get("clash" if cond.get("of") else "coin")
    return flipped is not None and bool(flipped) == (cond["coin"] == "win")


def coin_flip(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    import secrets

    if plan.rng is None:
        plan.rng = secrets.SystemRandom()  # (the result is recorded on the step: the history replays it, not the generator)
    face = "'face': True" in str(ctx.get("effects"))  # (705.2: the effect reads heads or tails: no winner or loser)
    for _ in range(1000 if e.get("until_lose") else 1):  # (ponytail: no game wins 1000 flips in a row)
        done = plan.do({"type": "coin", "count": 1}, actor=ctx["controller"])
        ctx["coin"] = bool(done.r.results[0])  # type: ignore[union-attr]
        if not face:
            emit(plan.state, "designation", counter="coin_flip", player=ctx["controller"], amount=int(ctx["coin"]))
        if not ctx["coin"]:
            break
    return True


def refs_ok(effects: list[dict[str, Any]]) -> bool:
    """A condition about a flip only after a flip of the same ability."""
    flipped = False
    for e in effects:  # (-- review (wave 7R) -- any nesting: a condition read before any flip would be false both ways)
        text = str(e)
        if "'coin_flip'" in text or "'do': 'clash'" in text:
            flipped = True
        elif "'coin':" in text and not flipped:
            return False
    return True


PRIMITIVES = {"coin_flip": coin_flip}
