"""Triggers carried by the exact authority a player actually used."""
from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from app.game.rules_state import ObjectRef, PermissionUseTrigger, TriggerEvent

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.plan import Plan


def static_receipt(state: GameState, source: CardInstance, index: int, kind: Any) -> PermissionUseTrigger | None:
    if kind is None:
        return None
    definition = None
    if isinstance(kind, dict) and kind.get("kind") == "native":
        definition = kind.get("definition")
        if not isinstance(definition, dict) or not isinstance(definition.get("effects"), list):
            raise ValueError("A native permission trigger requires an effect definition")
        kind = "native"
    if kind not in ("replenish_top", "owner_loses_mv", "create_food69", "native") or state.rules is None:
        raise ValueError("Unknown permission-use trigger")
    return PermissionUseTrigger(kind=kind, source=ObjectRef(card=source.id, object_id=state.rules.object_id(source.id), zone=source.zone),
                                controller=source.controller, name=source.name, index=index, definition=definition)


def stored_receipt(plan: Plan, ctx: dict[str, Any], descriptor: Any) -> PermissionUseTrigger | None:
    if descriptor is None:
        return None
    return PermissionUseTrigger(kind=descriptor['kind'],
        source=ObjectRef(card=ctx['source_card'], object_id=ctx['source_object']),
        controller=ctx['controller'], name=ctx['name'], index=descriptor['index'], definition=descriptor.get('definition'))


def committed(plan: Plan, receipt: PermissionUseTrigger, card_id: str, verb: str) -> None:
    from app.rules import stack_interaction, triggers

    if receipt.controller not in plan.live() or (receipt.kind == 'owner_loses_mv' and verb != 'cast'):
        return
    card=plan.state.cards[card_id]
    native_definition = None
    if receipt.kind == 'native':
        from app.rules import selectors

        native_definition = copy.deepcopy(receipt.definition or {})
        only = native_definition.pop('object_filter', None)
        if only is not None and not selectors.matches(plan, selectors.from_key(only), card, plan.ch(card), receipt.controller, receipt.source.card):
            return
        player, amount = plan.actor, 0
        effects = native_definition.get('effects') or []
    elif receipt.kind == 'create_food69':
        from app.rules import scripts

        player, amount = receipt.controller, 0
        parsed = scripts.parse_effects('Create a Food token.')
        if parsed is None:
            raise ValueError('Food token effect must be natively supported')
        effects = parsed[0]
    elif receipt.kind == 'replenish_top':
        player,amount=plan.actor,0
        effects=[{'do':'exile_top','player':'player:'+player,'n':1,'link':True,'as':'permission_refill'}]
    else:
        if card.zone != 'stack':
            raise ValueError('A cast-use receipt requires the actual stack spell')
        player=card.owner
        amount=stack_interaction.mana_value(card,plan.ch(card))
        effects=[{'do':'lose_life','who':'player:'+player,'n':amount}]
    triggers._add(plan,controller=receipt.controller,source_card=receipt.source.card,
        source_object=receipt.source.object_id,name=receipt.name,index=receipt.index,
        definition={**(native_definition or {}),'kind':'triggered','trigger':'reflexive','effects':effects},
        event=TriggerEvent(kind='reflexive',players=[player],actor=plan.actor,amount=amount,
                           objects=[ObjectRef(card=card.id,object_id=plan.oid(card),zone=card.zone)]))
