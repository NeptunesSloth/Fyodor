"""Chapter choices, simultaneous linked exile and ordinary paid casts."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption, ObjectRef

if TYPE_CHECKING:
    from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import sagas

    if ability.text == 'I — Exile an instant or sorcery card from each graveyard.':
        base = sagas.chapter_definition(replace(ability, text='I — Gain 1 life.'), ch)
        return {**base, 'effects': [{'do': 'esper_graveyard_choices'}]} if base is not None else None
    if ability.text == ('II, III, IV — Add {R} for each lore counter on this Saga. You may cast an instant or sorcery '
            'card exiled with this Saga, and mana of any type can be spent to cast that spell.'):
        base = sagas.chapter_definition(replace(ability, text='II, III, IV — Gain 1 life.'), ch)
        return {**base, 'effects': [
            {'do': 'add_mana', 'sym': 'R', 'n': {'counters': 'lore', 'on': 'self'}},
            {'do': 'esper_paid_cast'}]} if base is not None else None
    return None


def _eligible(plan: Plan, player: str) -> list[str]:
    return [cid for cid in plan.state.zones.get(f'{player}:graveyard', [])
            if plan.ch(plan.state.cards[cid]).is_instant_or_sorcery]


def graveyard_choices(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    return _next(plan, ctx, [p for p in plan.state.seat_order if p in plan.live()], [])


def _next(plan: Plan, ctx: dict[str, Any], players: list[str], picked: list[dict[str, Any]]) -> bool:
    from app.rules import effects
    from app.rules.plan import decide

    while players:
        player, *players = players
        ids = _eligible(plan, player)
        if not ids:
            continue
        decide(plan, player=ctx['controller'], kind='choose_cards',
            prompt=f"Exile an instant or sorcery card from {plan.name(player)}'s graveyard",
            options=[DecisionOption(id=cid, label=plan.ch(plan.state.cards[cid]).name, card_id=cid) for cid in ids],
            min_choices=1, max_choices=1,
            resume={'step': 'esper_graveyard_choice', 'ctx': ctx, 'players': players, 'picked': picked,
                    'graveyard': player, 'options': {cid: ObjectRef(card=cid, object_id=plan.oid(cid)).model_dump() for cid in ids}})
        return False
    ids = [ref.card for raw in picked if (ref := ObjectRef.model_validate(raw)).card in plan.state.cards
           and plan.oid(ref.card) == ref.object_id and plan.state.cards[ref.card].zone.endswith(':graveyard')]
    return effects.exile_cards(plan, ctx, {'link': True}, ids)


def resume_graveyard(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    job = decision.resume
    picked = [*job['picked'], job['options'][chosen[0]]]
    if _next(plan, job['ctx'], job['players'], picked):
        effects.continue_effects(plan, job['ctx'])


def paid_cast(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, exiled_with
    from app.rules import exile_packet_continuations as packets

    ids = [cid for cid in exiled_with.cards(plan, ctx) if plan.ch(plan.state.cards[cid]).is_instant_or_sorcery]
    context.bind_objects(plan, ctx, 'esper_packet', ids)
    return packets.insert(ctx, [packets.offer({'binding': 'ref:esper'}, paid=True, spend='type', n=1)])


PRIMITIVES = {'esper_graveyard_choices': graveyard_choices, 'esper_paid_cast': paid_cast}
RESUME = {'esper_graveyard_choice': resume_graveyard}
