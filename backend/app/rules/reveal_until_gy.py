"""-- trigger other (wave 52B) -- "Each opponent reveals cards from the top of their library until they reveal a land card, then puts those cards into their graveyard." (Consuming Aberration).

* 701.20a / 701.20b: each opponent reveals cards from the top of their own library, one at a time, down to and including the first card of the kind (all of the library if
  it has none); the cards are shown to everyone. 400.3: they are then put into that library's owner's graveyard (a "put", not a mill: 701.17a needs the word).
* Every opponent does it for their own library, one after the other in turn order; nothing is chosen, so there is nothing to pause for. A library with no card of the kind
  loses all its cards (nothing is found).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_EACH = re.compile(r"^each opponent reveals cards from the top of their library until they reveal an? (?P<what>[a-z ]+? card), then puts those cards into their graveyard\.$")


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    from app.rules import language

    m = _EACH.match(body)
    if m is None:
        return None
    try:
        until = language._card_sel(m["what"])
    except language._Fail:
        return None
    return [{"do": "reveal_until_gy", "who": "each_opponent", "until": until}], None, False


def reveal_until_gy(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.effects import _first_match, _players

    for pid in _players(plan, ctx, e["who"]):
        library = list(plan.state.zones.get(f"{pid}:library", []))
        at = _first_match(plan, ctx, library, e["until"], ctx["controller"])
        top = library if at is None else library[: at + 1]
        if not top:
            continue
        plan.do({"type": "reveal_top", "player": pid, "count": len(top)}, actor=pid)
        for start in range(0, len(top), 250):  # (a move names at most 250 cards)
            plan.do({"type": "move", "card_ids": top[start:start + 250], "to": {"player": pid, "zone": "graveyard"}}, actor=pid)
    return True


PRIMITIVES: dict[str, Any] = {"reveal_until_gy": reveal_until_gy}
