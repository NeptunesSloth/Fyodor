"""-- wave 110O -- exact Oracle wordings of single cards, read as native instructions or built from parts of them.

Each entry matches one whole ability's (or spell body's) Oracle text exactly and nothing else; any other wording stays unsupported.
Researched against the Comprehensive Rules of 2026-09-25.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

Context = dict[str, Any]

# spell body (exact) -> the native wording
REWRITES: dict[str, str] = {}


_REMEMBRANCE = "Shuffle Serene Remembrance and up to three target cards from a single graveyard into their owners' libraries."


def parse(body: str) -> Any:
    from app.rules import scripts

    if body.strip() == _REMEMBRANCE.replace("Serene Remembrance", "~"):  # 701.24a: the spell and the cards are shuffled in, each owner's library shuffled
        own = scripts.parse_effects("Shuffle ~ into its owner's library.")
        cards = scripts.parse_effects("Shuffle up to three target cards from a single graveyard into their owner's library.")
        assert own and cards
        return [*own[0], *cards[0]], cards[1], False
    return scripts.parse_effects(same) if (same := REWRITES.get(body.strip())) is not None else None


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    del text
    return None


PRIMITIVES: dict[str, Any] = {}
RESUME: dict[str, Any] = {}
