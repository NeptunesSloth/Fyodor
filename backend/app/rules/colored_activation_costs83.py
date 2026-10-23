"""Exact own colored activation reductions, using native draw/entry receipts."""
from __future__ import annotations

from typing import Any

KAMI = "This ability costs {4}{B} less to activate if you've drawn three or more cards this turn."
DRONE = 'This ability costs {1}{U} less to activate if another creature with flying entered the battlefield under your control this turn.'


def sentence(text: str) -> str | None:
    from app.rules import cost_changes

    _, found = cost_changes.split_ability(text.split(':', 1)[-1])
    return found if found in (KAMI, DRONE) else None


def flying_receipts(plan: Any, player: str, card: Any) -> tuple[bool, bool]:
    from app.rules import history

    positive, unknown = False, False
    for entry in history.log_for(plan).entered:
        if entry.controller != player or entry.object_id == plan.oid(card):
            continue
        if entry.types is None:
            unknown = True
        elif 'Creature' in entry.types:
            if entry.keywords83 is None:
                unknown = True
            elif 'flying' in entry.keywords83:
                positive = True
    return positive, unknown


def reduction(state: Any, player: str, card: Any, text: str, info: Any) -> tuple[int, tuple[str, ...]]:
    from app.rules import history
    from app.rules.plan import Plan

    found = sentence(text)
    if found is None:
        return 0, ()
    view = Plan.view(state, player, info)
    if found == KAMI and history.log_for(view).drew.get(player, 0) >= 3:
        return 4, ('B',)
    if found == DRONE and flying_receipts(view, player, card)[0]:
        return 1, ('U',)
    return 0, ()


def require_known(plan: Any, card: Any, text: str) -> None:
    if sentence(text) != DRONE or plan.locked_cost is not None:
        return
    positive, unknown = flying_receipts(plan, plan.actor, card)
    if unknown and not positive:
        from app.game.errors import ActionError

        raise ActionError('This saved turn lacks entry-time flying history; resolve Flying Drone manually or begin a new native turn.')
