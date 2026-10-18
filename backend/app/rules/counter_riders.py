"""-- if you do (wave 52A) -- counterspell riders that put the countered card to use (CR 2026-09-25).

* Delay: "Counter target spell. If the spell is countered this way, exile it with three time counters on it instead of putting it into its owner's graveyard. If it doesn't have
  suspend, it gains suspend." Exiled instead (608.2c: the counter's own destination), then suspended with those counters — the same two instructions "Exile target card …
  with two time counters on it. If it doesn't have suspend, it gains suspend." make (702.62b, suspend_grants.py).
* Transcendent Dragon: "If that spell is countered this way, exile it instead of putting it into its owner's graveyard, then you may cast it without paying its mana cost." The cast
  is a free cast of the card the counter exiled (608.2g; a spell not countered is still on the stack and is no card to cast, permissions._free_pool).
"""

from __future__ import annotations

import re
from typing import Any

_SUSPENDED = re.compile(r"(If (?:that|the) spell is countered this way, exile it) with (an?|one|two|three|four|five|six|seven|eight|nine|ten) time counters? on it"
                        r"( instead of putting it into its owner's graveyard)\. If it doesn't have suspend, it gains suspend\.")
_THEN_CAST = re.compile(r"(If (?:that|the) spell is countered this way, exile it instead of putting it into its owner's graveyard), "
                        r"then you may cast it without paying its mana cost\.")


def rewrite(body: str) -> str:
    body = _SUSPENDED.sub(lambda m: f"{m[1]}{m[3]}. Suspend it with {m[2]} time counters.", body)
    return _THEN_CAST.sub(lambda m: f"{m[1]}. You may cast that card without paying its mana cost.", body)


# * Counterbalance: "Whenever an opponent casts a spell, you may reveal the top card of your library. If you do, counter that spell if it has the same mana value as the revealed
#   card." 608.2d: the controller chooses once whether to reveal; the card stays on top of the library (701.20a); the spell is countered when its mana value (a spell on the stack
#   counts its X, 202.3e) is equal to the revealed card's (a land card has mana value 0, 202.3).
_COUNTERBALANCE = re.compile(r"^you may reveal the top card of your library\. if you do, counter that spell if it has the same mana value as the revealed card\.?$", re.I)


def counterbalance(body: str, it: str | None) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if it != "event_spell" or _COUNTERBALANCE.match(body.strip()) is None:
        return None
    return [{"do": "may_rest"}, {"do": "look_top", "n": 1, "player": "you", "reveal": True, "as": "e0"},
            {"do": "only_if", "cond": {"object": "event", "stat": "mana_value", "op": "==", "n": {"mana_value": "ref:e0"}}, "skip": 1},
            {"do": "counter", "who": "event_spell"}], None, False
