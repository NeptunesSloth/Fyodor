"""Pure, opt-in allocation of a finite redirect pool between simultaneous sources.

This deliberately supports one original recipient only. Cross-recipient allocations
need a distinct frontier/chooser design and are not inferred from packet order.
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules import group_choice, replace

if TYPE_CHECKING:
    from app.rules.plan import Plan

PREFIX = "redirect_allocation:"
STEP = "redirect_amount"


class AllocationAsk(replace.ShieldAsk):
    def __init__(self, request: dict[str, Any]):
        super().__init__(request["target"], request["chooser"], request["rows"], request["total"])
        self.request = request


def allocations(answers: dict[str, str]) -> dict[str, dict[str, int]]:
    return {
        k: {str(row): int(n) for row, n in json.loads(value).items()}
        for k, value in answers.items()
        if k.startswith(PREFIX)
    }


def identity(candidate: Any, event: dict[str, Any]) -> str:
    return PREFIX + candidate.id + ":" + event["target"] + ":" + str(event.get("target_oid") or "")


def amount(sim: dict[str, Any], candidate: Any, event: dict[str, Any], left: int) -> int:
    key = identity(candidate, event)
    row = str(event["_redirect_lineage"]) + ":" + ",".join(event.get("applied") or [])
    profiles = sim.setdefault("redirect_profiles", {}).setdefault(key, {})
    profiles[row] = {
        "row": row,
        "amount": int(event["amount"]),
        "source_card": event.get("source_card"),
        "source_oid": event.get("source_oid"),
        "src": dict(event.get("src") or {}),
        "target": event["target"],
        "target_oid": event.get("target_oid"),
    }
    choice = (sim.get("redirect_allocations") or {}).get(key)
    return (
        min(int(event["amount"]), left, max(0, int(choice.get(row, 0))))
        if choice is not None
        else min(int(event["amount"]), left)
    )


def validate(
    plan: Plan, sim: dict[str, Any], candidates: list[Any], answers: dict[str, str]
) -> AllocationAsk | None:
    selected = sim.get("redirect_allocations") or {}
    profiles = sim.get("redirect_profiles") or {}
    for candidate in candidates:
        recipients = {
            r["target"]
            for k, rows in profiles.items()
            if k.startswith(PREFIX + candidate.id + ":")
            for r in rows.values()
        }
        if len(recipients) > 1:
            raise ValueError("Single-recipient redirection cannot allocate across recipients")
    for key, profile in (sim.get("redirect_profiles") or {}).items():
        rows = list(profile.values())
        if len({r["target"] for r in rows}) != 1:
            raise ValueError("Single-recipient redirection cannot allocate across recipients")
        candidate = next(c for c in candidates if key.startswith(PREFIX + c.id + ":"))
        budget = int(candidate.op["limit"])
        total = min(budget, sum(r["amount"] for r in rows))
        chosen = selected.get(key)
        # A one-packet unchosen pool has no allocation decision.
        if chosen is None and len(rows) < 2:
            continue
        if (
            chosen is not None
            and set(chosen) == set(profile)
            and sum(chosen.values()) == total
            and all(0 <= chosen[r["row"]] <= r["amount"] for r in rows)
        ):
            continue
        target = rows[0]["target"]
        chooser = target if target in plan.state.players else plan.state.cards[target].controller
        return AllocationAsk(
            {
                "key": key,
                "candidate": candidate.id,
                "target": target,
                "chooser": chooser,
                "rows": rows,
                "total": total,
                "budget": budget,
            }
        )
    return None


def ask(plan: Plan, q: AllocationAsk, resume: dict[str, Any], order: list[str]) -> None:
    frame = {
        "request": q.request,
        "site_resume": copy.deepcopy(resume),
        "order": list(order),
        "i": 0,
        "amounts": {},
        "left": q.request["total"],
    }
    _choose(plan, frame)


def _choose(plan: Plan, frame: dict[str, Any]) -> None:
    from app.rules.plan import decide

    request = frame["request"]
    rows = request["rows"]
    i = frame["i"]
    if i >= len(rows) - 1:
        if i < len(rows):
            frame["amounts"][rows[i]["row"]] = frame["left"]
        _finish(plan, frame)
        return
    row = rows[i]
    names = row["src"].get("names") or []
    label = names[0] if names else "this source"
    decide(
        plan,
        player=request["chooser"],
        kind="choose_one",
        prompt=f"Redirect how much damage from {label}? ({frame['left']} left to allocate)",
        options=[DecisionOption(id=group_choice.NUMBER, label="Type a number ≥ 0", group="number")],
        resume={"step": STEP, "frame": frame},
    )


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    frame = d.resume["frame"]
    n = int(chosen[0])
    left = int(frame["left"])
    if n < 0 or n > left:
        raise ActionError(f"Choose an amount from 0 to {left}")
    row = frame["request"]["rows"][frame["i"]]
    frame["amounts"][row["row"]] = n
    frame["left"] = left - n
    frame["i"] += 1
    _choose(plan, frame)


def _finish(plan: Plan, frame: dict[str, Any]) -> None:
    r = frame["site_resume"]
    # A new allocation can make a former order relevant. Re-ask those orders
    # before committing; preserve only other independently saved allocations.
    answers = {k: v for k, v in (r.get("answers") or {}).items() if k.startswith(PREFIX)}
    answers[frame["request"]["key"]] = json.dumps(frame["amounts"], sort_keys=True)
    replace.resume_site(plan, r, answers, [])


RESUME = {STEP: resume}
