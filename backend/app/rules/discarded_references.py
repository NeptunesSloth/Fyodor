"""Opt-in CR 702.35c/400.7k tracking; ordinary target identity never follows a move."""

from __future__ import annotations

from typing import Any

from app.game.rules_state import MadnessFollowup
from app.rules.plan import Plan


def begin(plan: Plan, cid: str) -> str:
    from app.rules import context

    ref = context.ref_of(plan, cid)
    assert ref is not None
    plan.rules.madness_declined[ref.object_id] = MadnessFollowup(original=ref)
    return ref.object_id


def observe(plan: Plan, payload: dict[str, Any]) -> None:
    """Only the committed native transition, including a held 616 choice, supplies a result."""
    if payload.get("type") != "move":
        return
    ids = set(payload.get("card_ids") or [])
    from app.rules import context

    for item in plan.rules.madness_declined.values():
        if not item.pending or item.original.card not in ids:
            continue
        card = plan.state.cards.get(item.original.card)
        if card is not None and plan.oid(card) == item.original.object_id:
            continue
        item.pending = False
        if (
            card is not None
            and card.zone.rsplit(":", 1)[-1] not in context.HIDDEN_ZONES
            and not card.face_down
        ):
            item.result = context.ref_of(plan, card.id)


def finish_attempt(plan: Plan, oid: str) -> None:
    item = plan.rules.madness_declined[oid]
    if item.pending and item.original.card not in plan.rules.pending_616:
        item.pending = False


def objects(plan: Plan, ctx: dict[str, Any], name: str) -> list[str]:
    from app.rules import context

    out = []
    for ref in context._object_refs(ctx, name):
        card = context._same(plan, ref)
        if card is None:
            item = plan.rules.madness_declined.get(ref.object_id)
            if (
                item is not None
                and item.original.card == ref.card
                and not item.pending
                and item.result is not None
            ):
                card = context._same(plan, item.result)
        if card is not None:
            out.append(card.id)
    return list(dict.fromkeys(out))
