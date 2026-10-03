"""-- triggers (wave 5D) -- wordings of triggered abilities read as the plainer ones the grammar already knows.
Researched against CR 2026-09-25.

* "they" for the player a trigger is about: "Whenever an opponent draws a card, they lose 2 life." (Sheoldred, the
  Apocalypse) reads as "that player loses 2 life" — only when the trigger event names one player (the player who
  drew / gained / was dealt damage …, or the player whose step it is: "At the beginning of each opponent's upkeep,
  they lose 1 life") and only as the subject that opens the ability.
* "that player draws an additional card" in "At the beginning of each player's draw step, …" (Howling Mine, Kami of
  the Crescent Moon, Dictate of Kruphix): a draw on top of the turn-based draw (504.1), i.e. that player draws a card.
* "you may have [~ / it / target opponent / that player …] [do X]": an optional instruction (603.5: the choice is made
  as it resolves) whose doer is that object or player — the same as "[it] [does X]" with "you may".
"""

from __future__ import annotations

import re
from typing import Any

# third person singular of the verbs read here ("they lose" → "that player loses")
_VERBS = {"lose": "loses", "draw": "draws", "discard": "discards", "sacrifice": "sacrifices", "gain": "gains",
          "mill": "mills", "get": "gets", "create": "creates", "deal": "deals", "exile": "exiles", "reveal": "reveals",
          "shuffle": "shuffles", "return": "returns", "put": "puts", "search": "searches", "scry": "scries"}
_VERB_RE = "|".join(sorted(_VERBS, key=len, reverse=True))
_THEY = re.compile(rf"^they (?P<v>{_VERB_RE})\b")
_HAVE = re.compile(rf"^have (?P<s>~|it|target (?:player|opponent)|that player|each opponent) (?P<v>{_VERB_RE})\b")


def they_names_event_player(name: str, cond: dict[str, Any] | None, has_player: bool) -> bool:
    from app.rules.scripts import STEP_PLAYER_WHOSE

    if has_player:
        return True
    return name.startswith("step:") and name.rsplit(":", 1)[-1] in STEP_PLAYER_WHOSE


def rewrite_body(body: str, name: str, cond: dict[str, Any] | None, has_player: bool) -> str:
    """The body of a triggered ability with these wordings replaced by the plainer ones (else unchanged)."""
    if they_names_event_player(name, cond, has_player):
        body = _THEY.sub(lambda m: f"that player {_VERBS[m['v']]}", body)
    if name.startswith("step:draw:") and name.rsplit(":", 1)[-1] in ("each", "opponent"):
        # 504.1: the active player draws in the draw step; "an additional card" is one more card
        body = re.sub(r"\bthat player draws an additional card\.$", "that player draws a card.", body)
    return body


_NUMBER_OF = re.compile(r"\bcreate a number of (?P<what>[^.]+? tokens?(?: with [^.]+?)?) equal to (?P<v>[^.]+)\.")
_GAIN_AND_DRAW = re.compile(r"^you gain life and draw cards equal to (?P<v>[^.]+)\.$")


def plain_amounts(body: str) -> str:
    """"create a number of tapped Treasure tokens equal to its power" → "create X tapped Treasure tokens, where X is its
    power" (Goldvein Hydra; 107.3c: one X for the instruction); "you gain life and draw cards equal to its power" →
    both amounts spelled out (Lifeblood Hydra: the same value, read once per instruction from the object as it last
    existed, 608.2h)."""
    body = _NUMBER_OF.sub(lambda m: f"create X {m['what']}, where X is {m['v']}.", body)
    m = _GAIN_AND_DRAW.match(body.strip())
    if m is not None:
        body = f"you gain life equal to {m['v']}. Draw cards equal to {m['v']}."
    return body


def have_subject(text: str) -> str:
    """"have ~ deal 1 damage to any target" → "~ deals 1 damage to any target" (after "you may")."""
    return _HAVE.sub(lambda m: f"{m['s']} {_VERBS[m['v']]}", text)
