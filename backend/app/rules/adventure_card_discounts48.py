"""Count qualifying physical cards once, across the exact printed discount zones."""
from __future__ import annotations

from typing import Any

from app.rules import selectors


def value(phrase: str) -> dict[str, Any] | None:
    text = phrase.strip().lower()
    if text == "the number of cards in your graveyard that are instant cards, sorcery cards, and/or have an adventure":
        base = selectors.Selector(card=True, zones=("graveyard",), zone_owner="you")
    elif text == "card you own in exile and in your graveyard that's an instant card, a sorcery card, or a card that has an adventure":
        base = selectors.Selector(card=True, zones=("graveyard", "exile"), owner="you")
    else:
        return None
    from dataclasses import replace

    spells = replace(base, types=("Instant", "Sorcery"))
    adventurers = replace(base, extras=("has_adventure",))
    union = selectors.Selector(zones=base.zones, either=(spells.key(), adventurers.key()))
    return {"count": union.key()}
