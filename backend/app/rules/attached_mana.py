"""-- attached events (wave 4L) -- "Whenever enchanted land is tapped for mana, its controller adds an additional
{G}." (Wild Growth, Overgrowth, Fertile Ground, Dawn's Reflection), researched against CR 2026-09-25.

* 106.12 / 106.12a: to tap a permanent for mana is to activate a mana ability of it with {T} in its cost; the
  ability triggers whenever such a mana ability resolves and produces mana.
* 605.1b: it is a triggered mana ability (no target, triggers from a mana ability, could add mana); 605.4a: it
  doesn't use the stack and resolves immediately after the mana ability that triggered it. So the mana arrives
  together with the land's own: the engine adds it as part of the same activation (``extend``), which is also
  what lets the payment solver count it.
* "its controller" is the land's controller (who tapped it), whoever controls the Aura.
* Wild Growth ruling (2004-10-04): "The additional mana is not an ability of the land and is not something the
  land can produce" — the extra mana never appears among what a land "could produce" (Reflecting Pool reads
  printed mana abilities: app/rules/casting.py ``_land_mana``), and it carries none of the land ability's
  spending restrictions; an ability with a restriction ("Spend this mana only to …") is left to the player while
  the land is enchanted this way (the engine doesn't split one activation's mana into restricted and free parts).

The extra is one of: mana symbols ("{G}{G}"), "one mana of any color" (the controller chooses: each color is an
option), "two mana in any combination of colors". Counted ("{G} for each Elf") or chosen-color extras stay manual.

Definition: ``{"kind": "triggered", "trigger": "tapped_for_mana", "extra": [[<mana>…], …] (options), "effects": []}``
— never put on the stack (app/rules/triggers.py doesn't know the trigger); applied by
``casting.mana_abilities`` through :func:`extend`.
"""

from __future__ import annotations

import re
from itertools import combinations_with_replacement, product
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules import mana as M
    from app.rules.characteristics import CardInfo

COLORS = ("W", "U", "B", "R", "G")
_LINE = re.compile(r"^Whenever enchanted land is tapped for mana, its controller adds an additional (?P<m>.+)\.$")


def definition(text: str) -> dict[str, Any] | None:
    m = _LINE.match(text.strip())
    if m is None:
        return None
    what = m["m"]
    options: list[list[str]]
    if re.fullmatch(r"(?:\{[WUBRGC]\})+", what):
        options = [re.findall(r"\{([WUBRGC])\}", what)]
    elif what == "one mana of any color":
        options = [[c] for c in COLORS]
    elif what == "two mana in any combination of colors":
        options = [list(pair) for pair in combinations_with_replacement(COLORS, 2)]
    else:
        return None
    return {"kind": "triggered", "trigger": "tapped_for_mana", "extra": options, "optional": False, "target": None,
            "effects": []}


def _extras(state: GameState, card: CardInstance, info: CardInfo) -> list[list[list[str]]]:
    """The extra-mana options of each such trigger of what is attached to ``card`` (one entry per trigger)."""
    from app.rules import scripts
    from app.rules.characteristics import of as chars_of
    from app.rules.layers import derive

    r = state.rules
    out = []
    for c in state.cards.values():
        if c.attached_to != card.id or not c.zone.endswith(":battlefield") or c.face_down:
            continue
        if r is not None and r.card_mode(c.id) == "manual":
            continue
        ch = derive(state, c, chars_of(c, info), info)
        for d in scripts.definitions(ch).values():
            if d.get("trigger") == "tapped_for_mana":
                out.append(d["extra"])
    return out


def extend(state: GameState, card: CardInstance, info: CardInfo, is_land: bool,
           found: list[tuple[int, M.ManaAbility]]) -> list[tuple[int, M.ManaAbility]]:
    """The land's mana abilities with each {T} ability's options carrying the extra mana of the triggers of the
    Auras on it (605.4a: added right after, with the ability's own)."""
    if not is_land or not found or not any(c.attached_to == card.id for c in state.cards.values()):
        return found
    extras = _extras(state, card, info)
    if not extras:
        return found
    from dataclasses import replace

    out = []
    for index, ab in found:
        if not ab.tap:
            out.append((index, ab))
            continue
        if ab.spend_only is not None:
            continue  # (restricted mana with unrestricted extra: by hand)
        options = tuple(dict.fromkeys(tuple(opt) + tuple(m for part in combo for m in part)
                                      for opt in ab.options for combo in product(*extras)))
        out.append((index, replace(ab, options=options)))
    return out
