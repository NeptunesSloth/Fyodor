"""-- keywords (wave 50H) -- tribute N (CR 702.104), researched against the stored Comprehensive Rules (2026-09-25) and the 2014-02-01 / 2017-04-18 rulings.

* 702.104a — "Tribute N" means "As this creature enters, choose an opponent. That player may put an additional N +1/+1 counters on it as it
  enters." The controller chooses the opponent (asked only when there is more than one), then that opponent decides, privately, as a question of
  their own (app/rules/replacements.py: ``choice["decider"]``); the creature enters with the counters (614.12a; ruling: the opponent doesn't get
  to respond, and the counters are put by that opponent, not by the creature's controller, 2017-04-18).
* 702.104b — "if tribute wasn't paid" is true unless the chosen opponent had the creature enter with the counters: ``RulesState.tribute_paid``
  holds the objects that were paid for (a new object, 400.7, is unpaid), read by conditions._cast_holds.

Only one tribute instance on an object is read. The answers are ``choices["tribute_opp"]`` (a player id) and ``choices["tribute"]`` ("pay" or "no").
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

WHAT = "tribute"
OPP = "tribute_opp"
_LINE = re.compile(r"tribute (?P<n>\d+)")


def spec(ch: Any) -> int | None:
    """N of the object's one "Tribute N" line, or None."""
    found = [m["n"] for ab in ch.abilities if ab.kind == "keywords" and "tribute" in ab.keywords
             and (m := _LINE.fullmatch(re.sub(r"\s*\(.*?\)", "", ab.text).strip().rstrip(".").lower())) is not None]
    return int(found[0]) if len(found) == 1 else None


def supported(line: str) -> bool:
    return _LINE.fullmatch(re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".").lower()) is not None


def plan_entry(plan: Plan, card: CardInstance, controller: str, answers: dict[str, str], out: dict[str, Any]) -> None:
    """replacements.entry_plan's part: the question (``out["choice"]``, with its ``decider``) or the answers in ``out["choices"]``."""
    if plan.manual(card) or "choice" in out:
        return
    if spec(plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller}))) is None:
        return
    opponents = [p for p in plan.live() if p != controller]
    opp = answers.get(OPP) if answers.get(OPP) in opponents else opponents[0] if len(opponents) == 1 else ""
    if not opponents:  # (no opponent left to choose, 800.4: tribute isn't paid)
        out.setdefault("choices", {}).update({OPP: "", WHAT: "no"})
    elif not opp:
        out["choice"] = {"what": OPP}
    elif answers.get(WHAT) in ("pay", "no"):
        out.setdefault("choices", {}).update({OPP: opp, WHAT: answers[WHAT]})
    else:
        out["choices"] = {**out.get("choices", {}), OPP: opp}
        out["choice"] = {"what": WHAT, "decider": opp}


def is_choice(what: str) -> bool:
    return what in (WHAT, OPP)


def prompt(plan: Plan, card: CardInstance, controller: str, choice: dict[str, Any]) -> tuple[str, list[DecisionOption]]:
    if choice["what"] == OPP:
        return (f"{card.name}: tribute — as it enters, choose an opponent",
                [DecisionOption(id=p, label=plan.name(p)) for p in plan.live() if p != controller])
    n = spec(plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller}))) or 0
    return (f"{card.name} (tribute {n}): put {n} additional +1/+1 counter{'s' if n != 1 else ''} on it as it enters?",
            [DecisionOption(id="pay", label=f"Pay tribute: {n} +1/+1 counter{'s' if n != 1 else ''}"), DecisionOption(id="no", label="Don't pay tribute")])


def counters(ch: Any, choices: dict[str, str] | None) -> int:
    n = spec(ch)
    return n if n is not None and (choices or {}).get(WHAT) == "pay" else 0
