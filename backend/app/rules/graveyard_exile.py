"""-- graveyard exile (wave 4J) -- "Exile target player's graveyard." (Bojuka Bog, Rakdos Charm), "Exile each
opponent's graveyard.", "Exile all graveyards." (Farewell). Researched against CR 2026-09-25.

* 404.1 / 400.1: a graveyard is a zone; exiling a player's graveyard moves every card in it to exile (406.1), all
  at once — one move, one event batch (a "one or more cards leave your graveyard" trigger triggers once, 603.2c).
* 115.1 / 115.10a: "target player" is a target of the ability; if that player is an illegal target as it resolves
  (left the game, 800.4a), the instruction does nothing.

The ``who`` is ``"graveyard_of:<player reference>"`` (effects._players reads the reference: "target", "each_opponent",
"each_player"); app/rules/effects._cards gives the cards in those players' graveyards. Nothing here executes text.
"""

from __future__ import annotations

import re
from typing import Any

PREFIX = "graveyard_of:"
_PLAYERS = {"target player's": ("target", "player"), "target opponent's": ("target", "opponent"),
            "each opponent's": ("each_opponent", None), "each player's": ("each_player", None),
            "all": ("each_player", None)}
_EXILE = re.compile(r"^exile (?P<p>target player's|target opponent's|each opponent's|each player's) graveyard$|"
                    r"^exile (?P<all>all) graveyards$|"
                    r"^exile all (?P<sel>[a-z]+ cards) from (?P<p2>target player's|target opponent's) graveyard$")  # (wave 15C)


def _effect(m: re.Match[str]) -> tuple[list[dict[str, Any]], str | None]:
    who, target = _PLAYERS[m["p"] or m["p2"] or m["all"]]
    if m["sel"]:  # -- if you do (wave 15C) -- "Exile all creature cards from target player's graveyard": only the cards of that kind
        from app.rules import selectors
        from app.rules.scripts import _NoMatch  # (scripts imports this module)

        sel = selectors.parse(m["sel"][:-1] + " from a graveyard")
        if sel is None or sel.zones != ("graveyard",) or not sel.card:
            raise _NoMatch
        who += "|" + sel.key()
    return [{"do": "exile", "who": PREFIX + who}], target


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_EXILE, _effect)]
