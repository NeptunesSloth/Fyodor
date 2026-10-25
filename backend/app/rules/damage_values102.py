"""Exact damage values composed with native targets, receipts and replacements."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import per_opponent, scripts, selectors, values

    text = body.strip()
    if text == '~ deals X damage divided evenly, rounded down, among any number of targets.':
        return [{'do': 'fireball_even102'}], [{'what': 'any', 'min': 0, 'max': 250}], False
    if text == 'For each opponent, choose up to one target creature that player controls. ~ deals damage equal to the greatest power among creatures you control to each of the chosen creatures.':
        key = selectors.Selector(types=('Creature',), controller='opponent').key()
        amount = values.parse_count('the greatest power among creatures you control')
        assert amount is not None
        return [{'do': 'damage', 'who': 'target:0', 'n': amount, 'with_next': True}], [
            {'what': key, 'min': 0, 'max': 1, per_opponent.FLAG: True}], False
    if text == 'Target creature you control deals damage equal to its power to target creature or planeswalker. If a Dragon was beheld, surveil 2.':
        bite = scripts.parse_effects('Target creature you control deals damage equal to its power to target creature or planeswalker.')
        tail = scripts.parse_effects('If a dragon was beheld, surveil 2.')
        assert bite is not None and tail is not None
        return [*bite[0], *tail[0]], bite[1], False
    if text == 'Tap target creature that player controls. That creature deals damage equal to its power to the player. Prevent all combat damage that would be dealt to and dealt by the creature this turn.':
        tap = scripts.parse_effects('Tap target creature. It deals damage equal to its power to its controller.')
        prevent = scripts.parse_effects('Prevent all combat damage that would be dealt to and dealt by target creature this turn.')
        assert tap is not None and prevent is not None
        key = selectors.Selector(types=('Creature',), controller='active').key()
        tapped = [*tap[0]]
        tapped[1] = {**tapped[1], 'who': 'ref:active102'}
        return [{'do': 'bind_active102', 'as': 'active102'}, *tapped, *[{**e, 'who': 'ref:e0'} for e in prevent[0]]], key, False
    if text == "Return target card from your graveyard to your hand. If you return a nonland card to your hand this way, ~ deals damage equal to that card's mana value to any target.":
        returned = scripts.parse_effects('Return target card from your graveyard to your hand.')
        assert returned is not None
        nonland = selectors.Selector(card=True, zones=('hand',), not_types=('Land',)).key()
        return [{**returned[0][0], 'who': 'target:0', 'as': 'returned102'},
                {'do': 'only_if', 'cond': {'value': {'ref_count': 'returned102', 'this_way': 'returned', 'of': nonland, 'public': True}, 'op': '>=', 'n': 1}, 'skip': 1},
                {'do': 'damage', 'who': 'target:1', 'n': {'mana_value': 'ref:returned102'}}], [
                    {'what': returned[1], 'min': 1, 'max': 1}, {'what': 'any', 'min': 1, 'max': 1}], False
    return None


def even(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, values

    count = len(effects._cards(plan, ctx, 'target:0')) + len(effects._players(plan, ctx, 'target:0'))
    amount = values.evaluate(plan, ctx, {'x': True}) // count if count else 0
    return effects.damage(plan, ctx, {'do': 'damage', 'who': 'target:0', 'n': amount})


def bind_active(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context

    context.bind_players(ctx, e['as'], [plan.active])
    return True


PRIMITIVES = {'fireball_even102': even, 'bind_active102': bind_active}
