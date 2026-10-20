"""CR 701.34 / 702.26: choices among permanents that received proliferated counters."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'choose_proliferated_permanents'
_RECEIVED = 'proliferate_counter_receipts'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip() != ('Proliferate, then choose any number of permanents you control that had a counter put on them this way. '
                        'Those permanents phase out.'):
        return None
    return ([{'do': 'mark_proliferate_counters'}, {'do': 'proliferate'},
             {'do': STEP, 'as': 'proliferated_choices'},
             {'do': 'phase_out', 'who': 'ref:proliferated_choices'}], None, False)


def mark(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    # A separate instruction encloses repeated proliferates from a replacement.
    ctx[_RECEIVED] = []
    return True


def continuation(ctx: dict[str, Any], batch: int) -> dict[str, Any]:
    return ({'do': 'record_proliferate_counters', 'ctx': ctx, 'after_batch': batch}
            if _RECEIVED in ctx else {'do': 'continue', 'ctx': ctx})


def record(plan: Plan, then: dict[str, Any]) -> None:
    from app.rules import effects

    ctx = then['ctx']
    received = set(ctx.get(_RECEIVED) or [])
    received.update(ev.object_id for ev in plan.rules.events
                    if ev.kind == 'counters' and not ev.manual and ev.amount > 0 and ev.object_id and ev.batch > then['after_batch'])
    scope = ctx
    while _RECEIVED in scope:
        scope[_RECEIVED] = sorted(set(scope.get(_RECEIVED) or []) | received)
        parent = scope.get('body_done') or {}
        if parent.get('do') != 'continue' or not isinstance(parent.get('ctx'), dict):
            break
        scope = parent['ctx']  # replacements execute in copied contexts, then resume their parent
    effects.continue_effects(plan, ctx)


def pool(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    received = set(ctx.get(_RECEIVED) or [])
    return [c.id for c in plan.state.cards.values()
            if c.zone.endswith(':battlefield') and plan.in_game(c) and c.controller == ctx['controller']
            and plan.oid(c) in received]


def choose(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    options = pool(plan, ctx)
    if not options:
        effects._remember(plan, ctx, e, [])
        return True
    decide(plan, player=ctx['controller'], kind='choose_cards',
           prompt='Choose any number of your permanents that received counters this way to phase out',
           options=[DecisionOption(id=cid, label=plan.state.cards[cid].name or 'Permanent', card_id=cid) for cid in options],
           min_choices=0, max_choices=len(options), resume={'step': STEP, 'ctx': ctx, 'e': e})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume['ctx'], d.resume['e']
    if len(set(chosen)) != len(chosen) or not set(chosen) <= set(pool(plan, ctx)):
        raise ActionError('Choose only your permanents that received counters this way')
    effects._remember(plan, ctx, e, chosen)
    effects.continue_effects(plan, ctx)


PRIMITIVES = {'mark_proliferate_counters': mark, STEP: choose}
