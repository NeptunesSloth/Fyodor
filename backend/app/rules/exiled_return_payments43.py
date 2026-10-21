"""Native resolution return payments and exact delayed as-entry returns."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'exiled_return_payment_preflight43'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip()
    text = text[:1].upper() + text[1:]
    if text != ("Exile another target creature you control. You may return that card to the battlefield under its owner's control. "
                "If you don't, at the beginning of the next end step, return that card to the battlefield under its owner's control "
                'with a vigilance counter and a lifelink counter on it.'):
        return None
    from app.rules import scripts

    exile = scripts.parse_effects('Exile another target creature you control.')
    assert exile is not None and len(exile[0]) == 1
    binding, paid = '_return_exiled43', '_return_paid43'
    return ([{**exile[0][0], 'as': binding}, {'do': STEP, 'ref_count': binding, 'bind': paid},
             {'do': 'may_rest', 'skip': 1, 'label': 'Return that card to the battlefield now'},
             {'do': 'return_card', 'who': 'ref:' + binding, 'to': 'battlefield', 'did': paid},
             {'do': 'only_if', 'cond': {'not': {'succeeded': paid}}, 'skip': 2},
             {'do': 'delayed', 'when': {'kind': 'step', 'step': 'end', 'whose': 'next'}, 'n': 1},
             {'do': 'deferred:return_card', 'who': 'ref:' + binding, 'to': 'battlefield',
              'conditional_counters': [{'kind': 'vigilance', 'n': 1}, {'kind': 'lifelink', 'n': 1}]}], exile[1], False)


def preflight(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import attachments, context, effects, prohibitions

    context.bind_payment(ctx, e['bind'], False)
    cards = effects._cards(plan, ctx, 'ref:' + e['ref_count'])
    card = plan.state.cards[cards[0]] if len(cards) == 1 else None
    possible = card is not None and card.zone.endswith(':exile') and not card.is_token and card.owner in plan.live()
    if card is not None and possible:
        ch = plan.ch(card)
        possible = not bool(ch.types & {'Instant', 'Sorcery'}) and prohibitions.cant_enter(plan, card, card.owner) is None
        if possible and attachments.attach_kind(ch) == 'aura':
            possible = bool(attachments._entry_hosts(plan, card, {'card': card.id, 'player': card.owner, 'actor': ctx['controller']}))
    if not possible:
        ctx['next'] += 2  # Skip the impossible optional cost, retaining its delayed fallback.
    # Native return_card.did is the CR118.12 payment receipt, bound before entry
    # replacements. A redirected return remains paid (118.11); final BF arrival
    # is deliberately not a test for this printed "if you don't".
    return True


PRIMITIVES = {STEP: preflight}
