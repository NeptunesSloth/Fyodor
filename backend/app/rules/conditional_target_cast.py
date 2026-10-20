"""CR 608.2g: a conditional paid cast during resolution, then a cast restriction."""
from __future__ import annotations

import re
from typing import Any

_PATTERN = re.compile(
    r"Choose target (?P<what>[^.]+ card) in your graveyard\. "
    r"If you haven't cast a spell this turn, you may cast that card\. "
    r"If you do, you can't cast additional spells this turn\."
)


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import selectors

    m = _PATTERN.fullmatch(body.strip())
    if m is None:
        return None
    sel = selectors.parse(m['what'] + ' in your graveyard')
    if sel is None or not sel.card or sel.player is not None or sel.zones != ('graveyard',) or sel.zone_owner != 'you':
        return None
    return ([{'do': 'choose_targets', 'who': 'target'},
             {'do': 'only_if', 'cond': {'not': {'history': 'spells', 'n': 1}}, 'skip': 3},
             {'do': 'free_cast', 'zone': 'target', 'filter': None, 'optional': True, 'paid': True,
              'mv': None, 'n': 1, 'did': 'conditional_cast'},
             {'do': 'only_if', 'cond': {'succeeded': 'conditional_cast'}, 'skip': 1},
             {'do': 'cast_limit', 'who': 'you', 'until': 'turn'}], sel.key(), False)
