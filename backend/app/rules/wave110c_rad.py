"""-- optional entering choice (wave 110C) -- 614.1c, 614.12a: "You may have this land enter tapped. If you do, you get two rad counters." (Mariposa Military Base).
Made before it enters, like riot (app/rules/riot.py is the model): the answer is ``choices["rad110c"]`` ("tapped" | "no"); the counters are put (122.1j rad counters,
through the counter choke point) as it enters, by its controller."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

WHAT = "rad110c"
REPLACEMENT = "tapped_for_rad110c"
_TEXT = "You may have this land enter tapped. If you do, you get two rad counters."


def definition(text: str) -> dict[str, Any] | None:
    return {"kind": "replacement", "replacement": REPLACEMENT, "n": 2, "effects": []} if text.replace("~", "this land") == _TEXT else None


def plan_entry(card: CardInstance, defs: list[dict[str, Any]], answers: dict[str, str], out: dict[str, Any]) -> None:
    """replacements.entry_plan's part: the question (``out["choice"]``), or the answer in ``out["choices"]`` (and the tapped entry it asks for)."""
    if not any(d["replacement"] == REPLACEMENT for d in defs):
        return
    if answers.get(WHAT) in ("tapped", "no"):
        out.setdefault("choices", {})[WHAT] = answers[WHAT]
        out["tapped"] = out["tapped"] or answers[WHAT] == "tapped"
    elif "choice" not in out:
        out["choice"] = {"what": WHAT}


def prompt(card: CardInstance) -> tuple[str, list[DecisionOption]]:
    return (f"{card.name}: have it enter tapped? If you do, you get two rad counters.",
            [DecisionOption(id="tapped", label="Enter tapped, get two rad counters"), DecisionOption(id="no", label="Enter untapped")])


def apply(plan: Plan, card_id: str, controller: str, choices: dict[str, str] | None) -> None:
    if (choices or {}).get(WHAT) == "tapped":
        from app.rules import replace

        replace.put_counters(plan, [(controller, "rad", 2)], by=controller)
