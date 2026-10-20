"""Staged linked actual mana notes; registrations intentionally remain absent."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import NotedMana

if TYPE_CHECKING:
    from app.rules.mana import ManaAbility
    from app.rules.plan import Plan


ICE_INPUT = ('{X}, {T}: You may exile a nonland card from your hand. You may cast that card for as long as it remains exiled. '
             'Put a charge counter on ~ and note the type and amount of mana spent to pay this activation cost. '
             'Activate only if there are no charge counters on ~.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    if ability.kind == 'activated' and scripts.self_text(ability.text, ch.name) == ICE_INPUT:
        base = scripts.define(replace(ability, text='{X}, {T}: Draw a card. '
            'Activate only if there are no charge counters on ~.'), ch)
        if base is not None:
            hand = selectors.Selector(zones=('hand',), zone_owner='you', card=True, not_types=('Land',)).key()
            return {**base, 'effects': [
                {'do': 'return_choice', 'sel': hand, 'to': 'exile', 'under': 'owner', 'n': 1, 'upto': True, 'as': 'ice_packet'},
                {'do': 'ice_actual_exile'},
                {'do': 'grant_play', 'who': 'ref:ice_packet', 'from_exile': True,
                 'play': False, 'cast': True, 'free': False, 'until': 'permanent'},
                {'do': 'add_counters', 'who': 'self', 'kind': 'charge', 'n': 1},
                {'do': 'note_actual_mana'}]}
    return None


def actual_exile(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, exiled_with

    refs = [ref for ref in context._object_refs(ctx, 'ice_packet')
            if (card := plan.state.cards.get(ref.card)) is not None and plan.oid(card) == ref.object_id
            and card.zone.endswith(':exile')]
    if refs:
        key = exiled_with.link_key(ctx)
        prior = plan.rules.noted_mana.get(key)
        plan.rules.noted_mana[key] = NotedMana(mana=prior.mana if prior is not None else None, last_exiled=refs)
    return True


def note_payment(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import exiled_with

    sid = ctx.get('stack_id')
    receipt = plan.rules.payments.get(plan.oid(sid)) if sid else None
    key = exiled_with.link_key(ctx)
    prior = plan.rules.noted_mana.get(key)
    last = prior.last_exiled if prior is not None else ([] if key in plan.rules.noted_mana else None)
    plan.rules.noted_mana[key] = NotedMana(mana=dict(receipt.mana_spent) if receipt is not None else None, last_exiled=last)
    return True


PRIMITIVES = {'ice_actual_exile': actual_exile, 'note_actual_mana': note_payment}


def parse_mana(text: str, identity: tuple[str, ...], name: str) -> ManaAbility | None:
    from app.rules import mana as M
    from app.rules import scripts

    if scripts.self_text(text, name) == ('{T}, Remove a charge counter from ~: Add ~\'s last noted type and amount of mana. '
            'Spend this mana only to cast the last card exiled with ~.'):
        return M.ManaAbility(tap=True, sacrifice_self=False, options=((),), extra_cost='Remove a charge counter from ~',
            chooses=True, native_body=True, immediate_effects=({'do': 'noted_mana_output'},))
    return None


def output(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    import json

    from app.game.rules_state import DecisionOption
    from app.rules import exiled_with, immediate_mana_resolutions
    from app.rules import mana as M
    from app.rules.plan import decide

    key = exiled_with.link_key(ctx)
    note = plan.rules.noted_mana.get(key)
    if key not in plan.rules.noted_mana or (note is not None and (note.mana is None or note.last_exiled is None)):
        decide(plan, player=ctx['controller'], kind='manual_resolution',
            prompt='This older object has no recorded exact mana note or last exiled card. Add and restrict the mana by hand, then press Done.',
            options=[DecisionOption(id='done', label='Done')], resume={'step': 'unknown_noted_mana', 'ctx': ctx})
        return False
    vector = note.mana if note is not None else {}
    refs = note.last_exiled if note is not None else []
    ctx['mana_context'] = {**ctx.get('mana_context', {}), 'only': 'cast_objects:' +
        json.dumps([ref.model_dump(mode='json') for ref in refs or []], sort_keys=True)}
    immediate_mana_resolutions.produce_chosen(plan, ctx, ctx['controller'],
        [color for color in M.ALL_MANA for _ in range((vector or {}).get(color, 0))])
    return False


def resume_unknown(plan: Plan, decision: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, decision.resume['ctx'])


PRIMITIVES['noted_mana_output'] = output
RESUME = {'unknown_noted_mana': resume_unknown}
