"""CR 608.2h: a nontargeted counter recipient uses an exiled creature's battlefield power."""
from __future__ import annotations

import re
from typing import Any

_PATTERN = re.compile(r'Exile target creature\. Put X \+1/\+1 counters on a (?P<what>(?:commander )?creature) you control, '
                      r'where X is the power of the creature exiled this way\.')


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    m = _PATTERN.fullmatch(body.strip())
    if m is None:
        return None
    found = scripts._parse_effects_plain(f"Put one +1/+1 counter on a {m['what']} you control.")
    if found is None or found[1] is not None or len(found[0]) != 2:
        return None
    choose, counters = found[0]
    return ([{'do': 'exile', 'who': 'target', 'as': 'exiled_power_source'}, choose,
             {**counters, 'n': {'power': 'ref:exiled_power_source'}}], 'creature', False)
