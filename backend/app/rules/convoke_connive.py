"""CR 702.51, 701.50b-c: the actual convokers, including departed objects, connive in chosen order."""
from __future__ import annotations

from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.plan import Plan, decide

Conniver = tuple[str | None, str | None, str]


def contributors(plan: Plan, ctx: dict[str, Any]) -> list[Conniver]:
    record = plan.rules.payments.get(ctx.get('source_object') or '')
    if record is None:
        return []
    seen: set[str] = set()
    result: list[Conniver] = []
    for paid in record.contributions:
        if paid.kind != 'convoke' or paid.object_id in seen:
            continue
        seen.add(paid.object_id)
        card = plan.state.cards.get(paid.card)
        if card is not None and card.zone.endswith(':phased') and plan.oid(card) == paid.object_id:
            continue  # CR 702.26b: this object is treated as though it does not exist.
        if card is not None and card.zone.endswith(':battlefield') and plan.oid(card) == paid.object_id:
            result.append((paid.card, paid.object_id, card.controller))
        elif (snap := plan.rules.lki.get(paid.object_id)) is not None:
            result.append((paid.card, paid.object_id, snap.controller))
    return result


def schedule(plan: Plan, ctx: dict[str, Any], queue: list[Conniver], n: int) -> bool:
    """The first player in APNAP order chooses one of their remaining connivers (701.50c)."""

    queue = [q for q in queue if q[2] in plan.live()]
    if not queue:
        return True
    order = plan.apnap()
    queue.sort(key=lambda q: order.index(q[2]) if q[2] in order else len(order))
    player = queue[0][2]
    eligible = [q for q in queue if q[2] == player]
    if len(eligible) == 1:
        return run_one(plan, ctx, queue, eligible[0], n)
    options = []
    for cid, oid, _ in eligible:
        card = plan.state.cards.get(cid or '')
        snap = plan.rules.lki.get(oid or '')
        name = (card.name if card is not None else None) or (snap.name if snap is not None else None) or 'A creature'
        options.append(DecisionOption(id=oid or cid or '', label=f'{name} connives next'[:200], card_id=cid))
    decide(plan, player=player, kind='choose_one', prompt='Choose which creature connives next', options=options,
           resume={'step': 'connive_order', 'ctx': ctx, 'queue': [list(q) for q in queue], 'n': n})
    return False


def run_one(plan: Plan, ctx: dict[str, Any], queue: list[Conniver], selected: Conniver, n: int) -> bool:
    from app.rules import replace

    remaining = list(queue)
    remaining.remove(selected)
    effects: list[dict[str, Any]] = [{'do': 'connive', 'conniver': list(selected), 'n': n}]
    if remaining:
        effects.append({'do': 'connive', 'connivers': [list(q) for q in remaining], 'n': n})
    return replace.run_effects(plan, ctx, effects)


def resume(plan: Plan, decision: Any, chosen: list[str]) -> None:
    queue: list[Conniver] = [(q[0], q[1], q[2]) for q in decision.resume['queue']]
    selected = next(q for q in queue if (q[1] or q[0]) == chosen[0])
    run_one(plan, decision.resume['ctx'], queue, selected, int(decision.resume['n']))
