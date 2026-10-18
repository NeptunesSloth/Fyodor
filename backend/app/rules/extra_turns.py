"""-- extra turns (wave 8A) -- "Take an extra turn after this one." (Temporal Manipulation, Capture of Jingzhou), "Target
player takes an extra turn after this one." (Time Warp, Beacon of Tomorrows), "Target player takes two extra turns after
this one." (Time Stretch), "You take an extra turn after this one." (Mu Yanling). Researched against CR 2026-09-25.

* 500.7: an effect that gives extra turns adds them directly after the specified turn ("after this one": the turn that is
  happening); several are added one at a time and the most recently created turn is taken first (so a stack). 500.7 is
  also why the turn after the extra turns is the one that would have followed the turn they were added to: the engine
  remembers whose regular turn it is (``turn_base``) and the turn order goes on from there.
* 614.10: a skipped turn never begins; an extra turn can be skipped like any other (skips.take), and a player who has left
  the game takes none (800.4a).
* "At the beginning of that turn's end step, you lose the game" (Final Fortune, Last Chance: wave 19A) is a delayed trigger made
  when the extra turn begins. Refused (manual): Warrior's Oath's extra clause, "Skip the untap step of that turn" (Savor the Moment), an extra turn per coin flip, and anything but a single
  player taking one, two or three extra turns directly "after this one".
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DelayedTrigger

if TYPE_CHECKING:
    from app.rules.plan import Plan

_N = {"an": 1, "two": 2, "three": 3}
_COUNT = r"(?P<n>an|two|three) extra turns?"


def _you(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "extra_turn", "who": "you", "n": _N[m["n"]]}], None


def _target(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "extra_turn", "who": "target", "n": _N[m["n"]]}], "player"


# -- static_other sweep (wave 19A) -- "Take an extra turn after this one. At the beginning of that turn's end step, you lose the game."
# (Final Fortune, Last Chance): 603.7 a delayed trigger of that turn, made as the turn begins (``take``) so a skipped extra turn
# (614.10) never leaves a loss waiting for another turn
LOSS = re.compile(r"(^|\. )Take an extra turn after this one\. At the beginning of that turn's end step, you lose the game\.")


# -- power-up (wave 50J) -- "Take an extra turn after this one. During that turn, power-up abilities can't be activated." (Kang the Conqueror): a rule of that turn, from the turn
# number it will have (take; read by restrictions)
NO_POWER_UP = re.compile(r"(^|\. )Take an extra turn after this one\. During that turn, power-up abilities can't be activated\.")


def one_sentence(body: str) -> str:
    """The two sentences read as one clause (the sentence split would part them)."""
    return NO_POWER_UP.sub(r"\1Take an extra turn after this one with no power-up abilities.", LOSS.sub(r"\1Take an extra turn after this one with a loss at its end step.", body))


def _you_no_power_up(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "extra_turn", "who": "you", "n": 1, "no_power_up": True}], None


def _you_then_lose(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    return [{"do": "extra_turn", "who": "you", "n": 1, "then_lose": True}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [
    (re.compile(r"^take an extra turn after this one with a loss at its end step$", re.I), _you_then_lose),
    (re.compile(r"^take an extra turn after this one with no power-up abilities$", re.I), _you_no_power_up),
    (re.compile(rf"^(?:take|you take) {_COUNT} after this one$"), _you),
    (re.compile(rf"^target player takes {_COUNT} after this one$"), _target),
]


def extra_turn(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """500.7: the extra turns are added one at a time, each taken before the ones created earlier."""
    from app.rules.effects import _players

    name = ctx.get("name") or "An effect"
    for pid in _players(plan, ctx, e["who"]):
        n = int(e.get("n") or 1)
        for _ in range(n):
            plan.rules.extra_turns.append({"player": pid, "label": name, **({"lose": True} if e.get("then_lose") else {}),
                                           **({"no_power_up": True} if e.get("no_power_up") else {})})
        plan.note(f"{plan.name(pid)} will take {'an' if n == 1 else n} extra turn{'s' if n > 1 else ''} after this one "
                  f"({name}, 500.7)", actor=ctx["controller"])
    return True


def take(plan: Plan) -> str | None:
    """The player whose extra turn is next (the most recently created first), or None. A turn that is skipped (614.10) or
    belongs to a player who has left is dropped."""
    from app.rules import skips

    r = plan.rules
    while r.extra_turns:
        rec = r.extra_turns.pop()
        pid = str(rec["player"])
        if pid not in plan.live():
            continue
        label = skips.take(plan, pid, "turn") or skips._static(plan, pid, "extra_turn")  # (wave 51G: a permanent that skips extra turns, 614.10)
        if label is not None:
            plan.note(f"{plan.name(pid)} skips their extra turn ({label}, 614.10)", actor=plan.active)
            continue
        plan.note(f"{plan.name(pid)} takes an extra turn ({rec.get('label') or 'an effect'}, 500.7)", actor=plan.active)
        if rec.get("no_power_up"):  # (wave 50J: that turn is the next one)
            r.no_power_up_turns.append(plan.state.turn.number + 1)
        if rec.get("lose"):  # (created between the turns: "a later turn" is that one, delayed._step_due)
            plan.rules.delayed.append(DelayedTrigger(
                id=secrets.token_hex(4), controller=pid, name=str(rec.get("label") or ""), when={"kind": "step", "step": "end", "whose": "next_turn"},
                effects=[{"do": "lose_game", "who": "you"}], refs={}, turn=plan.state.turn.number, step=plan.state.turn.phase, once=True,
                until_turn=plan.state.turn.number + 1))  # (review 19: only that turn's end step; one skipped or ended early, 724.1, is no loss later)
        return pid
    return None


PRIMITIVES = {"extra_turn": extra_turn}
