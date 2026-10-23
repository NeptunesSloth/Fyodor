"""Per-permanent choices precede prepared life payments and sacrifice outcomes."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, ObjectRef
from app.rules import world_durations80
from app.rules.plan import DepartureBefore, Plan, decide

TEXT = 'For each creature, its controller sacrifices it unless they pay X life.'


class Offer83(BaseModel):
    object: ObjectRef
    payer: str
    name: str
    paid: bool = False
    routes: list[dict[str, Any]] = Field(default_factory=list)
    chosen_route: int | None = None


class Packet83(BaseModel):
    rows: list[Offer83]
    remaining: list[str]
    life: int
    before: DepartureBefore | None = None


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    return ([{'do': 'permanent_life83'}], None, False) if body.strip() == TEXT else None


def begin(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, effects

    rows = [Offer83(object=ref, payer=card.controller, name=plan.ch(card).name or 'Creature')
            for card in plan.state.cards.values()
            if card.zone.endswith(':battlefield') and plan.in_game(card) and plan.ch(card).is_creature
            and (ref := context.ref_of(plan, card.id)) is not None]
    packet = Packet83(rows=rows, remaining=plan.apnap(), life=effects._amount(plan, ctx, {'x': 1}))
    return ask(plan, ctx, packet)


def guard(plan: Plan, rows: list[Offer83]) -> None:
    from app.rules import context

    for row in rows:
        if row.payer not in plan.live():
            continue
        if context._same(plan, row.object) is None:
            raise ActionError('An original creature changed before the permanent choices finished')


def ask(plan: Plan, ctx: dict[str, Any], packet: Packet83) -> bool:
    guard(plan, packet.rows)
    packet.remaining = [p for p in packet.remaining if p in plan.live()]
    while packet.remaining and not any(r.payer == packet.remaining[0] for r in packet.rows):
        packet.remaining.pop(0)
    if not packet.remaining:
        return prepare(plan, ctx, packet)
    player = packet.remaining[0]
    rows = [r for r in packet.rows if r.payer == player]
    decide(plan, player=player, kind='choose_cards',
           prompt=f"{ctx.get('name') or 'The spell'}: choose creatures to pay {packet.life} life for each",
           options=[DecisionOption(id=r.object.card, label=r.name, card_id=r.object.card) for r in rows],
           min_choices=0, max_choices=len(rows),
           resume={'step': 'permanent_life83', 'ctx': ctx, 'packet': packet.model_dump(mode='json')})
    return False


def resume_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects, optional_payment

    ctx = d.resume['ctx']
    packet = Packet83.model_validate(d.resume['packet'])
    guard(plan, packet.rows)
    eligible = {r.object.card for r in packet.rows if r.payer == d.player}
    if len(set(chosen)) != len(chosen) or not set(chosen) <= eligible:
        raise ActionError('Choose distinct creatures offered to your payment')
    cost = optional_payment.parse(f'Pay {packet.life * len(chosen)} life')
    assert cost is not None
    if chosen and (why := optional_payment.problem(plan, ctx, cost, d.player)) is not None:
        raise ActionError(why)
    for row in packet.rows:
        if row.payer == d.player:
            row.paid = row.object.card in chosen
    plan.note(f"{plan.name(d.player)} chooses {len(chosen)} life payments for {ctx.get('name') or 'the spell'}", chosen)
    packet.remaining.pop(0)
    if ask(plan, ctx, packet):
        effects.continue_effects(plan, ctx)


def prepare(plan: Plan, ctx: dict[str, Any], packet: Packet83) -> bool:
    from app.rules import context, prohibitions, replacements

    packet.rows = [r for r in packet.rows if r.payer in plan.live()]
    for row in packet.rows:
        card = context._same(plan, row.object)
        if card is not None and not row.paid and card.controller == row.payer \
                and not prohibitions.sacrifice_forbidden(plan, card) \
                and not prohibitions.cant_cause_sacrifice(plan, row.payer, ctx['controller']):
            row.routes = [c._asdict() for c in {c.sig: c for c in replacements.zone_candidates(plan, card)}.values()]
        else:
            row.chosen_route = -1  # No sacrifice instruction can affect this original object.
    return routes(plan, ctx, packet)


def routes(plan: Plan, ctx: dict[str, Any], packet: Packet83) -> bool:
    guard(plan, packet.rows)
    for row in packet.rows:
        if row.chosen_route is None and len(row.routes) > 1:
            decide(plan, player=row.payer, kind='choose_one',
                   prompt=f'{row.name}: which graveyard replacement applies first? (616.1)',
                   options=[DecisionOption(id=str(i), label=c['label'] + ': ' + c['outcome'])
                            for i, c in enumerate(row.routes)],
                   resume={'step': 'permanent_route83', 'ctx': ctx, 'packet': packet.model_dump(mode='json'),
                           'card': row.object.card})
            return False
    packet.before = plan.freeze_departures([r.object.card for r in packet.rows if not r.paid and r.chosen_route != -1])
    losses = {p: packet.life * sum(r.payer == p and r.paid for r in packet.rows) for p in plan.live()}
    at = ctx['next']
    ctx['effects'][at:at] = [
        {'do': 'lose_life', 'who': 'each_player', 'n': 0, 'counts': losses},
        {'do': 'permanent_commit83', 'packet': packet.model_dump(mode='json'), 'batch_start': plan.rules.batch}]
    return True


def resume_route(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    packet = Packet83.model_validate(d.resume['packet'])
    row = next(r for r in packet.rows if r.object.card == d.resume['card'])
    if len(chosen) != 1 or chosen[0] not in {str(i) for i in range(len(row.routes))}:
        raise ActionError('Choose one prepared replacement')
    row.chosen_route = int(chosen[0])
    if routes(plan, d.resume['ctx'], packet):
        effects.continue_effects(plan, d.resume['ctx'])


@world_durations80.native
def commit(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import replace, replacements
    from app.rules.triggers import sacrificing

    packet = Packet83.model_validate(e['packet'])
    guard(plan, packet.rows)
    rows = [r for r in packet.rows if not r.paid and r.chosen_route != -1]
    chosen = [(r, replacements.Cand(**r.routes[r.chosen_route or 0]) if r.routes else None) for r in rows]
    sacrificing(plan, [r.object.card for r in rows])
    groups: dict[str, dict[str, dict[str, str]]] = {}
    shuffles: list[str] = []
    for row, candidate in chosen:
        card = plan.state.cards[row.object.card]
        outcome = candidate.outcome if candidate is not None else 'graveyard'
        position = 'bottom' if outcome == 'library:bottom' else 'top'
        groups.setdefault(position, {})[card.id] = {'player': card.owner, 'zone': outcome.split(':')[0]}
        if candidate is not None and candidate.used:
            plan.rules.exile_if_graveyard = [o for o in plan.rules.exile_if_graveyard if o != row.object.object_id]
            plan.rules.bottom_if_graveyard = [o for o in plan.rules.bottom_if_graveyard if o != row.object.object_id]
        plan.rules.exile_if_leaves = [o for o in plan.rules.exile_if_leaves if o != row.object.object_id]
        if outcome == 'library:shuffle':
            plan.do({'type': 'reveal', 'card_ids': [card.id]}, actor=ctx['controller'])
            shuffles.append(card.owner)
    for position, destinations in groups.items():
        plan.do({'type': 'move', 'card_ids': list(destinations), 'to': {'zone': 'graveyard'},
                 'routes': destinations, 'position': position}, actor=ctx['controller'], departure_before=packet.before)
    for row, candidate in chosen:
        if candidate is not None:
            replacements._record_link(plan, row.object.card, candidate)
            if candidate.counter:
                replacements.mark_exiled_counters(plan, [row.object.card], candidate.counter, actor=ctx['controller'])
            if candidate.rider is not None:
                replacements.run_rider(plan, candidate.rider)
    replace._one_batch(plan, e['batch_start'])
    for player in dict.fromkeys(shuffles):
        plan.do({'type': 'shuffle', 'player': player, 'zone': 'library'}, actor=player)
    return True


PRIMITIVES = {'permanent_life83': begin, 'permanent_commit83': commit}
RESUME = {'permanent_life83': resume_choice, 'permanent_route83': resume_route}
