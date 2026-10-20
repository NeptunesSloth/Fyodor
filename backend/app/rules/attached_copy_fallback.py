"""CR 608.2c/h, 111.2: conditional payment for an attached copy, otherwise a token."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import context

if TYPE_CHECKING:
    from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import token_grammar

    m = re.fullmatch(r"[Yy]ou may pay (?P<cost>(?:\{[0-9WUBRG]+\})+) if (?:~|this permanent) is attached to a creature you control\. "
                     r"If you do, create a token that's a copy of that creature\. If you didn't create a token this way, "
                     r'(?P<fallback>create .+? token)\.', body)
    if m is None:
        return None
    fallback = token_grammar.parse(m['fallback'])
    if not fallback or len(fallback) != 1:
        return None
    return ([{'do': 'prepare_attached_copy', 'as': 'attached_copy_host', 'bind': 'attached_copy_eligible'},
             {'do': 'only_if', 'cond': {'flag': 'attached_copy_eligible'}, 'skip': 3},
             {'do': 'optional_payment', 'who': 'you', 'cost': m['cost'], 'bind': 'attached_copy_paid'},
             {'do': 'only_if', 'cond': {'succeeded': 'attached_copy_paid'}, 'skip': 1},
             {'do': 'token_copy', 'who': 'ref:attached_copy_host', 'n': 1, 'as': 'attached_copy_made'},
             {'do': 'only_if', 'cond': {'not': {'created_by_you': 'ref:attached_copy_made'}}, 'skip': 1},
             fallback[0]], None, False)


def prepare(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    source = plan.state.cards.get(ctx.get('source_card') or '')
    host = plan.state.cards.get(source.attached_to or '') if source is not None else None
    eligible = bool(source is not None and source.zone.endswith(':battlefield') and plan.oid(source) == ctx.get('source_object')
                    and host is not None and host.zone.endswith(':battlefield') and plan.ch(host).is_creature
                    and host.controller == ctx['controller'])
    context.bind_objects(plan, ctx, e['as'], [host.id] if eligible and host is not None else [])
    context.bind_flag(ctx, e['bind'], eligible)
    return True


def created_by_you(plan: Plan, ctx: dict[str, Any], who: str) -> bool:
    name = who[len(context.PREFIX):]
    for ref in context._object_refs(ctx, name):
        card = plan.state.cards.get(ref.card)
        snapshot = context.snapshot(plan, ref) if card is None else None
        is_token = card.is_token if card is not None else snapshot.is_token if snapshot is not None else False
        owner = card.owner if card is not None else snapshot.owner if snapshot is not None else None
        if is_token and owner == ctx['controller']:
            return True
    return False


PRIMITIVES = {'prepare_attached_copy': prepare}
