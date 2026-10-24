"""Balthier and Fran read actual original crew contributors at native attack triggers."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = "Whenever a Vehicle crewed by ~ this turn attacks, if it's the first combat phase of the turn, you may pay {1}{R}{G}. If you do, after this phase, there is an additional combat phase."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    proxy = TEXT.replace(' crewed by ~ this turn', '')
    native = scripts.define(replace(ability, text=proxy), ch)
    if native is None:
        return None
    return {**native, 'if': {'all': [native['if'], {'crewed_by_source84': True}]}}


def holds(plan: Any, ctx: dict[str, Any]) -> bool:
    from app.rules import crew_saddle

    event = ctx.get('event') or {}
    return any(crew_saddle.tapped_for(plan, 'crew', ctx.get('source_object'), ref.get('object_id'))
               for ref in event.get('objects') or [])
