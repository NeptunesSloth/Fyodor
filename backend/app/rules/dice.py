"""-- rolling dice (wave 12A) -- "Roll a d20." (Ancient Gold Dragon), "Roll a six-sided die." (Vegetation Abomination), "Roll two
d12 and choose one result." (Reckless Endeavor), with the result as an amount: "equal to the result", "that result", "the other
result". Researched against CR 2026-09-25, 706.

* 706.1a: a dN has N equally likely outcomes, 1 to N. The table's recorded "roll" action is one randomizer (the result is in the
  history, so a replay or a reload reproduces it): app/game/actions.py ``Roll``.
* 706.2: the natural result is the number rolled; no modifier exists unless an effect makes one (not read: see below).
* 706.4: an ability without a results table says in its text how the result is used; here as an amount, read from this
  resolution's own roll (``ctx["die"]``; ``ctx["die_other"]`` for the other die of "choose one result": the roller chooses).

-- wave 13E -- "Whenever you roll one or more dice" is a trigger event (a "designation" event, counter "roll", once per roll of
any number of dice; its highest result rides along); the results themselves are not read by a trigger yet.

Refused (manual): results tables (706.3), triggers that read a result, rerolls and ignored rolls (706.2b, 706.6), "roll X dice",
rolling for each player, a roll that is part of a cost, a result used by a reflexive "When you do" ability.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
STEP = "roll_choose"
_SIDES = {"four": 4, "six": 6, "eight": 8, "ten": 10, "twelve": 12, "twenty": 20}
_ONE = re.compile(r"^roll (?:a d(?P<n>\d+)|a (?P<w>four|six|eight|ten|twelve|twenty)-sided die)$")
_TWO = re.compile(r"^roll two d(?P<n>\d+) and choose one result$")
_RESULT = {"the result": "result", "that result": "result", "the other result": "other"}


def _one(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    sides = int(m["n"]) if m["n"] else _SIDES[m["w"]]
    return ([{"do": "roll", "sides": sides, "count": 1}] if 2 <= sides <= 1000 else []), None


def _two(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return ([{"do": "roll", "sides": int(m["n"]), "count": 2}] if 2 <= int(m["n"]) <= 1000 else []), None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_ONE, _one), (_TWO, _two)]


def amount(phrase: str) -> dict[str, Any] | None:
    """"the result" / "that result" / "the other result" → the value ``{"die": "result" | "other"}``."""
    which = _RESULT.get(phrase)
    return {"die": which} if which else None


_AT = re.compile(r"^the result is (?P<n>\d+) or (?P<c>less|more|greater)$")
_ROLLED = re.compile(r"\broll a (?:d\d+|\w+-sided die)\b.*\bthe result is\b", re.I)


def condition(text: str) -> dict[str, Any] | None:
    """"the result is 3 or less" / "… 4 or greater" → a comparison of this resolution's roll (706.4)."""
    m = _AT.fullmatch(text)
    return {"value": {"die": "result"}, "op": "<=" if m["c"] == "less" else ">=", "n": int(m["n"])} if m else None


def plain(body: str) -> str:
    """"Roll a six-sided die. If the result is 3 or less, you lose that much life.": "that much" is the result."""
    return re.sub(r"\bthat much (life|damage)", r"\1 equal to the result", body) if _ROLLED.search(body) else body


def evaluate(ctx: Context, which: str) -> int:
    return max(0, int(ctx.get("die" if which == "result" else "die_other") or 0))


def roll(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    import secrets

    if plan.rng is None:
        plan.rng = secrets.SystemRandom()  # (the result is recorded on the step: the history replays it, not the generator)
    pid = ctx["controller"]
    done = plan.do({"type": "roll", "sides": e["sides"], "count": e["count"]}, actor=pid)
    results = list(done.r.results)  # type: ignore[union-attr]
    from app.game.rules_state import emit

    emit(plan.state, "designation", counter="roll", player=pid, amount=max(results))  # "Whenever you roll one or more dice"
    if e["count"] == 1 or results[0] == results[1]:
        ctx["die"], ctx["die_other"] = results[0], results[-1]
        return True
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name') or 'Roll'}: choose one result",
           options=[DecisionOption(id=str(i), label=str(r)) for i, r in enumerate(results)],
           resume={"step": STEP, "ctx": ctx, "results": results})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    if len(chosen) != 1 or chosen[0] not in ("0", "1"):
        raise ActionError("Choose one of the results")
    results, ctx = r["results"], r["ctx"]
    ctx["die"], ctx["die_other"] = results[int(chosen[0])], results[1 - int(chosen[0])]
    plan.note(f"{plan.name(d.player)} chooses {ctx['die']}")
    effects.continue_effects(plan, ctx)


def refs_ok(effects: list[dict[str, Any]]) -> bool:
    """An amount from a roll only after a roll of the same ability."""
    rolled = False
    for e in effects:
        text = str(e)
        if "'do': 'roll'" in text:
            rolled = True
        elif "'die':" in text and not rolled:
            return False
    return True


PRIMITIVES = {"roll": roll}
