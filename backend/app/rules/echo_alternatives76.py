"""Exact repeatable echo alternative delegates original costs to native settlement."""
from __future__ import annotations

from typing import Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules.plan import decide


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if scripts.self_text(ability.text, ch.name) == "When ~'s echo cost is paid, each opponent may draw up to three cards.":
        return {'kind': 'triggered', 'trigger': 'event', 'cond': {'event': 'echo_paid76', 'subject': 'self'},
                'optional': False, 'target': None, 'effects': [{'do': 'echo_draws76'}]}
    if ability.text == 'You may pay {0} rather than pay the echo cost for permanents you control.':
        return {'kind': 'static', 'static': 'echo_alternative76', 'effects': []}
    return None


def available(plan: Any, payer: str) -> bool:
    from app.rules import permissions

    return any(src.controller == payer for src, _, _ in permissions._table_statics(plan.state, plan.info, {'echo_alternative76'}))


def source(plan: Any, ctx: dict[str, Any]) -> Any:
    from app.rules import effects

    return next((plan.state.cards[c] for c in effects._cards(plan, ctx, 'self')), None)


def insert(ctx: dict[str, Any], original: list[dict[str, Any]]) -> None:
    i = ctx['next']
    ctx['effects'] = ctx['effects'][:i] + original + ctx['effects'][i:]


def payment(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    card = source(plan, ctx)
    if card is None or card.controller != ctx['controller'] or not available(plan, ctx['controller']):
        insert(ctx, e['original'])
        return True
    decide(plan, player=ctx['controller'], kind='choose_one', prompt=f"{ctx.get('name', '')}: choose its echo payment",
           options=[DecisionOption(id='original', label='Use its printed echo cost'),
                    DecisionOption(id='zero', label='Pay {0} instead'),
                    DecisionOption(id='sacrifice', label=f'Sacrifice {card.name}')],
           min_choices=1, max_choices=1,
           resume={'step': 'echo_alternative76', 'ctx': ctx, 'original': e['original']}, source=card)
    return False


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import casting, effects, mana

    ctx = d.resume['ctx']
    card = source(plan, ctx)
    if chosen[0] == 'zero':
        if card is None or card.controller != d.player or not available(plan, d.player):
            raise ActionError('The alternative echo cost is no longer available')
        note_paid(plan, ctx, {})
        casting.pay_from_pool_then(plan, d.player, mana.parse_cost('{0}'), 'paid alternative echo {0}',
                                   then={'do': 'continue', 'ctx': ctx})
        return
    if chosen[0] == 'original':
        insert(ctx, d.resume['original'])
    else:
        insert(ctx, [{'do': 'sacrifice', 'who': 'self'}])
    effects.continue_effects(plan, ctx)


def note_paid(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import emit

    cid, oid = ctx.get('source_card'), ctx.get('source_object')
    if cid and oid:
        emit(plan.state, 'designation', counter='echo_paid76', card=cid, object_id=oid, player=ctx['controller'])
    return True


def draws(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    state = ctx.setdefault('echo_draws76', {'players': [p for p in plan.apnap() if p != ctx['controller']],
                                         'counts': {}, 'at': 0})
    while state['at'] < len(state['players']):
        player = state['players'][state['at']]
        if player not in plan.live():
            state['at'] += 1
            continue
        decide(plan, player=player, kind='choose_one', prompt=f"{ctx.get('name', '')}: draw how many cards?",
               options=[DecisionOption(id=str(n), label=f'Draw {n}') for n in range(4)],
               min_choices=1, max_choices=1,
               resume={'step': 'echo_draw_count76', 'ctx': ctx, 'player': player,
                       'rest': state['players'][state['at'] + 1:], 'picked': dict(state['counts'])})
        return False
    # CR101.4 choices precede actions; CR121.2c performs each player's complete draws in APNAP order.
    insert(ctx, [{'do': 'draw', 'who': f'player:{p}', 'n': state['counts'].get(p, 0)}
                 for p in state['players'] if p in plan.live()])
    return True


def resume_draw(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume['ctx']
    state = ctx['echo_draws76']
    if chosen and d.resume['player'] in plan.live():
        state['counts'][d.resume['player']] = int(chosen[0])
    state['at'] += 1
    if draws(plan, ctx, {}):
        effects.continue_effects(plan, ctx)
