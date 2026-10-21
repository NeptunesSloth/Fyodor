"""Native consequences of revealed cards, fixed before those cards move."""
from __future__ import annotations

from typing import Any

from app.rules import context, selectors
from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip().rstrip('.')
    text = text[:1].upper() + text[1:]
    lead = 'Reveal the top card of your library and put it into your hand. '
    cases = {
        lead + "You lose life equal to that card's mana value": 'life',
        "Reveal the top card of your library and put that card into your hand. You lose life equal to the card's mana value": 'life',
        lead + "You lose life equal to that card's mana value if ~ isn't saddled. Otherwise, each opponent loses that much life": 'bronco',
        lead + "~ deals damage to himself equal to that card's mana value": 'sarkhan',
        "Reveal the top card of your library. You may put that card onto the battlefield if it's a permanent card with mana value 3 or less. Otherwise, put that card into your hand": 'reshape',
    }
    if text == "Target creature's controller sacrifices it, then that player creates a 5/5 red Dragon creature token with flying":
        return [{'do': 'sarkhan_transmute'}], 'creature', False
    if text == "Target opponent reveals the top three cards of their library, may put a creature card from among them onto the battlefield, then puts the rest into their graveyard. You do the same with the top three cards of your library. If two creatures are put onto the battlefield this way, those creatures fight each other":
        return [{'do': 'guild_reveals'}], 'opponent', False
    if text in cases:
        return [{'do': 'reveal_consequence', 'mode': cases[text]}], None, False
    if text == 'You may reveal the top card of your library and put it into your hand. If you do, you lose life equal to its mana value':
        return [{'do': 'reveal_consequence', 'mode': 'life'}], None, True
    return None


def insert(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    ctx['effects'][ctx['next']:ctx['next']] = steps


def reveal_consequence(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import reveal_outcomes

    mode = e['mode']
    if not reveal_outcomes.reveal_outcome_top(plan, ctx, {'do': 'reveal_outcome_top', 'n': 1, 'player': 'you', 'reveal': True, 'exact_look': True}):
        return False
    ids = list(ctx.get('looked') or [])
    value = int(plan.ch(plan.state.cards[ids[0]]).mana_value) if ids else 0
    if mode == 'reshape':
        key = f'reshape_shown_{ctx["next"]}'
        context.bind_objects(plan, ctx, key, ids)
        sel = selectors.parse('permanent card with mana value 3 or less')
        assert sel is not None
        insert(ctx, [{'do': 'pick_looked', 'n': 1, 'optional': True, 'sel': sel.key(), 'to': 'battlefield'},
                     {'do': 'reveal_remaining_hand', 'ref': 'ref:' + key}])
        return True
    steps: list[dict[str, Any]] = [{'do': 'pick_looked', 'which': 'all', 'to': 'hand'}]
    if mode == 'sarkhan':
        steps.append({'do': 'damage', 'who': 'self', 'n': value})
    else:
        saddled = mode == 'bronco' and plan.rules.turn_log.turn == plan.state.turn.number and any(
            f.kind == 'saddled' and f.object_id == ctx.get('source_object') for f in plan.rules.turn_log.facts)
        steps.append({'do': 'lose_life', 'who': 'each_opponent' if saddled else 'you', 'n': value})
    insert(ctx, steps)
    return True


def remaining_hand(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    # A selected permanent can fail to enter (Cage, no legal Aura host). Only the
    # original revealed library object is put into hand; redirected cards stay put.
    ids = [cid for cid in context.objects(plan, ctx, e['ref'].removeprefix(context.PREFIX))
           if plan.state.cards[cid].zone == ctx['controller'] + ':library']
    ctx['looked'] = ids
    insert(ctx, [{'do': 'rest_looked', 'to': 'hand'}])
    return True


PRIMITIVES = {'reveal_consequence': reveal_consequence, 'reveal_remaining_hand': remaining_hand}


def sarkhan_transmute(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, scripts

    ids = effects._cards(plan, ctx, 'target')
    if not ids:
        return True
    player = plan.state.cards[ids[0]].controller
    native = scripts.parse_effects('Create a 5/5 red Dragon creature token with flying.')
    assert native is not None
    insert(ctx, [{'do': 'sacrifice', 'who': 'target', 'by': 'controller'},
                 *[{**step, 'who': 'player:' + player} for step in native[0]]])
    return True


PRIMITIVES.update({'sarkhan_transmute': sarkhan_transmute})


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    if ability.kind != 'triggered':
        return None
    text = scripts.self_text(ability.text, ch.name)
    cases = {
        'Whenever equipped creature dies, you may reveal cards from the top of your library until you reveal a creature card that shares a creature type with it. Put that card into your hand and the rest on the bottom of your library in a random order.': ('Whenever equipped creature dies, you gain 1 life.', 'heirloom', True),
        'Whenever one or more creatures you control deal combat damage to a player, you may sacrifice one of them. If you do, reveal cards from the top of your library until you reveal a creature card that shares a creature type with the sacrificed creature. Put that card onto the battlefield and the rest on the bottom of your library in a random order.': ('Whenever one or more creatures you control deal combat damage to a player, you gain 1 life.', 'fury_choose', False),
        "At the beginning of enchanted player's upkeep, that player reveals cards from the top of their library until they reveal a creature card. Put that card onto the battlefield under your control. That player puts the rest of the revealed cards into their graveyard.": ("At the beginning of enchanted player's upkeep, you gain 1 life.", 'unbinding', False),
        'At the beginning of your upkeep, reveal cards from the top of your library until you reveal a creature card. Until your next turn, ~ has base power twice that card\'s power and it has base toughness twice that card\'s toughness. Put the revealed cards on the bottom of your library in a random order.': ('At the beginning of your upkeep, you gain 1 life.', 'amplifire', False),
    }
    if text not in cases:
        return None
    native_text, mode, optional = cases[text]
    native = scripts.define(replace(ability, text=native_text), ch)
    if native is None:
        return None
    return {**native, 'optional': optional, 'effects': [{'do': 'reveal_relative', 'mode': mode, 'who': 'ref:event'}]}


def reveal_relative(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import reveal_outcomes, scripts
    from app.rules.creature_types import CREATURE_TYPES

    mode = e['mode']
    if mode == 'fury_choose':
        from app.rules import prohibitions

        eligible = [c for c in context.objects(plan, ctx, 'event')
                    if plan.state.cards[c].zone.endswith(':battlefield')
                    and plan.state.cards[c].controller == ctx['controller']
                    and plan.ch(plan.state.cards[c]).is_creature
                    and not prohibitions.sacrifice_forbidden(plan, plan.state.cards[c])
                    and not prohibitions.cant_cause_sacrifice(plan, ctx['controller'], ctx['controller'])]
        key = f'fury_options_{ctx["next"]}'
        selected, paid = key + '_selected', key + '_paid'
        context.bind_objects(plan, ctx, key, eligible)
        insert(ctx, [{'do': 'return_choice', 'who': 'ref:' + key, 'to': 'choose', 'upto': True, 'n': 1, 'as': selected},
                     {'do': 'sacrifice', 'who': 'ref:' + selected, 'as': paid},
                     {'do': 'reveal_relative', 'mode': 'fury', 'who': 'ref:' + paid}])
        return True
    until = selectors.Selector(zones=(), card=True, types=('Creature',))
    if mode in ('heirloom', 'fury'):
        infos = context.infos(plan, ctx, e['who'].removeprefix(context.PREFIX))
        if mode == 'fury' and not infos:
            return True
        types = set().union(*(ch.subtypes & CREATURE_TYPES for _, ch in infos))
        from dataclasses import replace
        until = replace(until, subtypes=tuple(sorted(types))) if types else replace(until, not_types=('Creature',))
    player = 'enchanted_player' if mode == 'unbinding' else 'you'
    if not reveal_outcomes.reveal_outcome_top(plan, ctx, {'do': 'reveal_outcome_top', 'n': 0, 'player': player, 'until': until.key(), 'reveal': True, 'exact_look': True}):
        return False
    ids = list(ctx.get('looked') or [])
    found = ctx.get('found')
    if mode == 'amplifire':
        pt = plan.ch(plan.state.cards[found]).pt if isinstance(found, str) and found in ids else None
        p, t = (2 * pt[0], 2 * pt[1]) if pt is not None else (0, 0)
        native = scripts.parse_effects(f'Until your next turn, ~ has base power and toughness {p}/{t}.')
        assert native is not None
        insert(ctx, [*native[0], {'do': 'rest_looked', 'to': 'bottom_random'}])
    else:
        insert(ctx, [{'do': 'pick_looked', 'which': 'that', 'require_found': True, 'to': 'hand' if mode == 'heirloom' else 'battlefield'},
                     {'do': 'rest_looked', 'to': 'graveyard' if mode == 'unbinding' else 'bottom_random', 'viewer': player}])
    return True


PRIMITIVES.update({'reveal_relative': reveal_relative})


def guild_reveals(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import reveal_outcomes

    own = bool(e.get('own'))
    player = 'you' if own else 'target'
    if not reveal_outcomes.reveal_outcome_top(plan, ctx, {'do': 'reveal_outcome_top', 'n': 3, 'player': player, 'viewer': player, 'reveal': True, 'exact_look': True}):
        return False
    key = f'guild_arrival_{ctx["next"]}'
    creature = selectors.Selector(zones=(), card=True, types=('Creature',)).key()
    steps: list[dict[str, Any]] = [{'do': 'pick_looked', 'n': 1, 'optional': True, 'sel': creature, 'to': 'battlefield', 'by_owner': True, 'chooser': 'looked_owner', 'as': key},
             {'do': 'rest_looked', 'to': 'graveyard', 'viewer': player}]
    if own:
        steps.append({'do': 'fight', 'who': e['who'], 'with': 'ref:' + key})
    else:
        steps.append({'do': 'guild_reveals', 'own': True, 'who': 'ref:' + key})
    insert(ctx, steps)
    return True


PRIMITIVES.update({'guild_reveals': guild_reveals})
