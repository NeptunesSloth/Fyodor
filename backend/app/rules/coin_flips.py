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

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

_FLIP = re.compile(r"^flip a coin(?P<until> until you lose a flip)?$")
_COND = re.compile(r"^(?:you (?P<w>win|lose) the flip|(?:it|the coin) comes up (?P<f>heads|tails)|(?P<c>you win))$")
# -- chosen filters (wave 53B) -- several flips, as many as the number chosen earlier in this resolution: "Flip a coin that many times or until you lose a flip, whichever comes first."
# (Squee's Revenge), "Flip that many coins." (Yusri); each is its own flip (705.2) and the ones won / lost are counted: "for each flip you win, draw a card", "If you win all the flips",
# "If you won five flips this way", "draw two cards for each flip"
_MANY = re.compile(r"^flip (?:a coin (?:that many|the chosen number) times(?P<until> or until you lose a flip, whichever comes first)|(?:that many|the chosen number) coins)$")
_FOR_EACH = re.compile(r"^for each flip you (?P<w>win|lose), (?P<rest>.+)$")
_DRAW_EACH = re.compile(r"^draw (?P<n>a|an|one|two|three|four|five) cards? for each flip$")
_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_WON_N = re.compile(r"^you won (?P<n>one|two|three|four|five|six|seven|eight|nine|ten) flips this way$")
_NUMS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "coin_flip", **({"until_lose": True} if m["until"] else {})}], None


def _build_many(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "coin_flip", "n": {"chosen_n": 1}, **({"until_lose": True} if m["until"] else {})}], None


def _counted(effect: dict[str, Any], kind: str, factor: int | None = None) -> dict[str, Any]:
    n = factor if factor is not None else effect.get("n")
    return {**effect, "n": {"coin_flips": kind} if n == 1 else {"times": [n, {"coin_flips": kind}]}}


def _build_for_each(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules.scripts import _NoMatch, _one_clause

    found = _one_clause(m["rest"])
    if found is None or found[1] is not None or len(found[0]) != 1 or not isinstance(found[0][0].get("n"), int):
        raise _NoMatch
    return [_counted(found[0][0], "won" if m["w"] == "win" else "lost")], None


def _build_draw_each(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [_counted({"do": "draw", "who": "you"}, "flips", _WORDS[m["n"]])], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_FLIP, _build), (_MANY, _build_many), (_FOR_EACH, _build_for_each), (_DRAW_EACH, _build_draw_each)]


def condition(text: str) -> dict[str, Any] | None:
    """"you win the flip" / "it comes up tails" → ``{"coin": "win" | "lose"}`` (heads is a win, 705.2), else None."""
    if text == "you win all the flips":  # -- chosen filters (wave 53B) -- every flip of this resolution was won (none stopped by a lost one)
        return {"coin": "all"}
    if (won := _WON_N.fullmatch(text)) is not None:
        return {"coin": "wins", "n": _NUMS.index(won["n"])}
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


def count(ctx: Context, kind: str) -> int:
    """-- chosen filters (wave 53B) -- the flips of this resolution: "won", "lost" or all of them."""
    flips = ctx.get("flips") or []
    return flips.count(True) if kind == "won" else flips.count(False) if kind == "lost" else len(flips)


def holds(ctx: Context, cond: dict[str, Any]) -> bool:
    if cond["coin"] == "all":  # (wave 53B)
        return bool(ctx.get("flips")) and all(ctx["flips"])
    if cond["coin"] == "wins":
        return count(ctx, "won") == cond["n"]
    flipped = ctx.get("clash" if cond.get("of") else "coin")
    return flipped is not None and bool(flipped) == (cond["coin"] == "win")


def coin_flip(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import coin_outcomes

    face = bool(e.get("face")) or "'face': True" in str(ctx.get("effects"))
    many = e.get("n") if isinstance(e.get("n"), int) else None
    if not e.get('until_lose'):
        return coin_outcomes.group(plan, ctx, [{'player': ctx['controller']} for _ in range(many if many is not None else 1)], face=face)
    return _loop(plan, ctx, {'do': 'coin_flip_finish', 'remaining': many, 'all': [], 'face': face})


def _loop(plan: Plan, ctx: Context, after: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import coin_outcomes
    from app.rules.plan import decide

    while after['remaining'] != 0:
        if len(plan.steps) >= plan.max_steps - 40:
            decide(plan, player=ctx['controller'], kind='confirm', prompt='Continue the mandatory coin process.',
                   options=[DecisionOption(id='continue', label='Continue resolving')],
                   resume={'step': 'coin_loop', 'ctx': ctx, 'after': after})
            return False
        ctx['coin_after'] = after
        if not coin_outcomes.group(plan, ctx, [{'player': ctx['controller']}], face=after['face']):
            return False
        ctx.pop('coin_after', None)
        _collect(ctx, after)
        if not ctx['coin']:
            break
    ctx['flips'] = after['all']
    return True


def _collect(ctx: Context, after: dict[str, Any]) -> None:
    after['all'].extend(ctx['flips'])
    if after['remaining'] is not None:
        after['remaining'] -= len(ctx['flips'])


def finish_flip(plan: Plan, ctx: Context, after: dict[str, Any]) -> bool:
    _collect(ctx, after)
    if ctx['coin'] and after['remaining'] != 0:
        return _loop(plan, ctx, after)
    ctx['flips'] = after['all']
    return True


def resume_loop(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if _loop(plan, d.resume['ctx'], d.resume['after']):
        effects.continue_effects(plan, d.resume['ctx'])


def refs_ok(effects: list[dict[str, Any]]) -> bool:
    """A condition about a flip only after a flip of the same ability."""
    flipped = False
    for e in effects:  # (-- review (wave 7R) -- any nesting: a condition read before any flip would be false both ways)
        text = str(e)
        if "'coin_flip'" in text or "'do': 'clash'" in text:
            flipped = True
        elif ("'coin':" in text or "'coin_flips'" in text) and not flipped:
            return False
    return True


PRIMITIVES = {"coin_flip": coin_flip, "coin_flip_finish": finish_flip}
RESUME = {"coin_loop": resume_loop}
