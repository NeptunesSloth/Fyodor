"""Staged exact text-change instructions; unhooked and not production admitted."""
from __future__ import annotations

import re
from typing import Any

from app.game.errors import ActionError
from app.rules import context, effects, layers, selectors
from app.rules.creature_types import CREATURE_TYPES
from app.rules.plan import Plan

_PATTERN = re.compile(r'Change the text of target (?P<who>spell or permanent|permanent) by replacing all instances of '
                      r'(?P<category>one color word|one basic land type|one creature type) with another'
                      r'(?P<other> or one basic land type with another)?(?P<until> until end of turn)?\.'
                      r"(?P<wall> The new creature type can't be Wall\.)?")
COLORS = ('white', 'blue', 'black', 'red', 'green')
LANDS = ('Plains', 'Island', 'Swamp', 'Mountain', 'Forest')


def category(word: str) -> str | None:
    return 'color' if word in COLORS else 'basic_land' if word in LANDS else 'creature' if word in CREATURE_TYPES else None


def parse(body: str) -> tuple[list[dict[str, Any]], str, bool] | None:
    if (m := _PATTERN.fullmatch(body)) is None:
        return None
    cats = ['color'] if m['category'] == 'one color word' else ['basic_land'] if m['category'] == 'one basic land type' else ['creature']
    if m['other']:
        if cats != ['color']:
            return None
        cats.append('basic_land')
    if m['wall'] and cats != ['creature']:
        return None
    permanent = selectors.Selector()
    target = permanent.key() if m['who'] == 'permanent' else selectors.Selector(
        zones=('battlefield', 'stack'), either=(permanent.key(), selectors.Selector(zones=('stack',)).key())).key()
    return ([{'do': 'text71_old', 'categories': cats, 'duration': 'end_of_turn' if m['until'] else 'permanent',
              'not_wall': bool(m['wall'])}], target, False)


def old_word(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    words = [*COLORS, *LANDS, *sorted(CREATURE_TYPES)]
    options = [w for w in words if category(w) in effect['categories']]
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do': 'choose_value', 'what': 'text word71', 'who': 'you', 'as': 'text71_old', 'options': options},
        {**effect, 'do': 'text71_new'}]
    return True


def new_word(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    old = context.refs(ctx).get('text71_old', {}).get('value')
    cat = category(old) if isinstance(old, str) else None
    if cat not in effect['categories']:
        raise ActionError('The original text word is not valid')
    words = COLORS if cat == 'color' else LANDS if cat == 'basic_land' else tuple(sorted(CREATURE_TYPES))
    ctx['effects'][ctx['next']:ctx['next']] = [
        {'do': 'choose_value', 'what': 'text word71', 'who': 'you', 'as': 'text71_new',
         'options': [w for w in words if w != old and not (effect['not_wall'] and w == 'Wall')]},
        {**effect, 'do': 'text71_apply', 'category': cat, 'old': old}]
    return True


def apply_word(plan: Plan, ctx: dict[str, Any], effect: dict[str, Any]) -> bool:
    from app.game.rules_state import TextChange71

    new = context.refs(ctx).get('text71_new', {}).get('value')
    old = effect['old']
    if not isinstance(new, str) or category(old) != effect['category'] or category(new) != effect['category'] or old == new \
            or (effect['not_wall'] and new == 'Wall'):
        raise ActionError('The replacement text word is not valid')
    cards = effects._cards(plan, ctx, 'target')
    if cards:
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer='3', source=ctx.get('source_object'),
                          controller=ctx['controller'], duration=effect['duration'],
                          text_change71=TextChange71(category=effect['category'], old=old, new=new),
                          label=f'Text: {old} becomes {new}')
    return True


PRIMITIVES = {'text71_old': old_word, 'text71_new': new_word, 'text71_apply': apply_word}
