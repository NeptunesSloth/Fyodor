"""Bounded public mill selections keep return outcomes separate from optional payment."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_PUBLIC = ('graveyard', 'exile', 'battlefield', 'command', 'stack')
_CACHE = 'Mill four cards. You may put a permanent card from among the cards milled this way into your hand. If you control a Squirrel or returned a Squirrel card to your hand this way, create a Food token.'
_MIDNIGHT = 'Mill four cards, then you may return a permanent card from among them to your hand.'
_DUMMY = 'Mill a card. You may put a land card milled this way into your hand. You gain 2 life if a Lesson card is milled this way.'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts, selectors

    body = body.strip()
    if body not in (_CACHE, _MIDNIGHT, _DUMMY):
        return None
    types = ('Land',) if body == _DUMMY else ('Artifact', 'Battle', 'Creature', 'Enchantment', 'Land', 'Planeswalker')
    sel = selectors.Selector(card=True, zones=_PUBLIC, types=types)
    effects: list[dict[str, Any]] = [
        {'do': 'mill', 'who': 'you', 'n': 1 if body == _DUMMY else 4, 'as': 'milled60'},
        {'do': 'post_mill_pick60' if body == _CACHE else 'pick_looked', 'who': 'ref:milled60', 'public_mill59': True,
         'n': 1, 'sel': sel.key(), 'to': 'hand', 'optional': True},
    ]
    if body == _CACHE:
        food = scripts.parse_effects('Create a Food token.')
        if food is None or food[1] is not None or food[2]:
            return None
        effects.append({'do': 'cache_food60', 'effects': food[0]})
    elif body == _DUMMY:
        effects.insert(1, {'do': 'milled_lesson_flag60'})
        effects.extend([{'do': 'only_if', 'cond': {'flag': 'milled_lesson60'}, 'skip': 1},
                        {'do': 'gain_life', 'who': 'you', 'n': 2}])
    return effects, None, False


def choose_return(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    ctx['cache_return60'] = None
    done = effects.pick_looked(plan, ctx, e)
    if not done:
        d = plan.rules.decision
        assert d is not None and d.resume is not None and d.resume.get('step') == 'pick_looked'
        d.resume['step'] = 'post_mill_pick60'
    return done


def resume_return(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume['ctx'], d.resume['e']
    selected = [cid for cid in chosen if cid in effects._looked(plan, ctx)[1]]
    if selected:
        cid = selected[0]
        # Capture the chosen public object's characteristics BEFORE its hand movement.
        # A graveyard-only type grant must not be re-read from the new card in hand.
        ctx['cache_return60'] = {'card': cid, 'oid': plan.oid(plan.state.cards[cid]),
                                 'squirrel': 'Squirrel' in plan.ch(plan.state.cards[cid]).subtypes}
    _finish_selected(plan, ctx, e, selected)


def _finish_selected(plan: Plan, ctx: Context, e: dict[str, Any], selected: list[str]) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules import effects, replacements
    from app.rules.plan import decide

    # The actual-hand outcome must wait for 903.9b. Ordinary post-move prompts
    # cannot be read as a completed return while the owner can still replace it.
    if selected:
        card = plan.state.cards[selected[0]]
        key = f'{plan.oid(card)}>hand'
        if key not in plan.rules.answers_903_9b and replacements._commander_instead(plan, card, 'hand') is None:
            decide(plan, player=card.owner, kind='confirm',
                   prompt=f'{card.name} would enter your hand: put it into the command zone instead? (903.9b)',
                   options=[DecisionOption(id='yes', label='Command zone'), DecisionOption(id='no', label='Into your hand')],
                   resume={'step': 'post_mill_command60', 'ctx': ctx, 'e': e, 'selected': selected, 'key': key},
                   memory_key=f'commander_zone:{card.commander_key}', memory_context='hand')
            return
    if effects._picked(plan, ctx, e, selected):
        effects.continue_effects(plan, ctx)


def resume_command(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    selected = [cid for cid in r['selected'] if cid in effects._looked(plan, r['ctx'])[1]]
    if not selected:
        r['ctx']['cache_return60'] = None
    else:
        plan.rules.answers_903_9b[r['key']] = chosen[0]
    _finish_selected(plan, r['ctx'], r['e'], selected)


def food_if_squirrel(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    controlled = any(c.zone.endswith(':battlefield') and c.controller == ctx['controller']
                     and 'Squirrel' in plan.ch(c).subtypes for c in plan.state.cards.values())
    choice = ctx.get('cache_return60') or {}
    card = plan.state.cards.get(choice.get('card', ''))
    # This continuation immediately follows the native move, with no priority window.
    # Unlike an optional-payment flag, "returned ... to your hand" requires the hand outcome.
    returned = bool(choice.get('squirrel') and card is not None and card.zone == ctx['controller'] + ':hand'
                    and plan.oid(card) != choice.get('oid'))
    if controlled or returned:
        ctx['effects'][ctx['next']:ctx['next']] = e['effects']
    return True


def lesson_flag(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context

    # Freeze public information before the optional selection moves any cards.
    # 701.17c does not permit inferring an unseen hidden replacement's type.
    found = any(plan.state.cards[cid].zone.rsplit(':', 1)[-1] in _PUBLIC and not plan.state.cards[cid].face_down
                and 'Lesson' in plan.ch(plan.state.cards[cid]).subtypes for cid in context.objects(plan, ctx, 'milled60'))
    context.bind_flag(ctx, 'milled_lesson60', found)
    return True


PRIMITIVES = {'post_mill_pick60': choose_return, 'cache_food60': food_if_squirrel, 'milled_lesson_flag60': lesson_flag}
RESUME = {'post_mill_pick60': resume_return, 'post_mill_command60': resume_command}
