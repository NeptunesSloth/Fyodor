"""-- if you do (wave 52A) -- counterspell riders that put the countered card to use (CR 2026-09-25).

* Delay: "Counter target spell. If the spell is countered this way, exile it with three time counters on it instead of putting it into its owner's graveyard. If it doesn't have
  suspend, it gains suspend." Exiled instead (608.2c: the counter's own destination), then suspended with those counters — the same two instructions "Exile target card …
  with two time counters on it. If it doesn't have suspend, it gains suspend." make (702.62b, suspend_grants.py).
* Transcendent Dragon: "If that spell is countered this way, exile it instead of putting it into its owner's graveyard, then you may cast it without paying its mana cost." The cast
  is a free cast of the card the counter exiled (608.2g; a spell not countered is still on the stack and is no card to cast, permissions._free_pool).
"""

from __future__ import annotations

import re

_SUSPENDED = re.compile(r"(If (?:that|the) spell is countered this way, exile it) with (an?|one|two|three|four|five|six|seven|eight|nine|ten) time counters? on it"
                        r"( instead of putting it into its owner's graveyard)\. If it doesn't have suspend, it gains suspend\.")
_THEN_CAST = re.compile(r"(If (?:that|the) spell is countered this way, exile it instead of putting it into its owner's graveyard), "
                        r"then you may cast it without paying its mana cost\.")


def rewrite(body: str) -> str:
    body = _SUSPENDED.sub(lambda m: f"{m[1]}{m[3]}. Suspend it with {m[2]} time counters.", body)
    return _THEN_CAST.sub(lambda m: f"{m[1]}. You may cast that card without paying its mana cost.", body)
