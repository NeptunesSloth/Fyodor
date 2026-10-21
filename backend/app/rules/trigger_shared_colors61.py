"""Spreading Plague selects one native destruction batch using current or LKI colors."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ("Whenever a creature enters, destroy all other creatures that share a color with it. "
        "They can't be regenerated.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text='Whenever a creature enters, you gain 1 life.'), ch)
    if native is None:
        return None
    return {**native, 'effects': [{'do': 'plague_shared_colors61'}, {'do': 'no_regen'}]}


def destroy_shared(plan: Any, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.rules import context, effects, selectors

    entering = context.info(plan, ctx, context.EVENT)
    if entering is None or not entering[1].colors:
        return True
    selected = selectors.Selector(types=('Creature',), colors=tuple(sorted(entering[1].colors))).key()
    # Native except uses exact ObjectRef identity; a blinked successor remains eligible.
    return effects.destroy(plan, ctx, {'do': 'destroy', 'who': 'except:event|' + selected})


PRIMITIVES = {'plague_shared_colors61': destroy_shared}
