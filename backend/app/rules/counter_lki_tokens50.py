"""Death-created tokens copy the departed object's counters through native LKI effects."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('When ~ dies, if it had one or more counters on it, create a 0/0 green and blue Fractal creature token, '
        "then put ~'s counters on that token.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    native = TEXT.replace("put ~'s counters on that token", "put a copy of ~'s counters on it")
    return scripts.define(replace(ability, text=native), ch)
