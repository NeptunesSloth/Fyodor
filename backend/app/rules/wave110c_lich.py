"""-- Phylactery Lich (wave 110C) -- "As this creature enters, put a phylactery counter on an artifact you control."

614.1c / 614.12a: a replacement effect of the permanent entering, not a trigger (603.6d): the artifact is chosen and gets the counter immediately
before the Lich enters, so its state trigger (603.8: "When you control no permanents with phylactery counters on them, sacrifice this creature.")
never sees the empty state unless the controller has no artifact (then nothing is chosen and the Lich is sacrificed). The counter goes through
the counter choke point (122.6, 614.16). One artifact is the whole choice; with a single artifact it is not asked."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.state import zone_key
from app.rules.plan import DecisionOption

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

DO = "phylactery110c"
WHAT = "phylactery artifact110c"


def artifacts(plan: Plan, controller: str, entering: str | None = None) -> list[str]:
    return [c for c in plan.state.zones.get(zone_key(controller, "battlefield"), [])
            if c != entering and plan.in_game(plan.state.cards[c]) and "Artifact" in plan.ch(plan.state.cards[c]).types]


def plan_entry(plan: Plan, card: CardInstance, controller: str, answers: dict[str, str] | None, out: dict[str, Any]) -> None:
    found = artifacts(plan, controller, card.id)
    if len(found) == 1:
        out.setdefault("choices", {})[WHAT] = found[0]
    elif found and (given := (answers or {}).get(WHAT)) is not None:
        out.setdefault("choices", {})[WHAT] = given
    elif found:
        out.setdefault("choice", {"what": WHAT})


def prompt(plan: Plan, card: CardInstance, controller: str) -> tuple[str, list[DecisionOption]]:
    return (f"{card.name}: as it enters, put a phylactery counter on an artifact you control",
            [DecisionOption(id=c, label=plan.state.cards[c].name or "artifact", card_id=c) for c in artifacts(plan, controller, card.id)])


def put(plan: Plan, card_id: str, ep: dict[str, Any], controller: str) -> None:
    from app.rules import replace

    target = (ep.get("choices") or {}).get(WHAT)
    if target in artifacts(plan, controller, card_id):  # (gone meanwhile: nothing to put it on)
        replace.put_counters(plan, [(target, "phylactery", 1)], by=controller)
