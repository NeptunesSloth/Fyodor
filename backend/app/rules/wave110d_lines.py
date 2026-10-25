"""-- lines (wave 110D) -- whole abilities read as an equivalent native wording (same meaning, citations at each entry; CR 2026-09-25)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

# the Oracle line (the card's name as ~) -> the wording the grammar already reads, with the same meaning
_AS: dict[str, str] = {
    # Thelon of Havenwood: "each Fungus on the battlefield" is each permanent with the Fungus subtype (a selector reads permanents on the battlefield; 109.2)
    "{B}{G}, Exile a Fungus card from a graveyard: Put a spore counter on each Fungus on the battlefield.":
        "{B}{G}, Exile a Fungus card from a graveyard: Put a spore counter on each Fungus.",
    # Jeska, Thrice Reborn: a loyalty counter "for each time" = a number of counters equal to the number of times (122.6, 903.8)
    "~ enters with a loyalty counter on it for each time you've cast a commander from the command zone this game.":
        "~ enters with a number of loyalty counters on it equal to the number of times you've cast a commander from the command zone this game.",
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    native = _AS.get(scripts.self_text(ability.text, ch.name))
    return None if native is None else scripts.define(replace(ability, text=native), ch)
