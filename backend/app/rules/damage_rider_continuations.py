"""Saved immediate prevention bodies; synchronous completion belongs to the caller."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter

if TYPE_CHECKING:
    from app.rules.plan import Plan


@dataclass
class DamageRiderFrame:
    riders: list[dict[str, Any]]
    then: dict[str, Any]


_FRAME = TypeAdapter(DamageRiderFrame)


def run(plan: Plan, frame: DamageRiderFrame) -> bool:
    from app.rules import effects, source_shields

    for i, rider in enumerate(frame.riders):
        ctx = source_shields.rider_context(plan, rider)
        if ctx is None:
            continue
        rest = DamageRiderFrame(frame.riders[i + 1:], frame.then)
        ctx['body_done'] = {'do': 'damage_riders', 'frame': _FRAME.dump_python(rest, mode='json')}
        if not effects.run_body(plan, ctx):
            return False
    return True


def resume(plan: Plan, then: dict[str, Any]) -> None:
    from app.rules import replace

    frame = _FRAME.validate_python(then['frame'])
    if run(plan, frame):
        replace.run_then(plan, frame.then)


from app.rules import replace as _replace  # noqa: E402

_replace.THEN['damage_riders'] = resume


@dataclass
class ManaDamageFrame:
    events: list[dict[str, Any]]
    actor: str
    then: dict[str, Any]


_MANA = TypeAdapter(ManaDamageFrame)


def mana_damage(plan: Plan, frame: ManaDamageFrame, answers: dict[str, str] | None = None,
                order: list[str] | None = None) -> bool:
    from app.rules import replace

    answers = dict(answers or {})
    out = replace.damage_outcome(plan, frame.events, answers=answers, order=order, ask=True)
    request = _MANA.dump_python(frame, mode='json')
    resume_site = {'site': 'mana_damage', 'request': request, 'then': frame.then,
                   'answers': answers, 'order': list(order or [])}
    if isinstance(out, replace.ShieldAsk):
        replace.ask_shield(plan, out, resume_site, list(order or []))
        return False
    if not isinstance(out, replace.DamageOutcome):
        replace.ask(plan, out, answers, resume_site)
        return False
    return replace.do_damage(plan, out, actor=frame.actor, combat=False, then=frame.then)


def resume_mana(plan: Plan, request: dict[str, Any], answers: dict[str, str], order: list[str] | None) -> None:
    from app.rules import replace

    frame = _MANA.validate_python(request)
    if mana_damage(plan, frame, answers, order):
        replace.run_then(plan, frame.then)
