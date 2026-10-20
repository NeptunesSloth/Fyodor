"""Public name/number guesses, using exact native reveal and resolution continuations."""
from __future__ import annotations

from typing import Any

from app.rules import context, selectors
from app.rules.plan import Plan


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = body.strip().rstrip('.')
    named = selectors.Selector(zones=(), card=True, extras=('chosen_name',)).key()
    if text == ('Choose a card name. Target player reveals cards from the top of their library until a card with that name is revealed. '
                'If it is, that player puts the rest of the revealed cards into their graveyard and puts the card with the chosen name on top of their library. Otherwise, the player shuffles'):
        return [{'do': 'choose_value', 'who': 'you', 'what': 'card name'},
                {'do': 'look_top', 'n': 0, 'player': 'target', 'until': named, 'reveal': True, 'exact_look': True},
                {'do': 'finish_named_reveal'}], 'player', False
    if text == ('Choose a nonland card name and a number greater than 0. Target player reveals their library. '
                'If that library contains exactly the chosen number of cards with the chosen name, ~ deals 8 damage to that player. Then that player shuffles'):
        return [{'do': 'choose_value', 'who': 'you', 'what': 'nonland card name'},
                {'do': 'choose_value', 'who': 'you', 'what': 'number', 'typed_min': 1},
                {'do': 'reveal_guess', 'zone': 'library', 'sel': named, 'n': {'chosen_n': 1}}], 'player', False
    if text == ('Choose a number greater than 0 and a color. Target opponent reveals their hand. '
                'If that opponent reveals exactly the chosen number of cards of the chosen color, you draw a card'):
        colored = selectors.Selector(zones=(), card=True, extras=('chosen_color',)).key()
        return [{'do': 'choose_value', 'who': 'you', 'what': 'number', 'typed_min': 1},
                {'do': 'choose_value', 'who': 'you', 'what': 'color'},
                {'do': 'reveal_guess', 'zone': 'hand', 'sel': colored, 'n': {'chosen_n': 1}}], 'opponent', False
    return None


def _insert(ctx: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    ctx['effects'][ctx['next']:ctx['next']] = steps


def finish_named_reveal(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    if ctx.get('found'):
        # Keep the named object separate while the other cards move. These are
        # graveyard moves, not mill; then native library placement handles the top.
        context.bind_objects(plan, ctx, 'tunnel_found', [ctx['found']])
        _insert(ctx, [{'do': 'to_library', 'who': 'ref:tunnel_found', 'place': 'top'},
                      {'do': 'hide_revealed', 'refs': 'tunnel_found', 'zone': 'library'}])
        ctx['looked'] = [c for c in ctx.get('looked', []) if c != ctx['found']]
        return effects.rest_looked(plan, ctx, {'to': 'graveyard', 'viewer': 'target'})
    _insert(ctx, [{'do': 'shuffle_library', 'who': 'target'}])
    return True


def reveal_guess(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    players = effects._players(plan, ctx, 'target')
    if not players:
        return True
    pid = players[0]
    ids = list(plan.state.zones.get(f'{pid}:{e["zone"]}', []))
    if ids:
        plan.do({'type': 'reveal', 'card_ids': ids}, actor=pid)
    context.bind_objects(plan, ctx, 'guess_revealed', ids)
    sel = selectors.from_key(e['sel'])
    count = sum(selectors.matches(plan, sel, plan.state.cards[c], plan.ch(plan.state.cards[c]),
                                  ctx['controller'], ctx.get('source_card')) for c in ids)
    steps: list[dict[str, Any]] = []
    if count == e['n']:
        steps.append({'do': 'damage', 'who': 'target', 'n': 8} if e['zone'] == 'library'
                     else {'do': 'draw', 'who': 'you', 'n': 1})
    steps.append({'do': 'shuffle_library', 'who': 'target'} if e['zone'] == 'library'
                 else {'do': 'hide_revealed', 'refs': 'guess_revealed', 'zone': 'hand'})
    _insert(ctx, steps)
    return True


PRIMITIVES = {'finish_named_reveal': finish_named_reveal, 'reveal_guess': reveal_guess}
