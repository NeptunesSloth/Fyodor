"""Bounded native mana-unit allocation restrictions."""
from __future__ import annotations

from dataclasses import replace

from app.rules import mana as M

JEGANTHA = "{T}: Add {W}{U}{B}{R}{G}. This mana can't be spent to pay generic mana costs."


def parse_mana(text: str, identity: tuple[str, ...], name: str) -> M.ManaAbility | None:
    if text != JEGANTHA:
        return None
    native = M.parse_mana_ability('{T}: Add {W}{U}{B}{R}{G}.', identity, card_name=name)
    return replace(native, generic_allowed=False,
                   spend_text="This mana can't be spent to pay generic mana costs.") if native else None
