"""CR 702.168d, 118.7: disguise cost reductions are applied only when turning face up."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

from app.rules import mana as M
from app.rules import selectors

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics

_PATTERN = re.compile(r'^disguise (?P<cost>(?:\{[^}]+\})+)(?:\. this cost is reduced by \{(?P<n>\d+)\} '
                      r'for each (?P<what>[a-z -]+ cards? in your graveyard))?$', re.I)


def parse(line: str) -> tuple[str, int, str | None] | None:
    m = _PATTERN.fullmatch(line.strip().rstrip('.'))
    if m is None:
        return None
    if not m['what']:
        return m['cost'], 0, None
    phrase = m['what'].replace('instant and sorcery', 'instant or sorcery')
    sel = selectors.parse(phrase)
    if sel is None or not sel.card or sel.zones != ('graveyard',) or sel.zone_owner != 'you' or sel.player:
        return None
    return m['cost'], int(m['n']), sel.key()


def of(ch: Characteristics) -> tuple[str, int, str | None] | None:
    return next((found for a in ch.abilities if a.kind == 'keywords' and 'disguise' in a.keywords
                 and (found := parse(a.text)) is not None), None)


def reduced(state: GameState, card: CardInstance, printed: Characteristics, info: CardInfo) -> str:
    from app.rules.plan import Plan

    spec = of(printed)
    assert spec is not None
    cost, n, key = spec
    if key is None or not n:
        return cost
    count = len(selectors.candidates(Plan.view(state, card.controller, info), selectors.from_key(key), card.controller, card.id))
    base = M.parse_cost(cost)
    return replace(base, generic=max(0, base.generic - n * count)).text()
