"""-- loops and repeats (wave 24B) -- "Repeat this process" (CR 2026-09-25, 608.2c).

The Comprehensive Rules have no rule of their own for "repeat this process": 608.2c has the controller follow the instructions in the
order written and "apply the rules of English to the text". "This process" is read as the instructions of the same ability before it
(every card with this wording repeats what the ability has said so far: Mana Clash's flips and damage, Professor Onyx's "may discard /
lose life", Zimone and Dina's draw and land, Demonlord Belzenlok's exile and take), nothing else: the targets and the costs stay as they
were chosen and paid, and the ability's own bindings ("that card", "this way") are those of the latest turn of the process.

* ``{"do": "repeat_process", "span": N, "times": n}`` — "Repeat this process once / six more times / X more times": the N instructions
  before it are carried out again, n times in all.
* ``{"do": "repeat_process", "span": N}`` — "If C, repeat this process" / "If you do, draw a card and repeat this process": the "If" is the
  ordinary conditional sentence in front of it (a gate over the repeat that the copy of the process carries too, so it is read again after
  each turn); only read after such a gate.
* ``{"do": "repeat_process", "span": N, "cond": C}`` — "Repeat this process until C" (``cond`` is C's negation), read again after each turn.
* ``{"do": "repeat_process", "span": N, "may": True}`` — "You may repeat this process any number of times": asked after each turn.

The repeat is unrolled as the resolution reaches it: the process's instructions are copied in right after it, followed by the repeat
itself (one fewer time when it counts), so a decision in the middle of a turn waits where it is and a save, a replay and undo see an
ordinary list of instructions (``ctx["effects"]`` is saved with the resolution). A process that never ends (a coin that keeps coming up
tails) stops after CAP turns: no game plays that long.
"""

from __future__ import annotations

import copy
import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules import values
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
CAP = 1000
STEP = "repeat_may"
_TIMES = re.compile(r"^repeat this process(?: (?P<n>once|twice|(?P<w>\w+|X) more times?))?$", re.IGNORECASE)
_MAY = re.compile(r"^(?:you may )?repeat this process any number of times$", re.IGNORECASE)
_UNTIL = re.compile(r"^repeat this process until (?P<c>.+)$", re.IGNORECASE)


def _times(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import scripts

    if m["n"] is None:
        return [{"do": "repeat_process", "span": None}], None  # (a bare "repeat this process": its "If …" before it says whether; ``finish``)
    if m["n"].lower() in ("once", "twice"):
        return [{"do": "repeat_process", "span": None, "times": 1 if m["n"].lower() == "once" else 2}], None
    n: Any = {"x": 1} if m["w"] in ("X", "x") else values.NUMBERS.get(m["w"].lower())
    if n is None:
        raise scripts._NoMatch
    return [{"do": "repeat_process", "span": None, "times": n}], None


def _may(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "repeat_process", "span": None, "may": True}], None


def _until(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    from app.rules import conditions, scripts

    cond = conditions.parse(m["c"], objects=True)
    if cond is None:
        raise scripts._NoMatch
    return [{"do": "repeat_process", "span": None, "cond": {"not": cond}}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_MAY, _may), (_UNTIL, _until), (_TIMES, _times)]


def may_sentence(text: str) -> list[dict[str, Any]] | None:
    """"…. You may repeat this process any number of times." mid-ability: the repeat itself is the optional thing (asked after each turn)."""
    return [{"do": "repeat_process", "span": None, "may": True}] if _MAY.fullmatch(text) else None


def plain(body: str) -> str:
    """"…, put it into your graveyard and repeat this process": two instructions in order (608.2c), as "…, then repeat this process"."""
    return re.sub(r"(, [^,.]+?) and repeat this process\b", r"\1, then repeat this process", body) if "repeat this process" in body else body


def finish(effects: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """The spans: a repeat repeats every instruction of the ability before it. None: nothing to repeat."""
    out = []
    for k, e in enumerate(effects):
        if e.get("do") == "repeat_process":
            bare = "times" not in e and "cond" not in e and not e.get("may")
            if k == 0 or (bare and not any(x.get("do") == "only_if" and j + int(x.get("skip", 0)) >= k for j, x in enumerate(effects[:k]))):
                return None  # (nothing to repeat; or a repeat nothing ever stops)
            e = {**e, "span": k}
        out.append(e)
    return out


def _again(plan: Plan, ctx: Context, e: dict[str, Any], rest: dict[str, Any] | None = None) -> None:
    """Carry the process out once more: its instructions (copied) and the repeat, right after this one."""
    effects, i = ctx["effects"], ctx["next"]
    body = copy.deepcopy(effects[i - 1 - e["span"]: i - 1])
    nxt = {**e, **(rest or {}), "turn": int(e.get("turn", 0)) + 1}
    ctx["effects"] = [*effects[:i], *body, nxt, *effects[i:]]


def repeat_process(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import conditions, effects

    if int(e.get("turn", 0)) >= CAP:
        plan.note("The process was repeated as often as the game allows")
        return True
    if e.get("may"):
        decide(plan, player=ctx["controller"], kind="confirm", prompt=f"{ctx.get('name') or 'Repeat'}: repeat this process?",
               options=[DecisionOption(id="yes", label="Repeat it"), DecisionOption(id="no", label="Stop")],
               resume={"step": STEP, "ctx": ctx, "e": e})
        return False
    if "times" in e:
        left = max(0, int(effects._amount(plan, ctx, e["times"])))
        if left > 0:
            _again(plan, ctx, e, {"times": left - 1})
        return True
    if e.get("cond") is None or conditions.holds(plan, ctx, e["cond"]):  # (bare: the "If …" before it, repeated with the process, decides)
        _again(plan, ctx, e)
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    if chosen[0] == "yes":
        _again(plan, ctx, e)
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"repeat_process": repeat_process}
