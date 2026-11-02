"""Explicit look authorization for exact face-down exile objects (406.3)."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_WISHES = ('Exile the top three cards of your library face down. You may look at those cards for as long as they remain exiled. '
           'Until your next turn, you may play those cards. At the beginning of your next upkeep, put any of those cards you didn\'t play into your graveyard.')
_IXHEL = ('Each opponent who has three or more poison counters exiles the top card of their library face down. '
          'You may look at and play those cards for as long as they remain exiled, and you may spend mana as though it were mana of any color to cast those spells.')


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = re.sub(r'\s+', ' ', body).strip().lower()
    for wording, mode in [(_WISHES, 'wishes'), (_IXHEL, 'corrupted')]:
        if text == wording.lower():
            return [{'do': 'linked_exile_grant', 'mode': mode}], None, False
    return None


def refresh(plan: Plan) -> None:
    """Live static authority grants enduring look rights, never enduring play rights."""
    from app.rules import exiled_with, scripts

    def looks(source: Any) -> bool:
        return any(d.get('static') == 'linked_look' or d.get('linked_look') for d in scripts.definitions(plan.ch(source)).values())

    # -- big boards (perf) -- first, in one read pass (Plan.reading: each permanent derived once, the statics table read once), whether any
    # permanent has such an ability at all. With none, the loop below would only derive every permanent (outside a pass: the square of
    # the board, twice per action) and do nothing, so there is nothing to do.
    with plan.reading():
        if not any(looks(s) for s in plan.state.cards.values()
                   if s.ability is None and s.zone.endswith(':battlefield') and not s.face_down):
            return
    for source in list(plan.state.cards.values()):
        if source.ability is not None or not source.zone.endswith(':battlefield') or source.face_down:
            continue
        for d in scripts.definitions(plan.ch(source)).values():
            if d.get('static') != 'linked_look' and not d.get('linked_look'):
                continue
            ctx: dict[str, Any] = {'source_object': plan.oid(source.id), 'controller': source.controller}
            for e in d.get('effects') or []:
                if e.get('do') == 'borrowed_link_scope':
                    ctx['borrowed_link_scope'] = e['scope']
            cards = [oid.rsplit('.', 1)[0] for oid in plan.rules.exiled_with.get(exiled_with.link_key(ctx), [])
                     if exiled_with._in_exile(plan, oid)]
            unseen = [cid for cid in cards if source.controller not in plan.state.cards[cid].revealed_to]
            if unseen:
                plan.do({'type': 'reveal', 'card_ids': unseen, 'to': [source.controller]}, actor=source.controller)


def exile_grant(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, delayed, effects, permissions

    pid = ctx['controller']
    if e['mode'] == 'wishes':
        players = [pid]
    else:
        players = [p for p in effects._players(plan, ctx, 'each_opponent') if plan.state.players[p].resources.get('poison', 0) >= 3]
    cards = [c for p in players for c in list(plan.state.zones.get(f'{p}:library', []))[:3 if e['mode'] == 'wishes' else 1]]
    effects.exile_cards(plan, ctx, {'do': 'exile', 'face_down': True, 'blind': True}, cards)
    cards = [c for c in cards if c in plan.state.cards and plan.state.cards[c].zone.endswith(':exile')]
    if cards:
        plan.do({'type': 'reveal', 'card_ids': cards, 'to': [pid]}, actor=pid)
    context.bind_objects(plan, ctx, 'linked_exile_grant', cards)
    permissions.grant_play(plan, ctx, {'who': 'ref:linked_exile_grant', 'play': True, 'cast': True, 'from_exile': True,
                                     'until': 'next_turn' if e['mode'] == 'wishes' else 'permanent',
                                     'spend': 'color' if e['mode'] == 'corrupted' else ''})
    if e['mode'] == 'wishes':
        delayed.create_plain(plan, pid, ctx.get('source_card') or '', ctx.get('source_object') or '', ctx.get('name') or 'Three Wishes',
                             {'kind': 'step', 'step': 'upkeep', 'whose': 'you'},
                             [{'do': 'bind_refs', 'refs': {'linked_exile_grant': ctx['refs']['linked_exile_grant']}},
                              {'do': 'return_card', 'who': 'ref:linked_exile_grant', 'to': 'graveyard'}])
    return True


PRIMITIVES = {'linked_exile_grant': exile_grant}
