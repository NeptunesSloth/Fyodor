"""Reveal outcomes whose information is fixed before later movements and choices."""
from __future__ import annotations

import re
from typing import Any

from app.rules import card_names, selectors
from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip().rstrip('.')
    text = text[:1].upper() + text[1:]
    if text == ('Reveal cards from the top of your library until you reveal a land card. ~ deals damage equal to the number of nonland cards revealed this way to any target. If the revealed land card was a Mountain, ~ deals double that damage instead. Put the revealed cards on the bottom of your library in any order'):
        return [{'do': 'reveal_snapshot', 'mode': 'charbelcher'}], 'any', False
    if text == ('Target opponent reveals the top card of their library. ~ deals damage equal to the revealed card\'s mana value to that player and each creature that player controls. If a land card is revealed this way, return ~ to its owner\'s hand'):
        return [{'do': 'reveal_snapshot', 'mode': 'eruption'}], 'opponent', False
    if text == ('Reveal the top ten cards of your library. For each blue mana symbol in the mana costs of the revealed cards, target opponent mills a card. Then put the cards you revealed this way on the bottom of your library in any order'):
        return [{'do': 'reveal_snapshot', 'mode': 'chroma'}], 'opponent', False
    if text == ('Reveal the top card of your library. If it has the same name as a card in your graveyard, put it into your graveyard. Otherwise, draw a card'):
        return [{'do': 'reveal_snapshot', 'mode': 'candles'}], None, False
    if text == ("Reveal cards from the top of your library until you reveal a nonland card. Put the revealed cards on the bottom of your library in a random order. When you reveal a nonland card this way, ~ deals damage equal to that card's mana value to any target"):
        return [{'do': 'reveal_snapshot', 'mode': 'blast'}], None, False
    if text == ('Reveal cards from the top of your library until you reveal a creature card. Put that card into your hand and the rest on the bottom of your library in a random order. When you reveal a creature card this way, put X +1/+1 counters on target creature you control, where X is the mana value of that card'):
        return [{'do': 'reveal_snapshot', 'mode': 'whistle'}], None, False
    if text == ("Reveal the top card of your library. If it isn't a creature card, put it into your graveyard. Otherwise, put that card onto the battlefield. That creature gains haste. Sacrifice it at the beginning of the next end step"):
        return [{'do': 'reveal_snapshot', 'mode': 'raid'}], None, False
    if text == ("Target opponent reveals cards from the top of their library until an artifact card or X cards are revealed, whichever comes first. If an artifact card is revealed this way, put it onto the battlefield under your control and sacrifice ~. Put the rest of the revealed cards into that player's graveyard"):
        return [{'do': 'reveal_snapshot', 'mode': 'dissect'}], 'opponent', False
    return None


def _insert(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    ctx['effects'][ctx['next']:ctx['next']] = steps


def reveal_snapshot(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects, reveal_outcomes

    mode = e['mode']
    if mode in ('naya', 'preserve'):
        return reveal_everyone(plan, ctx, e)
    who = 'target' if mode in ('eruption', 'dissect') else 'defending_player' if mode == 'trepan' else 'you'
    look: dict[str, Any] = {'do': 'reveal_outcome_top', 'n': 10 if mode == 'chroma' else 1,
                            'player': who, 'reveal': True, 'exact_look': True}
    if mode in ('charbelcher', 'trepan'):
        look.update(n=0, until=selectors.Selector(zones=(), card=True, types=('Land',)).key())
    artifact_at = None
    if mode in ('blast', 'whistle'):
        sel = selectors.Selector(zones=(), card=True)
        from dataclasses import replace
        sel = replace(sel, not_types=('Land',)) if mode == 'blast' else replace(sel, types=('Creature',))
        look.update(n=0, until=sel.key())
    if mode == 'dissect':
        players = effects._players(plan, ctx, 'target')
        if not players:
            return True
        limited = effects._library(plan, players[0])[:max(0, int(ctx.get('x') or 0))]
        artifact = selectors.Selector(zones=(), card=True, types=('Artifact',)).key()
        artifact_at = effects._first_match(plan, ctx, limited, artifact, ctx['controller'])
        look['n'] = artifact_at + 1 if artifact_at is not None else len(limited)
    # Mandatory reveals complete without a decision; every later effect is inserted
    # into the native continuation before the exact reveal cleanup just queued.
    if not reveal_outcomes.reveal_outcome_top(plan, ctx, look):
        return False
    ids = list(ctx.get('looked') or [])
    if mode == 'dissect':
        ctx['found'] = ids[artifact_at] if artifact_at is not None and artifact_at < len(ids) else None
    steps: list[dict[str, Any]] = []
    if mode == 'charbelcher':
        found = ctx.get('found')
        n = len(ids) - int(found in ids)
        if isinstance(found, str) and found in ids and 'Mountain' in plan.ch(plan.state.cards[found]).subtypes:
            n *= 2
        steps = [{'do': 'damage', 'who': 'target', 'n': n}, {'do': 'rest_looked', 'to': 'bottom_any'}]
    elif mode == 'chroma':
        n = sum('U' in symbol.split('/') for cid in ids
                for symbol in re.findall(r'\{([^}]+)\}', plan.ch(plan.state.cards[cid]).mana_cost))
        steps = [{'do': 'mill', 'who': 'target', 'n': n}, {'do': 'rest_looked', 'to': 'bottom_any'}]
    elif mode == 'eruption' and ids:
        ch = plan.ch(plan.state.cards[ids[0]])
        creatures = selectors.Selector(types=('Creature',)).key()
        steps = [{'do': 'damage', 'who': 'target', 'n': int(ch.mana_value), 'with_next': True},
                 {'do': 'damage', 'who': 'controlled:target|' + creatures, 'n': int(ch.mana_value)}]
        if ch.is_land:
            steps.append({'do': 'spell_self_move', 'to': 'hand'})
    elif mode == 'candles':
        graveyard = plan.state.zones.get(f'{ctx["controller"]}:graveyard', [])
        same = bool(ids) and any(card_names.share(plan.ch(plan.state.cards[ids[0]]), plan.ch(plan.state.cards[c])) for c in graveyard)
        steps = [{'do': 'rest_looked', 'to': 'graveyard'}] if same else [{'do': 'draw', 'who': 'you', 'n': 1}]
    elif mode == 'trepan':
        steps = [{'do': 'pump', 'who': 'ref:event', 'p': len(ids), 't': 0},
                 {'do': 'rest_looked', 'to': 'graveyard', 'viewer': 'defending_player'}]
    elif mode in ('blast', 'whistle'):
        found = ctx.get('found')
        revealed_value = int(plan.ch(plan.state.cards[found]).mana_value) if isinstance(found, str) and found in ids else None
        if mode == 'whistle':
            steps.append({'do': 'pick_looked', 'which': 'that', 'require_found': True, 'to': 'hand'})
        steps.append({'do': 'rest_looked', 'to': 'bottom_random'})
        if revealed_value is not None:
            steps.append(_reflexive(revealed_value, counters=mode == 'whistle'))
    elif mode == 'raid':
        if ids and plan.ch(plan.state.cards[ids[0]]).is_creature:
            key = f'raid_pick_{ctx["next"]}'
            steps = [{'do': 'pick_looked', 'which': 'that', 'to': 'battlefield', 'as': key},
                     {'do': 'raid_arrived', 'ref': 'ref:' + key, 'as': key + '_arrived'}]
        else:
            steps = [{'do': 'rest_looked', 'to': 'graveyard'}]
    elif mode == 'dissect':
        if ctx.get('found'):
            steps.extend([{'do': 'pick_looked', 'which': 'that', 'require_found': True, 'to': 'battlefield'},
                          {'do': 'sacrifice', 'who': 'self'}])
        steps.append({'do': 'rest_looked', 'to': 'graveyard'})
    _insert(ctx, steps)
    return True


PRIMITIVES = {'reveal_snapshot': reveal_snapshot}


def _reflexive(n: int, *, counters: bool = False) -> dict[str, Any]:
    from app.rules import scripts

    target = selectors.Selector(types=('Creature',), controller='you').key() if counters else 'any'
    effect = {'do': 'add_counters', 'who': 'target', 'kind': '+1/+1', 'n': n} if counters else {'do': 'damage', 'who': 'target', 'n': n}
    return {'do': 'reflexive', 'cond': {'all': []},
            'ability': {'kind': 'triggered', 'trigger': 'reflexive', 'effects': [effect], 'optional': False, **scripts.target_fields(target)}}


def raid_arrived(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, delayed

    ids = [c for c in context.objects(plan, ctx, e['ref'].removeprefix(context.PREFIX)) if plan.state.cards[c].zone.endswith(':battlefield')]
    if ids:
        context.bind_objects(plan, ctx, e['as'], ids)
        _insert(ctx, [{'do': 'grant', 'who': 'ref:' + e['as'], 'keywords': ['haste'], 'duration': 'permanent'},
                      *delayed.wrap_when([{'do': 'sacrifice', 'who': 'ref:' + e['as']}], {'kind': 'step', 'step': 'end', 'whose': 'next'})])
    return True


def reveal_everyone(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import attachments, context

    shown: list[str] = []
    entries: list[dict[str, Any]] = []
    total = 0
    all_creatures = True
    for pid in plan.live():
        ids = list(plan.state.zones.get(f'{pid}:library', []))[:1]
        if ids:
            plan.do({'type': 'reveal', 'card_ids': ids}, actor=pid)
        for cid in ids:
            ch = plan.ch(plan.state.cards[cid])
            total += int(ch.mana_value)
            all_creatures &= ch.is_creature
            entries.append({'card': cid, 'player': pid, 'actor': pid, 'tapped': False})
        shown.extend(ids)
    key = f'reveal_everyone_{ctx["next"]}'
    context.bind_objects(plan, ctx, key, shown)
    cleanup = {'do': 'hide_revealed', 'refs': key, 'zone': 'library'}
    if e['mode'] == 'naya':
        _insert(ctx, [{'do': 'spell_rider', 'who': 'event_spell', 'n': total, 'riders': [{'kind': 'counter'}]}, cleanup])
        return True
    _insert(ctx, [cleanup])
    return attachments.enter(plan, entries, ctx) if all_creatures else True


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    if ability.kind != 'triggered':
        return None
    text = scripts.self_text(ability.text, ch.name)
    cases = {
        'Whenever equipped creature attacks, defending player reveals cards from the top of their library until they reveal a land card. The creature gets +1/+0 until end of turn for each card revealed this way. That player puts the revealed cards into their graveyard.': ('Whenever equipped creature attacks, you gain 1 life.', 'trepan'),
        'When you cast this spell, each player reveals the top card of their library. ~ enters with X +1/+1 counters on it, where X is the total mana value of all cards revealed this way.': ('When you cast this spell, you gain 1 life.', 'naya'),
        "At the beginning of your upkeep, each player reveals the top card of their library. If all cards revealed this way are creature cards, put those cards onto the battlefield under their owners' control.": ('At the beginning of your upkeep, you gain 1 life.', 'preserve'),
    }
    if text not in cases:
        return None
    native_text, mode = cases[text]
    native = scripts.define(replace(ability, text=native_text), ch)
    if native is None:
        return None
    return {**native, 'effects': [{'do': 'reveal_snapshot', 'mode': mode}]}


PRIMITIVES.update({'raid_arrived': raid_arrived})
