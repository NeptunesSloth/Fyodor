"""-- additional land plays (wave 4J) -- "You may play an additional land on each of your turns." (Exploration, Oracle
of Mul Daya, Icetill Explorer), "You may play two additional lands on each of your turns." (Azusa, Lost but Seeking).
Researched against CR 2026-09-25.

* 305.2: a player can normally play one land during their turn; continuous effects may increase that number. 305.2a:
  a land play is legal while the number of lands the player can play this turn is greater than the number already
  played this turn (lands played during resolutions count too). Several such effects add up (Exploration and Azusa:
  four lands).
* The static ability works while its permanent is on the battlefield (611.3a); its controller is the "you".
* -- one-shot extra land plays (wave 8A) -- "You may play an additional land this turn." (Explore, Urban Evolution),
  "You may play up to three additional lands this turn." (Summer Bloom): a continuous effect from a resolving spell or
  ability, lasting this turn (611.2a), for the player it names ("you"). Several add up. "Up to" is no obligation: the
  extra plays are only permission (305.2).
* -- static grants (wave 15A) -- "Each player may play an additional land on each of their turns." (Rites of Flourishing,
  Ghirapur Orrery): the same for every player, from whoever controls the permanent (305.2).
* Refused (manual): "on each of your turns" with a condition and anything granting land plays to some other players.

Read by app/rules/engine.land_play_problem.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.characteristics import CardInfo

EXTRA_LANDS = "extra_land_plays"
_LINE = re.compile(r"^(?:You may|(?P<each>Each player may)) play (?:an additional land|(?P<n>two|three) additional lands) on each of "
                   r"(?(each)their|your) turns\.$")  # (wave 15A: Rites of Flourishing, Ghirapur Orrery: every player, 305.2)
_N = {"two": 2, "three": 3}


def static_definition(text: str) -> dict[str, Any] | None:
    m = _LINE.match(text.strip())
    if m is None:
        return None
    return {"kind": "static", "static": EXTRA_LANDS, "n": _N[m["n"]] if m["n"] else 1, "all": bool(m["each"]),
            "effects": []}


_ONE_SHOT = re.compile(r"^you may play (?:an additional land|(?:up to )?(?P<n>two|three) additional lands) this turn$")


def sentence(text: str) -> list[dict[str, Any]] | None:
    """"You may play an additional land this turn." as an effect (a permission, not a choice made on resolution)."""
    m = _ONE_SHOT.match(text)
    return [{"do": "extra_land", "n": _N[m["n"]] if m["n"] else 1}] if m else None


def extra_land(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """305.2 / 611.2a: the controller may play ``n`` additional lands this turn (several effects add up)."""
    from app.game.rules_state import TurnCount

    r, me, turn = plan.rules, ctx["controller"], plan.state.turn.number
    r.extra_land_plays[me] = TurnCount(turn=turn, count=one_shot(plan.state, me) + int(e["n"]))
    n = int(e["n"])
    plan.note(f"{plan.name(me)} may play {'an' if n == 1 else n} additional land{'s' if n > 1 else ''} this turn (305.2)", actor=me)
    return True


PRIMITIVES = {"extra_land": extra_land}


def one_shot(state: GameState, player: str) -> int:
    entry = state.rules.extra_land_plays.get(player) if state.rules else None
    return entry.count if entry and entry.turn == state.turn.number else 0


def allowed(state: GameState, player: str, info: CardInfo | None) -> int:
    """How many lands ``player`` can play this turn (305.2): one, plus each "additional land" static ability of a
    permanent they control. Without card information only the one."""
    if info is None or state.rules is None:
        return 1
    from app.rules import characteristics as chars
    from app.rules import scripts
    from app.rules.layers import derive

    n = 1 + one_shot(state, player)  # (-- one-shot extra land plays (wave 8A) --)
    for c in list(state.cards.values()):  # (wave 15A: "each player may …" works from anyone's battlefield)
        if not c.zone.endswith(":battlefield") or c.face_down or state.rules.card_mode(c.id) == "manual":
            continue
        ch = derive(state, c, chars.of(c, info), info)
        n += sum(int(d.get("n") or 0) for d in scripts.definitions(ch).values()
                 if d.get("kind") == "static" and d.get("static") == EXTRA_LANDS and (c.controller == player or d.get("all")))
    return n
