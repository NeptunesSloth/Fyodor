"""-- if you do (wave 52A) -- "For each creature exiled this way, its controller draws a card." (Martyr's Cry, King Solomon's Frogs), "… its controller cloaks the top card of their
library." (Unexplained Absence), "That player investigates for each nontoken creature exiled this way." (Declaration in Stone).

CR 2026-09-25: 608.2c: the instruction is carried out once for each object the earlier instruction acted on; 109.4 / 108.4a: "its controller" is the controller of that object
as it last existed (608.2h), a card that wasn't a permanent has its owner. The count is the one ``this_way.by_controller`` reads for "for each permanent destroyed this way,
its controller creates …", so each player draws / cloaks / investigates as many times as they controlled objects the instruction acted on.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.rules import this_way

_EACH = re.compile(r"^for each (?P<what>[^,]+ this way), its controller (?P<verb>draws a card|cloaks the top card of their library|investigates)$")
_IMPERATIVE = {"draws a card": "draw a card", "cloaks the top card of their library": "cloak the top card of your library", "investigates": "investigate"}
# "That player investigates for each nontoken creature exiled this way." after "Exile target creature and all other creatures its controller controls with the same name as that
# creature." (Declaration in Stone; read as "Exile target creature." with the same-name set bound afterwards, radiance.split): every object counted is controlled by that one
# player (the target's controller), so it is "its controller" of each (the only form read)
_THAT_PLAYER = re.compile(r"^that player investigates for each (?P<what>[^,]+ this way)$")
EXILE_TARGET = "exile target creature"


def parse(text: str, clause: Callable[[str], tuple[list[dict[str, Any]], Any] | None], before: str | None = None) -> list[dict[str, Any]] | None:
    """The lowercase sentence → one instruction done per controller, or None (not this form). ``before``: the lowercase sentence just before it."""
    that = _THAT_PLAYER.match(text)
    if that is not None:
        if before != EXILE_TARGET:
            return None
        text = f"for each {that['what']}, its controller investigates"
    m = _EACH.match(text)
    if m is None or (counted := this_way.parse(m["what"])) is None:
        return None
    found = clause(_IMPERATIVE[m["verb"]])
    if not found or found[1] is not None or len(found[0]) != 1:
        return None
    e = found[0][0]
    if e["do"] == "draw" and e["n"] == 1:
        return [{**e, "who": "each_player", "n": {**counted, "each_owner": True}}]  # (effects.draw: each player draws as many as the objects they controlled)
    if e["do"] in ("create_token", "manifest") and e.get("n") == 1:
        return [{**e, "who": "you" if e["do"] == "create_token" else "each_player", "per_controller": counted}]
    return None


# "Destroy all creatures target player controls. For each creature that died this way, that player creates two 1/1 red Goblin creature tokens." (Mogg Infestation): every
# object counted was controlled by the target player, so "that player" is "its controller" of each (read as the form above)
_ALL_THEIRS = re.compile(r"(\b(?:Destroy|Exile) all [^.]+? target (?:player|opponent) controls\. For each [^,.]+? this way, )that player (creates?)\b")
# "…, and those tokens gain haste until end of turn." (Warren Weirding): two instructions in order (608.2c), the second about the tokens the first made; with nobody to
# create them (the condition before it failed) there is no token to gain it
_AND_THOSE_TOKENS = re.compile(r"(\b[Cc]reates? [^.\"]+? tokens?), and (those tokens gain [^.\"]+? until end of turn)\.")


def rewrite(body: str) -> str:
    body = _ALL_THEIRS.sub(lambda m: f"{m[1]}its controller {m[2]}", body)
    return _AND_THOSE_TOKENS.sub(lambda m: f"{m[1]}. {m[2][0].upper()}{m[2][1:]}.", body)
