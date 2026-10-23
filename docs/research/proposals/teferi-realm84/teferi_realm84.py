"""Teferi's Realm chooses a public permanent category before native group phasing."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = "At the beginning of each player's upkeep, that player chooses artifact, creature, land, or non-Aura enchantment. All nontoken permanents of that type phase out."
WHAT = 'permanent type: artifact, creature, land, or non-Aura enchantment'
BIND = 'realm84_type'
CHOICES = {'Artifact': 'nontoken artifacts', 'Creature': 'nontoken creatures', 'Land': 'nontoken lands', 'Non-Aura enchantment': 'nontoken non-Aura enchantments'}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    native = scripts.define(replace(ability, text="At the beginning of each player's upkeep, that player draws a card."), ch)
    return {**native, 'effects': [{'do': 'choose_value', 'who': 'event_player', 'what': WHAT, 'as': BIND},
                                  {'do': 'realm_phase84'}]} if native is not None else None


def phase(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.errors import ActionError
    from app.rules import context, effects, phasing, selectors

    chosen = context.refs(ctx).get(BIND, {}).get('value')
    if chosen not in CHOICES:
        if not effects._players(plan, ctx, 'event_player'):
            return True
        raise ActionError('The saved permanent category is missing; resolve this ability manually')
    sel = selectors.parse(CHOICES[chosen])
    assert sel is not None
    return phasing.phase_out(plan, ctx, {'who': sel.key()})


PRIMITIVES = {'realm_phase84': phase}
