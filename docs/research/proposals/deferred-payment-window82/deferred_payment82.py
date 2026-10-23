"""Once-only early-payment special actions suppress their exact delayed triggers."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, DeferredPaymentWindow
from app.rules import mana as M
from app.rules import payment_continuations as pc
from app.rules.plan import Plan, require_no_decision, require_priority

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText

COBRA = 'Whenever ~ deals damage to a player, that player gets a poison counter. The player gets another poison counter at the beginning of their next upkeep unless they pay {2} before that step.'
GLASS = 'Whenever ~ deals combat damage to a player, that player loses 2 life at the beginning of their next draw step unless they pay {2} before that step.'
NAFS = 'Whenever ~ deals damage to a player, that player loses 1 life at the beginning of their next draw step unless they pay {1} before that draw step.'
FIRE = '~ deals 3 damage to target player or planeswalker. It deals an additional 3 damage to that player or planeswalker at the beginning of your next upkeep step unless that player or that planeswalker\'s controller pays {U} before that step.'


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text in (COBRA, GLASS, NAFS):
        header = text.split(', ', 1)[0]
        native = scripts.define(replace(ability, text=header + ', that player loses 1 life.'), ch)
        assert native is not None
        effect = {'do': 'player_counter', 'who': 'event_player', 'counter': 'poison', 'n': 1} if text == COBRA else {'do': 'lose_life', 'who': 'event_player', 'n': 2 if text == GLASS else 1}
        initial = [effect] if text == COBRA else []
        return {**native, 'effects': [*initial, {'do': 'deferred_window82', 'who': 'event_player',
            'cost': '{1}' if text == NAFS else '{2}', 'step': 'upkeep' if text == COBRA else 'draw', 'effects': [effect]}]}
    if text == FIRE:
        native = scripts.define(replace(ability, text='~ deals 3 damage to target player or planeswalker.'), ch)
        assert native is not None
        return {**native, 'effects': [{'do': 'deferred_prepare82', 'as': 'deferred_recipient82'}, *native['effects'],
            {'do': 'deferred_window82', 'who': 'prepared', 'cost': '{U}', 'step': 'upkeep', 'your_step': True,
             'effects': [{'do': 'damage', 'who': 'ref:deferred_recipient82', 'n': 3}]}]}
    return None


def active(state: GameState, player: str) -> list[DeferredPaymentWindow]:
    r = state.rules
    if r is None:
        return []
    ids = {t.id for t in r.delayed}
    return [w for w in r.deferred_payments if w.payer == player and w.delayed in ids]


def prepare(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    ctx['deferred_payer82'] = effects._players(plan, ctx, 'target_player_or_controller')
    objects = effects._cards(plan, ctx, 'target')
    if objects:
        context.bind_objects(plan, ctx, e['as'], objects)
    else:
        context.bind_players(ctx, e['as'], ctx['deferred_payer82'])
    return True


def create(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import delayed, effects

    players = ctx.get('deferred_payer82', []) if e['who'] == 'prepared' else effects._players(plan, ctx, e['who'])
    if len(players) != 1:
        raw = (ctx.get('event') or {}).get('players') or []
        if raw and all(p not in plan.live() for p in raw):
            return True
        from app.rules.plan import decide

        decide(plan, player=ctx['controller'], kind='manual_resolution',
               prompt=f"{ctx.get('name') or 'Delayed ability'}: this save lacks the original affected player. Record and resolve this delayed effect manually, then press Done.",
               options=[DecisionOption(id='done', label='Done')], resume={'step': 'deferred_unknown82', 'ctx': ctx})
        return False
    if players[0] not in plan.live():
        return True
    payer = players[0]
    when = {'kind': 'step', 'step': e['step'], 'whose': 'you' if e.get('your_step') else 'payer', 'player': payer}
    local = {**ctx, 'effects': e['effects'], 'next': 0}
    delayed.create(plan, local, {'n': len(e['effects']), 'when': when})
    trigger = plan.rules.delayed[-1]
    plan.rules.deferred_payments.append(DeferredPaymentWindow(id=trigger.id, payer=payer, cost=e['cost'],
        delayed=trigger.id, name=ctx.get('name') or 'Delayed ability', source_card=ctx.get('source_card')))
    return True


def pay(plan: Plan, a: A.PayDeferred) -> None:
    from app.rules.casting import Purpose, pay_then, payment_step

    require_no_decision(plan)
    require_priority(plan)
    row = next((w for w in active(plan.state, plan.actor) if w.id == a.window_id), None)
    if row is None:
        raise ActionError('That early-payment window is not available to you')
    cost = M.parse_cost(row.cost)
    if payment_step(plan, a, cost, f'preventing {row.name}', purpose=Purpose()):
        return
    tail = pc.continuation(plan, 'deferred_paid82', Paid(row.id, row.payer))
    pay_then(plan, plan.actor, cost, f'paid {row.cost} to prevent {row.name}', sources=a.sources, purpose=Purpose(), then=tail)


@dataclass
class Paid:
    window: str
    payer: str


def paid(plan: Plan, frame: Paid, payment: M.Payment | None) -> None:
    row = next((w for w in active(plan.state, frame.payer) if w.id == frame.window), None)
    if row is None or frame.payer != plan.actor:
        raise ActionError('That early-payment window expired')
    plan.rules.delayed = [t for t in plan.rules.delayed if t.id != row.delayed]
    plan.rules.deferred_payments = [w for w in plan.rules.deferred_payments if w.id != row.id]
    plan.rules.passed = []
    plan.note(f'{plan.name(frame.payer)} prevents the delayed ability of {row.name}')


pc.register('deferred_paid82', Paid, paid)
PRIMITIVES = {'deferred_prepare82': prepare, 'deferred_window82': create}


def unknown_done(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, d.resume['ctx'])


RESUME = {'deferred_unknown82': unknown_done}
