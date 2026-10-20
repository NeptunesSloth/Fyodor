"""CR 601.2i / 608.2i: a named spell cast earlier this game, and its alternative resolution."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.cards.names import normalize_name

if TYPE_CHECKING:
    from app.rules.plan import Plan

STEP = 'named_recast_win'


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    match = re.fullmatch(r"If this spell was cast from your hand and you've cast another spell named (?P<name>~|[A-Z][^\n]+?) "
                         r"this game, you win the game\. Otherwise, put ~ into its owner's library seventh from the top and you gain 7 life\.", body.strip())
    if match is None:
        return None
    return ([{'do': STEP, **({'name': match['name']} if match['name'] != '~' else {})}], None, False)


def resolve(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import card_names, values, win_game

    player = ctx['controller']
    record = plan.rules.payments.get(ctx.get('source_object') or '')
    found = values._object(plan, ctx, 'self')
    counts = plan.rules.named_casts_game.get(player, {})
    names = [e['name']] if e.get('name') else card_names.names_of(found[1]) if found is not None else []
    log = plan.rules.turn_log
    current = next((note for note in log.casts if note.object_id == ctx.get('source_object')), None) if log else None
    cast_names = {normalize_name(name) for name in current.names} if current is not None and current.names is not None else None
    prior = any(counts.get(normalize_name(name), 0) >= 1 + int(cast_names is None or normalize_name(name) in cast_names)
                for name in names)
    own_hand = (record is not None and record.cast_from == 'hand' and record.controller == player
                and found is not None and found[0].owner == player)
    if own_hand and prior:
        return win_game.win_game(plan, ctx, {'who': 'you'})
    at = int(ctx.get('next') or 0)
    ctx['effects'] = [*ctx['effects'][:at], {'do': 'to_library', 'who': 'self_stack', 'place': 7},
                      {'do': 'gain_life', 'who': 'you', 'n': 7}, *ctx['effects'][at:]]
    return True


PRIMITIVES = {STEP: resolve}
