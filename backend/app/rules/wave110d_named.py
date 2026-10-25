"""-- named Aura tokens (wave 110D) -- "create a red Aura enchantment token named Mark of the Rani attached to another target creature. That token has enchant
creature and "Enchanted creature gets +2/+2 and is goaded."" (The Rani), "... named Settlement attached to up to one target land you control. It has enchant land
and "Enchanted land has '{T}: Add one mana of any color.'"" (Preston Garvey): 111.3, 303.4f (an Aura token created attached enters attached to that permanent, not
targeting it), 111.4 (the name given). Read as the "<name> Aura token" roles.NAMED knows, only when the Oracle sentence matches the registered token exactly.
"""
from __future__ import annotations

import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_SENTENCE = re.compile(r"create an? (?P<col>[a-z]+) Aura enchantment token named (?P<n>[A-Z][\w' ]+?) attached to (?P<o>[^.]+)\. "
                       r"(?:(?:The|That) token|It) has enchant (?P<k>creature|land) and \"(?P<t>.+)\"")


def rewrite(body: str) -> str:
    from app.rules import roles

    m = _SENTENCE.fullmatch(body.rstrip("."))
    if m is None or m["n"] not in roles.NAMED or m["n"] == "Contract":
        return body
    colors, text = roles.NAMED[m["n"]]
    own = text.split("\n")[-1] if text.startswith("Enchant ") else text
    if colors != [_COLORS.get(m["col"], "")] or m["t"].replace("'", '"') != own or text.startswith("Enchant ") != (m["k"] == "land"):
        return body
    return f"create a {m['n']} Aura token attached to {m['o']}."
