"""Native persistent, exact-object white mana replacements."""
from __future__ import annotations

import secrets
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.characteristics import AbilityText, Characteristics
    from app.rules.plan import Plan

TEXT = '{T}: If target Plains is tapped for mana, it produces colorless mana instead of white mana.'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'activated' or ability.text != TEXT:
        return None
    base = scripts.define(replace(ability, text='{T}: Tap target Plains.'), ch)
    if base is None:
        return None
    return {**base, 'effects': [{'do': 'record_white_mana_replacement', 'who': 'target'}]}


def record(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import ResolvedManaColorReplacement
    from app.rules import context, effects

    for cid in effects._cards(plan, ctx, e['who']):
        ref = context.ref_of(plan, cid)
        if ref is not None and (ref.zone or '').endswith(':battlefield'):
            plan.rules.resolved_mana_replacements.append(ResolvedManaColorReplacement(
                id=secrets.token_hex(8), target=ref, source_object=ctx.get('source_object')))
    return True


def statics(state: GameState) -> list[tuple[str, dict[str, Any]]]:
    rules = state.rules
    if rules is None:
        return []
    out = []
    for receipt in rules.resolved_mana_replacements:
        card = state.cards.get(receipt.target.card)
        if card is None or not card.zone.endswith(':battlefield') or rules.object_id(card.id) != receipt.target.object_id:
            continue
        out.append((card.controller, {'kind': 'static', 'static': 'mana_replace', 'who': 'any',
            'sel': 'sel:{}', 'op': {'do': receipt.op}, 'target_object': receipt.target.object_id,
            'effect_id': receipt.id, 'effects': []}))
    return out


PRIMITIVES = {'record_white_mana_replacement': record}
