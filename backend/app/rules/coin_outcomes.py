"""Replacement-aware simultaneous coin groups; only kept results produce game events."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

BUDGET = 24


def definition(text: str) -> dict[str, Any] | None:
    text = re.sub(r'^Two-Headed Coin — ', '', text)
    modes = {"If you would flip a coin, instead flip two coins and ignore one.": 'thumb',
             'The first time you flip one or more coins each turn, those coins come up heads and you win those flips.': 'edgar'}
    return {'kind': 'static', 'static': 'coin_replacement', 'mode': modes[text], 'effects': []} if text in modes else None


def _replacements(plan: Plan, player: str) -> list[dict[str, str]]:
    from app.rules import scripts

    out = []
    for card in plan.state.cards.values():
        if card.zone != player + ':battlefield' or card.controller != player:
            continue
        for index, d in scripts.definitions(plan.ch(card)).items():
            if d.get('static') == 'coin_replacement':
                out.append({'key': f'{plan.oid(card)}:{index}', 'object': plan.oid(card), 'mode': d['mode'], 'name': card.name or 'Coin replacement'})
    return out


def _seen(plan: Plan, player: str) -> bool | None:
    rules, turn = plan.rules, plan.state.turn.number
    if rules.coin_history_from_turn is None:
        rules.coin_history_from_turn = turn + 1
    if rules.coin_flipped.get(player) == turn:
        return True
    if rules.coin_history_from_turn is not None and turn >= rules.coin_history_from_turn:
        return False
    # Native old public logs can establish a previous flip, or a complete turn with none.
    for entry in plan.state.log:
        if entry.turn == turn and entry.actor == player and any(re.match(r' flipped (?:a coin|\d+ coins):', p.t or '') for p in entry.parts):
            return True
    if plan.state.log and (plan.state.log[0].turn < turn or plan.state.log[0].seq <= 1):
        return False
    return None


def _pause(plan: Plan, ctx: dict[str, Any], frame: dict[str, Any], *, phase: str, player: str,
           prompt: str, options: list[tuple[str, str]], index: int = 0) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    decide(plan, player=player, kind='choose_one', prompt=prompt,
           options=[DecisionOption(id=k, label=v) for k, v in options],
           resume={'step': 'coin_group', 'ctx': ctx, 'frame': frame, 'phase': phase, 'index': index})
    return False


def group(plan: Plan, ctx: dict[str, Any], coins: list[dict[str, Any]], *, face: bool = False,
          frame: dict[str, Any] | None = None) -> bool:
    """One simultaneous group, including all physical results before ignored-result choices."""
    from app.game.rules_state import emit, track

    if frame is None:
        order = plan.live()
        if plan.active in order:
            first = order.index(plan.active)
            order = order[first:] + order[:first]
        coins = sorted(coins, key=lambda c: order.index(c['player']) if c['player'] in order else len(order))
        players = list(dict.fromkeys(c['player'] for c in coins))
        frame = {'coins': coins, 'players': players, 'replacements': {p: _replacements(plan, p) for p in players},
                 'first': {}, 'nodes': [], 'roots': [], 'leaves': [], 'expand': 0, 'draw': 0, 'reduce': -1, 'face': face}
    for player in frame['players']:
        if player in frame['first']:
            continue
        seen = _seen(plan, player)
        if seen is None and any(d['mode'] == 'edgar' for d in frame['replacements'][player]):
            return _pause(plan, ctx, frame, phase='history', player=player,
                          prompt='Restore missing public coin history: have you flipped any coins this turn?',
                          options=[('yes', 'Already flipped this turn'), ('no', 'No previous flips this turn')])
        frame['first'][player] = not bool(seen)
    if not frame['nodes']:
        for coin in frame['coins']:
            frame['roots'].append(len(frame['nodes']))
            frame['nodes'].append({'player': coin['player'], 'applied': [], 'forced': False})
    work = 0
    while frame['expand'] < len(frame['nodes']):
        i = frame['expand']
        node = frame['nodes'][i]
        eligible = [d for d in frame['replacements'][node['player']] if d['key'] not in node['applied']
                    and (d['mode'] != 'edgar' or frame['first'][node['player']])]
        if len(eligible) > 1 and 'chosen' not in node:
            return _pause(plan, ctx, frame, phase='replace', player=node['player'], index=i,
                          prompt='Choose the next coin replacement to apply (616.1).',
                          options=[(d['key'], d['name']) for d in eligible])
        chosen_key = node.pop('chosen', None)
        selected = next((d for d in eligible if d['key'] == chosen_key), eligible[0] if eligible else None)
        if selected is not None:
            node['applied'].append(selected['key'])
            if selected['mode'] == 'edgar':
                node['forced'] = True
            else:
                node['children'] = [len(frame['nodes']), len(frame['nodes']) + 1]
                frame['nodes'] += [{'player': node['player'], 'applied': list(node['applied']), 'forced': node['forced']} for _ in range(2)]
                frame['expand'] += 1
        else:
            frame['leaves'].append(i)
            frame['expand'] += 1
        work += 1
        if work >= BUDGET:
            return _checkpoint(plan, ctx, frame)
    while frame['draw'] < len(frame['leaves']):
        node = frame['nodes'][frame['leaves'][frame['draw']]]
        rolled = plan.do({'type': 'coin', 'count': 1}, actor=node['player'])
        heads = bool(rolled.r.results[0])  # type: ignore[union-attr]
        node['heads'] = True if node['forced'] else heads
        node['won'] = node['heads'] if node['forced'] or not frame['face'] else None
        frame['draw'] += 1
        work += 1
        if work >= BUDGET:
            return _checkpoint(plan, ctx, frame)
    if frame['reduce'] < 0:
        frame['reduce'] = len(frame['nodes']) - 1
    while frame['reduce'] >= 0:
        i = frame['reduce']
        node = frame['nodes'][i]
        if 'children' in node:
            children = [frame['nodes'][j] for j in node['children']]
            if (children[0]['heads'], children[0]['won']) != (children[1]['heads'], children[1]['won']) and 'keep' not in node:
                return _pause(plan, ctx, frame, phase='ignore', player=node['player'], index=i,
                              prompt='Choose the result to keep; the other flip is ignored.',
                              options=[(str(j), 'Heads' if child['heads'] else 'Tails') for j, child in enumerate(children)])
            chosen = children[node.get('keep', 0)]
            node.update(heads=chosen['heads'], won=chosen['won'])
        frame['reduce'] -= 1
    outcomes = [{**coin, 'heads': frame['nodes'][root]['heads'], 'won': frame['nodes'][root]['won']}
                for coin, root in zip(frame['coins'], frame['roots'], strict=True)]
    ctx['coin_outcomes'] = outcomes
    ctx['coin'] = outcomes[-1]['heads'] if outcomes else None
    ctx['flips'] = [c['heads'] for c in outcomes]
    for outcome in outcomes:
        if outcome['won'] is not None:
            emit(plan.state, 'designation', counter='coin_flip', player=outcome['player'], amount=int(outcome['won']), source=ctx.get('source_object'))
    from app.rules import randomness

    for flipper in dict.fromkeys(outcome['player'] for outcome in outcomes):  # -- random choices (wave MBC-D) -- each flipper flipped one or more coins
        randomness.noted(plan, 'coin', flipper)  # (heads/tails flips too: 705.2 has no winner for them, but they are flips)
    if any(n['forced'] for n in frame['nodes']):
        plan.note('The first coin group comes up heads and its flipper wins (Edgar).')
    track(plan.state)  # Seal emitted kept-result facts before any following instruction can pause.
    return True


def _checkpoint(plan: Plan, ctx: dict[str, Any], frame: dict[str, Any]) -> bool:
    return _pause(plan, ctx, frame, phase='continue', player=ctx['controller'],
                  prompt='Continue resolving the coin group (no priority or state-based actions).',
                  options=[('continue', 'Continue resolving')])


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    r = d.resume
    frame, ctx = r['frame'], r['ctx']
    if r['phase'] == 'history':
        frame['first'][d.player] = chosen[0] == 'no'
        if chosen[0] == 'yes':
            plan.rules.coin_flipped[d.player] = plan.state.turn.number
        plan.note('Restored public first-coin history.', actor=d.player)
    elif r['phase'] == 'replace':
        frame['nodes'][r['index']]['chosen'] = chosen[0]
    elif r['phase'] == 'ignore':
        frame['nodes'][r['index']]['keep'] = int(chosen[0])
    if group(plan, ctx, [], frame=frame):
        after = ctx.pop('coin_after', None)
        if after is None or effects.PRIMITIVES[after['do']](plan, ctx, after):
            effects.continue_effects(plan, ctx)


RESUME = {'coin_group': resume}
