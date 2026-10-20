"""Life derived from actual damage, capped by each actual recipient's stated statistics."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from app.rules.plan import Plan


class Recipient(TypedDict):
    target: str
    object_id: str | None
    damage: int
    creature: bool
    loyalty: int | None
    life: int | None


_BODY = re.compile(r"^~ deals (?P<n>X|\d+) damage to any target\. You gain life equal to the damage dealt, but not more "
                   r"(?P<black>than the amount of \{B\} spent on X, |life than )the player's life total before the damage was dealt, "
                   r"the planeswalker's loyalty before the damage was dealt, or the creature's toughness\.$")


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    m = _BODY.fullmatch(body)
    if m is None:
        return None
    binding = 'damage_life_caps'
    return ([{'do':'damage', 'who':'target', 'n': {'x':1} if m['n'] == 'X' else int(m['n']), 'bind_life_caps':binding},
             {'do':'gain_capped_damage', 'life_caps':binding, 'black_on_x':m['black'].startswith('than the amount')}], 'any', False)


def capture(plan: Plan, ctx: dict[str, Any], name: str, events: list[dict[str, Any]]) -> None:
    from app.rules import context

    recipients: dict[tuple[str, str | None], Recipient] = {}
    for event in events:
        amount = max(0, int(event['amount']))
        if not amount:
            continue
        target = event['target']
        card = plan.state.cards.get(target)
        oid = plan.oid(card) if card is not None else None
        key = (target, oid)
        if key not in recipients:
            ch = plan.ch(card) if card is not None else None
            recipients[key] = {'target':target, 'object_id':oid, 'damage':0,
                               'creature':bool(ch is not None and ch.is_creature),
                               'loyalty':card.counters.get('loyalty', 0) if card is not None and ch is not None and 'Planeswalker' in ch.types else None,
                               'life':plan.state.players[target].life if target in plan.state.players else None}
        recipients[key]['damage'] += amount
    context.refs(ctx)[name] = {'kind':'damage_life_caps', 'recipients':list(recipients.values())}


def gain(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects, replace

    binding = context.refs(ctx).get(e['life_caps']) or {}
    amount = 0
    for recipient in binding.get('recipients') or []:
        caps = [recipient['damage']]
        caps += [recipient[k] for k in ('life', 'loyalty') if recipient[k] is not None]
        if recipient['creature']:
            card = plan.state.cards.get(recipient['target'])
            # Damage and its following gain occur without an intervening state-based check.
            # A toughness changed by wither/infect is read now, not before the damage.
            pt = plan.ch(card).pt if card is not None and plan.oid(card) == recipient['object_id'] else None
            caps.append(pt[1] if pt is not None else 0)
        amount += max(0, min(caps))
    if e.get('black_on_x'):
        payment = plan.rules.payments.get(ctx.get('source_object') or '')
        announced_x = payment.x if payment is not None else effects._amount(plan, ctx, {'x':1})
        amount = min(amount, max(0, int(announced_x or 0)))
        if amount > 0 and (payment is None or payment.x_black_spent is None):
            from app.game.rules_state import DecisionOption
            from app.rules.plan import decide

            decide(plan, player=ctx['controller'], kind='manual_resolution',
                   prompt=f"This older save did not record black mana spent on X. Gain the appropriate life by hand (at most {amount}), then press Done.",
                   options=[DecisionOption(id='done', label='Done')],
                   resume={'step':'capped_damage_legacy_done', 'ctx':ctx})
            return False
        amount = min(amount, payment.x_black_spent or 0) if payment is not None else 0
    return amount <= 0 or replace.gain_life(plan, [(ctx['controller'], amount)], actor=ctx['controller'], then=effects._then(ctx, e), ctx=ctx)


PRIMITIVES = {'gain_capped_damage':gain}


def legacy_done(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, decision.resume['ctx'])


RESUME = {'capped_damage_legacy_done':legacy_done}
