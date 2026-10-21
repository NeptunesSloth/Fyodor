"""CR 608.2f, 701.14: captured opposing creatures and simultaneous one-to-one fights."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules import selectors
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'token_fight_pairs'
PREY = 'fight_pair_opponents'
TOKENS = 'fight_pair_tokens'


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import token_grammar, values

    m = re.fullmatch(r'For each (?P<what>creature your opponents control), (?P<create>create a .+? creature token)\. '
                     r'Each of those tokens fights a different one of those creatures\.', body)
    if m is None:
        return None
    sel = selectors.parse(m['what'])
    count = values.parse_count('the number of creatures your opponents control')
    created = token_grammar.parse(m['create'])
    if sel is None or count is None or not created or len(created) != 1 or created[0]['do'] != 'create_token':
        return None
    return ([{**created[0], 'n': count, 'note_group': {'as': PREY, 'who': sel.key()}, 'as': TOKENS},
             {'do': STEP, 'prey': 'ref:' + PREY, 'tokens': 'ref:' + TOKENS}], None, False)


def live_creatures(plan: Plan, ctx: dict[str, Any], binding: str) -> list[str]:
    from app.rules import effects

    return [cid for cid in effects._cards(plan, ctx, binding)
            if plan.state.cards[cid].zone.endswith(':battlefield') and plan.ch(plan.state.cards[cid]).is_creature]


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    memory = ctx.setdefault('_token_fight_pairs', {})
    key = str(ctx['next'])
    if key not in memory:
        prey = live_creatures(plan, ctx, e['prey'])
        tokens = live_creatures(plan, ctx, e['tokens'])
        memory[key] = {'prey': prey, 'tokens': tokens, 'pairs': [], 'n': min(len(prey), len(tokens)),
                       'victims': prey if len(tokens) >= len(prey) else None}
    progress = memory[key]
    if progress['victims'] is None:
        if not progress['n']:
            return True
        decide(plan, player=ctx['controller'], kind='choose_cards', prompt='Choose the opposing creatures that will fight',
               options=[DecisionOption(id=cid, label=plan.state.cards[cid].name or 'Creature', card_id=cid) for cid in progress['prey']],
               min_choices=progress['n'], max_choices=progress['n'],
               resume={'step': STEP, 'ctx': ctx, 'e': e, 'key': key, 'stage': 'victims'})
        return False
    if len(progress['pairs']) < progress['n']:
        victim = progress['victims'][len(progress['pairs'])]
        used = {p[0] for p in progress['pairs']}
        available = [cid for cid in progress['tokens'] if cid not in used]
        decide(plan, player=ctx['controller'], kind='choose_one',
               prompt=f"Choose a token to fight {plan.state.cards[victim].name}",
               options=[DecisionOption(id=cid, label=plan.state.cards[cid].name or 'Token', card_id=cid) for cid in available],
               resume={'step': STEP, 'ctx': ctx, 'e': e, 'key': key, 'stage': 'fighter', 'victim': victim})
        return False
    hits = []
    notes = []
    for a, b in progress['pairs']:
        if any(cid not in plan.state.cards or not plan.state.cards[cid].zone.endswith(':battlefield')
               or not plan.ch(plan.state.cards[cid]).is_creature for cid in (a, b)):
            continue
        # References were captured before creation, and no priority is granted during choices.
        if a not in live_creatures(plan, ctx, e['tokens']) or b not in live_creatures(plan, ctx, e['prey']):
            continue
        ca, cb = plan.ch(plan.state.cards[a]), plan.ch(plan.state.cards[b])
        pa, pb = max(0, ca.pt[0]) if ca.pt else 0, max(0, cb.pt[0]) if cb.pt else 0
        hits.extend([(effects._card_source(plan, a), b, pa), (effects._card_source(plan, b), a, pb)])
        notes.append((f'{ca.name} fights {cb.name}', [a, b]))
    return effects._deal(plan, ctx, hits, e, before=tuple(notes))


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    r = d.resume
    progress = r['ctx']['_token_fight_pairs'][r['key']]
    if r['stage'] == 'victims':
        if len(chosen) != progress['n'] or len(set(chosen)) != len(chosen) or any(cid not in progress['prey'] for cid in chosen):
            raise ActionError('Choose distinct opposing creatures')
        progress['victims'] = list(chosen)
    else:
        used = {p[0] for p in progress['pairs']}
        if len(chosen) != 1 or chosen[0] not in progress['tokens'] or chosen[0] in used:
            raise ActionError('Choose an unused created creature token')
        progress['pairs'].append([chosen[0], r['victim']])
    if run(plan, r['ctx'], r['e']):
        effects.continue_effects(plan, r['ctx'])


PRIMITIVES = {STEP: run}
