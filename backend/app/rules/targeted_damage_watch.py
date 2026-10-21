"""CR 603.7a/c: bind the player named by a spell for a later combat-damage watch."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip() != ("Choose target opponent. Whenever a creature you control deals combat damage to that player this turn, "
                        "create a tapped Treasure token."):
        return None
    from app.rules import scripts

    chosen = scripts._parse_effects_plain('Choose target opponent.')
    watch = scripts._parse_effects_plain('Whenever a creature you control deals combat damage to an opponent this turn, create a tapped Treasure token.')
    if chosen is None or watch is None or watch[1] is not None:
        return None
    effects, target, _ = chosen
    deferred = watch[0]
    if not deferred or deferred[0].get('do') != 'delayed':
        return None
    deferred[0]['when'] = {**deferred[0]['when'], 'recipient_ref': 'target'}
    return [*effects, *deferred], target, False
