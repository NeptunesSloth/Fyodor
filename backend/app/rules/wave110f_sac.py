"""Brutal Suppression, Drought (wave 110F): a static additional cost of "Sacrifice a land / a Swamp" on spells and activated abilities.

118.8: an additional cost is paid with the rest (601.2f-h, 602.2b). 107.4e / 107.4f: a hybrid or Phyrexian symbol with a B half is a black mana symbol.
Only the spell tax is automated. The taxes on activated abilities (Brutal Suppression, Drought's second line) stay unsupported (PARTIAL): mana
abilities, cycling, unearth, equip ... each have their own cost route, and refusing a legal activation would forbid a legal play, so the table pays."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.costs import AbilityCost

DROUGHT_SPELL = 'Spells cost an additional "Sacrifice a Swamp" to cast for each black mana symbol in their mana costs.'


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind == "static" and scripts.self_text(ability.text, ch.name) == DROUGHT_SPELL:
        return {"kind": "static", "static": "sac_tax110f", "tax": "spell", "effects": []}
    return None


def black_symbols(text: str) -> int:
    """107.4e-f: every {..} symbol with a B part (B, B/G, 2/B, B/P, B/G/P)."""
    return sum("B" in s.split("/") for s in re.findall(r"\{([^}]*)\}", text))


def _sac(name: str, n: int) -> AbilityCost:
    from dataclasses import replace

    from app.rules import costs

    one = costs.parse_ability_cost(f"Sacrifice a {name}").components[0]
    return costs.AbilityCost(components=(replace(one, amount=n, text=f"Sacrifice {n} {name}{'s' if n != 1 else ''}"),))


def _taxes(state: GameState, info: CardInfo, tax: str) -> list[Any]:
    from app.rules import permissions

    return [src for src, _, d in permissions._table_statics(state, info, {"sac_tax110f"}) if d["tax"] == tax]


def spell_tax(state: GameState, info: CardInfo, ch: Characteristics) -> AbilityCost | None:
    """Drought, spells: one Swamp for each black symbol in the spell's mana cost, for each Drought."""
    n = black_symbols(ch.mana_cost or "") * len(_taxes(state, info, "spell"))
    return _sac("Swamp", n) if n else None
