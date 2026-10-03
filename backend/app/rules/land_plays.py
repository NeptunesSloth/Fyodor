"""-- additional land plays (wave 4J) -- "You may play an additional land on each of your turns." (Exploration, Oracle
of Mul Daya, Icetill Explorer), "You may play two additional lands on each of your turns." (Azusa, Lost but Seeking).
Researched against CR 2026-09-25.

* 305.2: a player can normally play one land during their turn; continuous effects may increase that number. 305.2a:
  a land play is legal while the number of lands the player can play this turn is greater than the number already
  played this turn (lands played during resolutions count too). Several such effects add up (Exploration and Azusa:
  four lands).
* The static ability works while its permanent is on the battlefield (611.3a); its controller is the "you".
* Refused (manual): the one-shot "You may play an additional land this turn." of a resolving spell, "on each of your
  turns" with a condition, and anything granting land plays to other players.

Read by app/rules/engine.land_play_problem.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.characteristics import CardInfo

EXTRA_LANDS = "extra_land_plays"
_LINE = re.compile(r"^You may play (?:an additional land|(?P<n>two|three) additional lands) on each of your turns\.$")
_N = {"two": 2, "three": 3}


def static_definition(text: str) -> dict[str, Any] | None:
    m = _LINE.match(text.strip())
    if m is None:
        return None
    return {"kind": "static", "static": EXTRA_LANDS, "n": _N[m["n"]] if m["n"] else 1, "effects": []}


def allowed(state: GameState, player: str, info: CardInfo | None) -> int:
    """How many lands ``player`` can play this turn (305.2): one, plus each "additional land" static ability of a
    permanent they control. Without card information only the one."""
    if info is None or state.rules is None:
        return 1
    from app.rules import characteristics as chars
    from app.rules import scripts
    from app.rules.layers import derive

    n = 1
    for cid in state.zones.get(f"{player}:battlefield", []):
        c = state.cards.get(cid)
        if c is None or c.controller != player or c.face_down or state.rules.card_mode(c.id) == "manual":
            continue
        ch = derive(state, c, chars.of(c, info), info)
        n += sum(int(d.get("n") or 0) for d in scripts.definitions(ch).values()
                 if d.get("kind") == "static" and d.get("static") == EXTRA_LANDS)
    return n
