"""Native upkeep/cast taxes retain their original payer and affected object."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

AURAS = {
    "At the beginning of the upkeep of enchanted land's controller, destroy that land unless that player pays {1} or 1 life.": 'erosion',
    "At the beginning of the upkeep of enchanted creature's controller, that player sacrifices that creature unless they pay {2}.": 'slow',
    "At the beginning of the upkeep of enchanted permanent's controller, that player sacrifices it unless they pay {X}, where X is its mana value.": 'tithe',
}
HEX = 'At the beginning of your upkeep, for each player, ~ deals 1 damage to that player unless they pay {B} or {3}.'
DRACO = 'At the beginning of your upkeep, sacrifice ~ unless you pay {10}. This cost is reduced by {2} for each basic land type among lands you control.'
WIZARD = "{1}{B}: Counter target black spell unless that spell's controller pays {B} or {3}."
BIND = 'tax79_paid'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts, values

    text = scripts.self_text(ability.text, ch.name)
    unpaid = {'do': 'only_if', 'cond': {'succeeded': BIND, 'negate': True}, 'skip': 1}
    if (mode := AURAS.get(text)) is not None:
        header = text.split(', ', 1)[0]
        native = scripts.define(replace(ability, text=header + ', that player sacrifices that creature.'), ch)
        assert native is not None
        pay: dict[str, Any] = {'do': 'optional_payment', 'who': 'event_player', 'cost': '{2}', 'bind': BIND}
        if mode == 'erosion':
            pay.update(cost='{1}', alts=['{1}', 'Pay 1 life'])
        elif mode == 'tithe':
            pay.update(cost='{0}', per='{1}', n={'mana_value': 'event'})
        action = {'do': 'destroy', 'who': 'event'} if mode == 'erosion' else native['effects'][0]
        return {**native, 'effects': [{'do': 'tax_event_known79', 'mode': mode}, pay, unpaid, action]}
    if text == DRACO:
        native = scripts.define(replace(ability, text='At the beginning of your upkeep, sacrifice ~ unless you pay {10}.'), ch)
        domain = values.parse_count('the number of basic land types among lands you control')
        assert native is not None and domain is not None
        return {**native, 'effects': [
            {'do': 'optional_payment', 'who': 'you', 'cost': '{0}', 'per': '{1}',
             'n': {'minus': [10, {'times': [2, domain]}]}, 'bind': BIND}, unpaid,
            {'do': 'sacrifice', 'who': 'self'}]}
    if text == HEX:
        native = scripts.define(replace(ability, text='At the beginning of your upkeep, each player loses 1 life.'), ch)
        assert native is not None
        return {**native, 'effects': [{'do': 'hex_offers79'}]}
    if text == WIZARD:
        native = scripts.define(replace(ability, text='{1}{B}: Counter target black spell unless its controller pays {3}.'), ch)
        assert native is not None
        return {**native, 'effects': [
            {'do': 'optional_payment', 'who': 'target', 'cost': '{B}', 'alts': ['{B}', '{3}'], 'bind': BIND},
            unpaid, {'do': 'counter', 'who': 'target'}]}
    return None


def require_event(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context
    from app.rules.plan import decide

    refs = context._object_refs(ctx, context.EVENT)
    players = (ctx.get('event') or {}).get('players') or []
    if len(refs) == 1 and len(players) == 1:
        if players[0] not in plan.live():
            ctx['next'] = len(ctx['effects'])
            return True
        if e['mode'] != 'tithe' or context.info(plan, ctx, context.EVENT) is not None:
            return True
    ctx['next'] = len(ctx['effects'])
    decide(plan, player=ctx['controller'], kind='manual_resolution',
           prompt=f"{ctx.get('name') or 'The ability'}: this save lacks the original affected object or payer. Resolve this tax manually, then press Done.",
           options=[DecisionOption(id='done', label='Done')], resume={'step': 'tax_event_known79', 'ctx': ctx})
    return False


def legacy_done(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, d.resume['ctx'])


def hex_offers(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    slots = [(p, f'hex79:{p}:{ctx["next"]}') for p in plan.apnap()]
    at = ctx['next']
    ctx['effects'][at:at] = [
        *[{'do': 'optional_payment', 'who': 'player:' + player, 'cost': '{B}', 'alts': ['{B}', '{3}'], 'bind': binding}
          for player, binding in slots], {'do': 'hex_damage79', 'slots': slots}]
    return True


def hex_damage(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    unpaid = [p for p, binding in e['slots'] if p in plan.live() and not context.succeeded(ctx, binding)]
    at = ctx['next']
    ctx['effects'][at:at] = [{'do': 'damage', 'who': 'player:' + p, 'n': 1,
                            **({'with_next': True} if i < len(unpaid) - 1 else {})} for i, p in enumerate(unpaid)]
    return True


PRIMITIVES = {'tax_event_known79': require_event, 'hex_offers79': hex_offers, 'hex_damage79': hex_damage}
RESUME = {'tax_event_known79': legacy_done}
