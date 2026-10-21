"""Player-event qualifiers: controlling a specified permanent when the event happens."""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


def parse(text: str, parse_inner: Callable[[str], dict[str, Any] | None]) -> dict[str, Any] | None:
    from app.rules import selectors

    m = re.fullmatch(r"(?P<who>an opponent|a player|you) who controls (?P<what>an? .+?) (?P<event>draws? a card|gains? life)(?P<tail> during (?:their|your) turn)?", text)
    if m is None:
        return None
    what = m['what']
    named = re.fullmatch(r"(.+?) named (.+)", what)
    if named is not None:
        what = named[1]
    sel = selectors.parse(re.sub(r'^an? ', '', what))
    if sel is None or sel.player is not None or sel.card:
        return None
    if named is not None:
        sel = selectors.replace(sel, extras=(*sel.extras, 'named_self' if named[2] == '~' else 'name:' + named[2]))
    inner = parse_inner(m['who'] + ' ' + m['event'] + (m['tail'] or ''))
    return {**inner, 'player_controls': sel.key()} if inner is not None else None
