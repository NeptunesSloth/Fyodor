"""Counters whose amount is each recipient's own current characteristic (608.2h)."""
from __future__ import annotations

import re
from typing import Any

_FORM = re.compile(r"put a number of (?P<kind>[+-]\d+/[+-]\d+) counters on "
                   r"(?P<who>each (?:other )?creature you control) equal to that creature's (?P<stat>power|toughness)", re.I)


def parse(text: str) -> tuple[list[dict[str, Any]], Any] | None:
    m = _FORM.fullmatch(text)
    if m is None:
        return None
    from app.rules import selectors

    selector = selectors.parse(re.sub(r'^each ', '', m['who'], flags=re.I))
    if selector is None:
        return None
    return [{'do': 'add_counters', 'who': selector.key(), 'kind': m['kind'],
             'n': {'recipient_stat': m['stat'].lower()}}], None
