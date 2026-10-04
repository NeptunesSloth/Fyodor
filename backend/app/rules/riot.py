"""-- keywords (wave 15E) -- riot (702.136) and unleash (702.98): an "as it enters" choice made before it enters (614.12a), like
the other entering answers (app/rules/devour.py is the model).

* 702.136a — riot: "You may have this permanent enter with an additional +1/+1 counter on it. If you don't, it gains haste."
  The haste is for as long as it stays on the battlefield (a permanent layer-6 effect, like dash's).
* 702.98a — unleash: "You may have this permanent enter with an additional +1/+1 counter on it" and "This permanent can't block
  as long as it has a +1/+1 counter on it" (the second is a static, scripts._define).

Only one instance of either keyword on an object is read (702.136b: several work separately — left manual). The answer is
``choices["riot"]``: "counter", "haste" (riot) or "none" (unleash).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

WHAT = "riot"


def instances(ch: Any) -> list[str]:
    return [kw for ab in ch.abilities if ab.kind == "keywords" for kw in ab.keywords if kw in ("riot", "unleash")]


def spec(ch: Any) -> str | None:
    """"riot" or "unleash" when the object has exactly one instance of exactly one of them."""
    found = instances(ch)
    return found[0] if len(found) == 1 else None


def supported(kw: str, line: str) -> bool:
    """A keyword line of the engine's (unleash needs its own line: its static is that line's definition)."""
    text = re.sub(r"\s*\(.*?\)", "", line).strip().rstrip(".").lower()
    return text == "unleash" if kw == "unleash" else text.split(", ").count("riot") == 1


def plan_entry(plan: Plan, card: CardInstance, controller: str, answers: dict[str, str], out: dict[str, Any]) -> None:
    """replacements.entry_plan's part: the question (``out["choice"]``) or the answer in ``out["choices"]``."""
    if plan.manual(card):
        return
    ch = plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller}))
    if spec(ch) is None:
        return
    if answers.get(WHAT) in ("counter", "haste", "none"):
        out.setdefault("choices", {})[WHAT] = answers[WHAT]
    elif "choice" not in out:
        out["choice"] = {"what": WHAT}


def is_choice(what: str) -> bool:
    return what == WHAT


def prompt(plan: Plan, card: CardInstance, controller: str) -> tuple[str, list[DecisionOption]]:
    ch = plan.ch(card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller}))
    if spec(ch) == "riot":
        return (f"{card.name}: riot — enter with a +1/+1 counter, or gain haste?",
                [DecisionOption(id="counter", label="A +1/+1 counter"), DecisionOption(id="haste", label="Haste")])
    return (f"{card.name}: unleash — enter with a +1/+1 counter?",
            [DecisionOption(id="counter", label="A +1/+1 counter"), DecisionOption(id="none", label="No counter")])


def counters(ch: Any, choices: dict[str, str] | None) -> int:
    return 1 if spec(ch) is not None and (choices or {}).get(WHAT) == "counter" else 0


def gains_haste(ch: Any, choices: dict[str, str] | None) -> bool:
    return spec(ch) == "riot" and (choices or {}).get(WHAT) == "haste"
