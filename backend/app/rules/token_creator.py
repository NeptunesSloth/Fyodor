"""CR 111.2, 614.1a: this turn's token creation changes its creating player."""
from __future__ import annotations

from typing import Any


def parse(body: str) -> tuple[list[dict[str, Any]], None, bool] | None:
    text = body[:1].lower() + body[1:]
    if text != "each token that would be created under an opponent's control this turn is created under your control instead.":
        return None
    return ([{'do': 'replace_record', 'event': 'tokens', 'match': {'who': 'opponent'}, 'op': {'do': 'set_creator'}}], None, False)
