"""CR 101.4, 701.23: each member of one player target group searches privately."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    if body.strip() != ('Choose two target players. Each of them searches their library for a card, '
                        'then shuffles and puts that card on top.'):
        return None
    chosen = scripts._parse_effects_plain('Choose two target players.')
    searched = scripts._parse_effects_plain('Target player searches their library for a card, then shuffles and puts that card on top.')
    if chosen is None or searched is None:
        return None
    return ([*chosen[0], {**searched[0][0], 'who': 'target:0', 'each_target': True}], chosen[1], False)
