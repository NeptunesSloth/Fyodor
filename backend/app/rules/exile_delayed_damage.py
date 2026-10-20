"""Exact exile batches with temporary play permission and later remaining-card damage."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_BODY = re.compile(r"Exile the top X cards of your library, where X is the number of (?P<count>creatures you control with power \d+ or greater)\. "
                   r"You may play those cards until your next end step\. At the beginning of your next end step, "
                   r"(?:~|this creature) deals (?P<n>\d+) damage to each opponent for each of those cards that are still exiled\.")


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import selectors

    m = _BODY.fullmatch(body[:1].upper() + body[1:])
    if m is None or (sel := selectors.parse(m['count'])) is None:
        return None
    return ([{'do': 'exile_top', 'n': {'count': sel.key()}, 'as': 'exile_batch'},
             {'do': 'grant_play', 'who': 'ref:exile_batch', 'play': True, 'cast': True,
              'until': 'next_end_step', 'from_exile': True},
             {'do': 'delay_exile_damage', 'ref': 'exile_batch', 'n': int(m['n'])}], None, False)


def schedule(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from copy import deepcopy

    from app.rules import delayed

    refs = {e['ref']: deepcopy((ctx.get('refs') or {}).get(e['ref']) or {'kind': 'objects', 'objects': []})}
    delayed.create_plain(plan, ctx['controller'], ctx['source_card'], ctx['source_object'], ctx.get('name') or 'A creature',
                         {'kind': 'step', 'step': 'end', 'whose': 'you'},
                         [{'do': 'bind_refs', 'refs': refs},
                          {'do': 'damage', 'who': 'each_opponent',
                           'n': {'times': [e['n'], {'live_ref_count': e['ref'], 'zone': 'exile'}]}}])
    return True


PRIMITIVES = {'delay_exile_damage': schedule}
