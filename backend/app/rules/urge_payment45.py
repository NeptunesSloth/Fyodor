"""Urge to Feed accepted-tap set using native payment binding."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'urge_payment45'
BIND = '_urge_vampires45'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip() != ('Target creature gets -3/-3 until end of turn. You may tap any number of untapped Vampire '
                        'creatures you control. If you do, put a +1/+1 counter on each of those Vampires.'):
        return None
    from app.rules import scripts

    first = scripts.parse_effects('Target creature gets -3/-3 until end of turn.')
    assert first is not None
    return ([*first[0], {'do': STEP}], first[1], False)


def _available(plan: Plan, ctx: dict[str, Any], card: Any) -> bool:
    return (card.zone.endswith(':battlefield') and card.controller == ctx['controller']
            and plan.in_game(card) and not card.tapped and plan.ch(card).is_creature
            and 'Vampire' in plan.ch(card).subtypes)


def start(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context
    from app.rules.plan import decide

    refs = [ref for card in plan.state.cards.values() if _available(plan, ctx, card)
            and (ref := context.ref_of(plan, card.id)) is not None]
    if not refs:
        return True
    decide(plan, player=ctx['controller'], kind='choose_cards', prompt='Choose any number of untapped Vampires to tap',
           options=[DecisionOption(id=r.card, label=plan.state.cards[r.card].name or 'Vampire', card_id=r.card) for r in refs],
           min_choices=0, max_choices=len(refs),
           resume={'step': STEP, 'ctx': ctx, 'objects': [r.model_dump(mode='json') for r in refs]})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    raw = d.resume
    if len(set(chosen)) != len(chosen) or any(cid not in {o.id for o in d.options} for cid in chosen):
        raise ActionError('Choose distinct offered Vampires')
    ctx = raw['ctx']
    selected = [ObjectRef.model_validate(r) for r in raw['objects'] if r['card'] in chosen]
    cards = [context._same(plan, r) for r in selected]
    if not selected or any(c is None or not _available(plan, ctx, c) for c in cards):
        effects.continue_effects(plan, ctx)
        return
    # Freeze EACH OF THOSE original objects before the native tap/payment
    # operation. Native did-tap records acceptance before its event; the next
    # instruction never reconstructs recipients from post-event tapped status.
    context.bind_objects(plan, ctx, BIND, [r.card for r in selected])
    at = int(ctx['next'])
    ctx['effects'] = [*ctx['effects'][:at],
                      {'do': 'tap', 'who': 'ref:' + BIND, 'did': BIND + '_paid'},
                      {'do': 'only_if', 'cond': {'succeeded': BIND + '_paid'}, 'skip': 1},
                      {'do': 'add_counters', 'who': 'ref:' + BIND, 'kind': '+1/+1', 'n': 1},
                      *ctx['effects'][at:]]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {STEP: start}
RESUME = {STEP: resume}
