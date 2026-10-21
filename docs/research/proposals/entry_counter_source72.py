"""Entry replacement counter amounts read from the existing source permanent."""
from __future__ import annotations

from typing import Any


def definition(text: str) -> dict[str, Any] | None:
    if text != ('Each other creature you control enters with an additional X +1/+1 counters on it, '
                'where X is the number of +1/+1 counters on ~.'):
        return None
    from app.rules import replace_grammar

    result = replace_grammar.parse('Each other creature you control enters with an additional +1/+1 counter on it.')
    assert result is not None
    result['op']['times'] = {'counters': '+1/+1', 'on': 'self'}
    return result
