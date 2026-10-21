"""Exact card incarnations paid directly, distinct from auxiliary mana-source costs."""

from __future__ import annotations

from typing import Any, Literal

from app.game.rules_state import PaidCardFact, PaymentRecord
from app.rules.plan import Plan

Kind = Literal["discarded", "revealed", "exiled", "milled"]


def describe(plan: Plan, card_id: str) -> PaidCardFact:
    from app.rules.stack_interaction import mana_value

    card = plan.state.cards[card_id]
    ch = plan.ch(card)
    return PaidCardFact(
        card=card_id,
        object_id=plan.oid(card),
        zone=card.zone,
        mana_value=mana_value(card, ch),
        mana_cost=ch.mana_cost,
        colors=sorted(ch.colors),
        types=sorted(ch.types),
        subtypes=sorted(ch.subtypes),
    )


def record(plan: Plan, paid: PaymentRecord, kind: Kind, ids: list[str]) -> None:
    key = kind + "_facts"
    prior = getattr(paid, key)
    setattr(paid, key, [*(prior or []), *(describe(plan, cid) for cid in ids if cid in plan.state.cards)])


def get(plan: Plan, ctx: dict[str, Any], kind: Kind) -> list[PaidCardFact] | None:
    sid = ctx.get("stack_id")
    paid = plan.rules.payments.get(plan.oid(sid)) if sid else None
    if paid is None:
        return None
    facts = getattr(paid, kind + "_facts")
    if facts is None:
        return None
    return [
        describe(plan, f.card)
        if f.card in plan.state.cards
        and plan.oid(f.card) == f.object_id
        and plan.state.cards[f.card].zone == f.zone
        else f
        for f in facts
    ]


def freeze_departures(plan: Plan, payload: dict[str, Any]) -> None:
    """Refresh only paid objects actually about to move; unrelated costs and old objects stay fixed."""
    if payload.get("type") not in ("move", "mill", "delete_card", "return_to_owner", "put_top_face_down"):
        return
    ids = set(payload.get("card_ids") or ([payload["card_id"]] if payload.get("card_id") else []))
    if payload.get("type") == "mill":
        ids.update(
            plan.state.zones.get(str(payload.get("player")) + ":library", [])[
                : int(payload.get("count") or 0)
            ]
        )
    if not ids:
        return
    for paid in plan.rules.payments.values():
        for key in ("discarded_facts", "revealed_facts", "exiled_facts", "milled_facts"):
            facts = getattr(paid, key)
            if facts is not None:
                setattr(
                    paid,
                    key,
                    [
                        describe(plan, f.card)
                        if f.card in ids
                        and f.card in plan.state.cards
                        and plan.oid(f.card) == f.object_id
                        and plan.state.cards[f.card].zone == f.zone
                        else f
                        for f in facts
                    ],
                )
