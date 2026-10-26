"""Native copies and once watches based on immutable activation cost facts."""
from __future__ import annotations

import re
from typing import Any

NEXT_X = 'When you next cast a spell with {X} in its mana cost or activate an ability with {X} in its activation cost this turn, copy that spell or ability. You may choose new targets for the copy'


def activation_cond() -> dict[str, Any]:
    return {'event': 'activate', 'subject': 'player', 'player': 'you', 'nonmana': True, 'loyalty': False}


def definition(text: str) -> dict[str, Any] | None:
    from app.rules import events, scripts

    if text == 'Whenever you cast a permanent spell with a mana cost that contains {X}, double the value of X.':
        from app.rules import selectors

        return {'kind': 'triggered', 'trigger': 'event', 'optional': False, 'target': None,
                'cond': {'event': 'cast', 'subject': 'player', 'player': 'you',
                         'spell': selectors.Selector(zones=('stack',), types=('Artifact', 'Creature', 'Enchantment', 'Land', 'Planeswalker', 'Battle')).key(),
                         'cost_has_x': True}, 'effects': [{'do': 'double_event_x'}]}
    if text == ("Whenever you cast an instant or sorcery spell or activate an ability, if that spell's mana cost or "
                "that ability's activation cost contains {X}, copy that spell or ability. You may choose new targets for the copy."):
        from app.rules import selectors

        return {'kind': 'triggered', 'trigger': 'event', 'optional': False, 'target': None,
                'cond': {'event': 'either', 'subject': 'player', 'conds': [
                    {'event': 'cast', 'subject': 'player', 'player': 'you', 'cost_has_x': True,
                     'spell': selectors.Selector(zones=('stack',), types=('Instant', 'Sorcery')).key()},
                    {'event': 'activate', 'subject': 'player', 'player': 'you', 'activation_cost': {'has_x': True}}]},
                'effects': [{'do': 'copy_event_stack'}, {'do': 'copy_new_targets', 'optional': True}]}
    if text == "Whenever you activate an ability that isn't a mana ability, copy it. You may choose new targets for the copy.":  # (wave 110E) Rowan Kenrith's emblem; 603.2, 707.10
        return {'kind': 'triggered', 'trigger': 'event', 'cond': activation_cond(), 'optional': False, 'target': None,
                'effects': [{'do': 'copy_event_stack'}, {'do': 'copy_new_targets', 'optional': True}]}
    m = re.fullmatch(r"Whenever (?P<event>you activate an ability(?: of an artifact or creature)? that isn't a mana ability), if (?P<cost>one or more permanents were sacrificed to activate it|life was paid to activate it), (?P<body>.+)", text)
    if m is None:
        return None
    cond = events.parse_condition(m['event'])
    if cond is None:
        return None
    if m['cost'].startswith('one or more'):
        if m['body'] != 'you may copy that ability. You may choose new targets for the copy.':
            return None
        parsed = scripts.parse_effects('Copy that ability. You may choose new targets for the copy.')
        optional = True
        cond['activation_cost'] = {'sacrificed': True}
    else:
        if m['body'] != 'you may pay that much life again. If you do, copy that ability. You may choose new targets for the copy.':
            return None
        parsed = scripts.parse_effects('You may pay X life, where X is the amount of mana spent to cast this spell. If you do, copy that ability. You may choose new targets for the copy.')
        if parsed is not None:
            parsed[0][0]['life_x'] = {'activation_life': 'event'}
        optional = False
        cond['activation_cost'] = {'life_positive': True}
    if parsed is None:
        return None
    return {'kind': 'triggered', 'trigger': 'event', 'cond': cond, 'effects': parsed[0], 'optional': optional, 'target': None}


def watch(*, x: bool = False, exhaust: bool = False, mana: int | None = None) -> list[dict[str, Any]]:
    from app.rules import delayed

    cond = activation_cond()
    if exhaust:
        cond['word'] = 'exhaust'
    if mana is not None:
        cond['activation_cost'] = {'mana_at_least': mana}
    if x:
        cond['activation_cost'] = {'has_x': True}
        cond = {'event': 'either', 'subject': 'player', 'conds': [
            {'event': 'cast', 'subject': 'player', 'player': 'you', 'spell': 'sel:{"zones":["stack"]}', 'cost_has_x': True}, cond]}
    head = {'kind': 'watch', 'cond': cond, 'text': 'you next cast or activate a matching spell or ability'}
    out = delayed.wrap_when([{'do': 'copy_event_stack'}, {'do': 'copy_new_targets', 'optional': True}], head, this_turn=True)
    out[0]['once'] = True
    return out


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    t = body.strip().rstrip('.')
    if t == NEXT_X:
        return watch(x=True), None, False
    if t == "When you next activate an exhaust ability that isn't a mana ability this turn, copy it. You may choose new targets for the copy":
        return watch(exhaust=True), None, False
    if t == "When you next activate an ability that isn't a mana ability this turn by spending four or more mana to activate it, copy that ability. You may choose new targets for the copy":
        return watch(mana=4), None, False
    return None


def matches(need: dict[str, Any], facts: dict[str, Any] | None) -> bool:
    if facts is None:
        return False
    if need.get('sacrificed') and not facts.get('sacrificed'):
        return False
    if need.get('life_positive') and not (facts.get('life') is not None and facts['life'] > 0):
        return False
    if need.get('has_x') and not facts.get('has_x'):
        return False
    if 'has_tap' in need and facts.get('has_tap') is not need['has_tap']:
        return False
    return not (need.get('mana_at_least') is not None and (facts.get('mana') is None or sum(facts['mana'].values()) < need['mana_at_least']))


def copy_event_stack(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import copying

    who = 'event_ability' if (ctx.get('event') or {}).get('kind') == 'activate' else 'event_spell'
    return copying.copy_stack_object(plan, ctx, {**e, 'who': who})


def double_event_x(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """CR107.3: change the spell's current X, never its already-paid costs."""
    from app.rules import context

    for cid in context.objects(plan, ctx, context.EVENT):
        card = plan.state.cards[cid]
        entry = plan.rules.stack.get(cid)
        if card.zone != 'stack' or card.ability is not None:
            continue
        value = 2 * int(card.stack_info.x or 0) if card.stack_info is not None else 0
        if entry is not None:
            entry.x = value
        plan.do({'type': 'set_stack_info', 'card_id': cid, 'x': value})
    return True


PRIMITIVES = {'copy_event_stack': copy_event_stack, 'double_event_x': double_event_x}
