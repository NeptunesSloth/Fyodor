"""-- Star Trek one-offs (wave 112T) -- Star Trek cards whose last missing line isn't one of the set's mechanics, and the ones the Star Trek
release notes (https://magic.wizards.com/en/news/feature/star-trek-release-notes) now settle. CR 2026-09-25.

* Tell Me What You See: "target opponent may have you draw a card. If they don't, they lose 4 life and you surveil 1." The target opponent
  chooses as the ability resolves (608.2d), as for Bane, Lord of Darkness (wave110n_cards) and Terrapact Intimidator (counters100j).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

_TELL = "When ~ enters, target opponent may have you draw a card. If they don't, they lose 4 life and you surveil 1."


def _tell(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    head = scripts.define(replace(ability, text="When ~ enters, target opponent loses 4 life and you surveil 1."), ch)
    if head is None or [e.get("do") for e in head["effects"]] != ["lose_life", "surveil"]:
        return None
    return {**head, "effects": [
        {"do": "optional_payment", "who": "target", "ask": "Have its controller draw a card (if you don't, you lose 4 life and they surveil 1)",
         "bind": "tell112t"},
        {"do": "only_if", "cond": {"succeeded": "tell112t"}, "skip": 1},
        {"do": "draw", "who": "you", "n": 1},
        {"do": "only_if", "cond": {"succeeded": "tell112t", "negate": True}, "skip": len(head["effects"])},
        *head["effects"]]}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind == "triggered" and ability.index < 100 and scripts.self_text(ability.text, ch.name) == _TELL:
        return _tell(ability, ch)
    return None
