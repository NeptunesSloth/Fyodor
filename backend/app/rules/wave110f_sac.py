"""Brutal Suppression, Drought (wave 110F): a static additional cost of "Sacrifice a land / a Swamp" on spells and activated abilities.

118.8: an additional cost is paid with the rest (601.2f-h, 602.2b). 107.4e / 107.4f: a hybrid or Phyrexian symbol with a B half is a black mana symbol.
Not automated (handed to the table, refused with a message): Drought's tax on mana abilities and on keyword activations that have their own route
(cycling, ninjutsu, unearth, equip, crew ...); their sources are not offered / the action is refused instead of being paid without the sacrifice."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics
    from app.rules.costs import AbilityCost

BRUTAL = 'Activated abilities of nontoken Rebels cost an additional "Sacrifice a land" to activate.'
DROUGHT_SPELL = 'Spells cost an additional "Sacrifice a Swamp" to cast for each black mana symbol in their mana costs.'
DROUGHT_ABILITY = 'Activated abilities cost an additional "Sacrifice a Swamp" to activate for each black mana symbol in their activation costs.'
_KINDS = {BRUTAL: "brutal", DROUGHT_SPELL: "spell", DROUGHT_ABILITY: "ability"}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    kind = _KINDS.get(scripts.self_text(ability.text, ch.name)) if ability.kind == "static" else None
    return {"kind": "static", "static": "sac_tax110f", "tax": kind, "effects": []} if kind else None


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


def ability_tax(state: GameState, info: CardInfo, card: CardInstance, ch: Characteristics, cost_text: str) -> AbilityCost | None:
    """Brutal Suppression (a land if the source is a nontoken Rebel) and Drought (a Swamp per black symbol of the activation cost)."""
    from app.rules import costs

    parts = []
    if "Rebel" in ch.subtypes and not card.is_token and (n := len(_taxes(state, info, "brutal"))):
        parts.append(_sac("land", n))
    if (n := black_symbols(cost_text) * len(_taxes(state, info, "ability"))):
        parts.append(_sac("Swamp", n))
    return costs.AbilityCost(components=tuple(c for p in parts for c in p.components)) if parts else None


def refuses(state: GameState, info: CardInfo, cost_text: str) -> bool:
    """Drought taxes this activation but its route does not pay a tax: refuse it."""
    return black_symbols(cost_text) > 0 and bool(_taxes(state, info, "ability"))
