"""Exact counter placements recorded by the native committed counter actions."""
from __future__ import annotations

from typing import Any

from app.game.rules_state import CounterPlacement as CounterPlacement


def store(ctx: dict[str, Any], binding: str, placements: list[CounterPlacement]) -> None:
    ctx.setdefault('counter_put_receipts', {})[binding] = [entry.model_dump(mode='json') for entry in placements]


def placements(ctx: dict[str, Any], binding: str) -> list[CounterPlacement]:
    return [CounterPlacement.model_validate(raw) for raw in ctx.get('counter_put_receipts', {}).get(binding, [])]
