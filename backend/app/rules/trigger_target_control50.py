"""The exact optional tap target retains its native resolution-time controller condition."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = ('When this creature enters, tap up to one target creature. '
        'If an opponent controls that creature, put a stun counter on it.')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != 'triggered' or ability.text != TEXT:
        return None
    return scripts.define(replace(ability, text=TEXT.replace(
        'an opponent controls that creature', "you don't control it")), ch)
