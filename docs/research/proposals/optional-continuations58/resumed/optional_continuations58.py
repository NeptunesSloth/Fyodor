"""Mid-resolution optional costs preserve native success receipts and reflexive target timing."""
from __future__ import annotations

from typing import Any


def payment_reflexive(parsed: tuple[list[dict[str, Any]], Any, bool]) -> bool:
    effects, target, optional = parsed
    if len(effects) != 2 or target is not None or optional:
        return False
    payment, child = effects
    return (payment.get('do') == 'optional_payment' and isinstance(payment.get('bind'), str)
            and child.get('do') == 'reflexive' and child.get('cond') == {'succeeded': payment['bind']})


def parse(body: str, it: str | None, event_player: bool) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    body = body.strip()
    text = body[:1].upper() + body[1:]
    if text == 'Mill a card and put a bloodstain counter on ~. Then sacrifice it if it has five or more bloodstain counters on it. When you do, return target creature card from your graveyard to your hand.':
        return scripts.parse_effects('Mill a card. Put a bloodstain counter on ~. If ~ has five or more bloodstain counters on it, sacrifice ~. When you do, return target creature card from your graveyard to your hand.', it, event_player=event_player)
    if text == 'Choose target creature an opponent controls. Tap it, then you may sacrifice an artifact or creature. If you do, put a stun counter on the chosen creature.':
        return scripts.parse_effects('Tap target creature an opponent controls. You may sacrifice an artifact or creature. If you do, put a stun counter on that creature.', it, event_player=event_player)
    if text in ('Return this card from your graveyard to the battlefield with a finality counter on ~. Then you may attach an Equipment you control to ~.', 'Return this card from your graveyard to the battlefield with a finality counter on him. Then you may attach an Equipment you control to him.'):
        returned = scripts.parse_effects('Return ~ from your graveyard to the battlefield with a finality counter on it.', it, event_player=event_player)
        if returned is not None and len(returned[0]) == 1:
            returned[0][0]['as'] = 'winter58'
            return [*returned[0], {'do': 'attach_choose', 'kinds': ['Equipment'], 'n': 1, 'who': 'ref:winter58', 'optional': True}], None, False
    recipes = {
        'Mill two cards. Then you may sacrifice ~. When you do, return another target permanent card from your graveyard to your hand.': (
            'Mill two cards.', 'You may sacrifice ~. When you do, return another target permanent card from your graveyard to your hand.'),
        'Draw a card. Then you may discard a nonland card. When you discard a card this way, ~ deals 3 damage to target creature or planeswalker.': (
            'Draw a card.', 'You may discard a nonland card. When you discard a card this way, ~ deals 3 damage to target creature or planeswalker.'),
    }
    recipe = recipes.get(text)
    if recipe is None:
        return None
    first = scripts.parse_effects(recipe[0], it, event_player=event_player)
    tail = scripts.parse_effects(recipe[1], it, event_player=event_player)
    if first is None or tail is None or first[1] is not None or first[2] or tail[1] is not None:
        return None
    if not tail[2] and not payment_reflexive(tail):
        return None
    if text.startswith('Mill two cards.'):
        tail[0][-1]['exclude_paid_successor58'] = True
    return [*first[0], *([{'do': 'may_rest'}] if tail[2] else []), *tail[0]], None, False


def reflexive_ability(plan: Any, ctx: dict[str, Any], effect: dict[str, Any]) -> dict[str, Any]:
    """Freeze actual sacrificed successors into the later target selector (400.7j)."""
    from copy import deepcopy
    from dataclasses import replace

    from app.rules import context, selectors

    ability = effect['ability']
    if not effect.get('exclude_paid_successor58'):
        return ability
    receipt = context.refs(ctx).get(effect['cond']['succeeded']) or {}
    successors = receipt.get('moved') or []
    found = [ref['object_id'] for ref in successors if ref.get('object_id')]
    ability = deepcopy(ability)
    spec = ability.get('target') or {}
    key = spec.get('what', '')
    if not key.startswith(selectors.PREFIX):
        return ability
    selected = selectors.from_key(key)
    spec['what'] = replace(selected, other=False, extras=(*selected.extras, *(f'exclude_successor58:{oid}' for oid in found))).key()
    return ability
