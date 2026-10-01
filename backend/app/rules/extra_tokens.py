"""-- refused grants/replacements (wave 3R2) -- Token-creation replacements that add a different
token (614.1a, 614.16, 616.1). Researched against the Comprehensive Rules of 2026-09-25.

"If one or more tokens would be created under your control, those tokens plus an additional Food
token are created instead." (Peregrin Took), "… plus a 1/1 green Frog creature token …" (Quina, Qu
Gourmet), "… plus a Mutagen token …" (Donatello, the Brains), "… plus that many 1/1 green Squirrel
creature tokens …" (Chatterfang, Squirrel General), "If you would create one or more tokens,
instead create those tokens plus an additional Food token." (Tippy-Toe, Terrific Partner).

A static replacement of app/rules/replace.py (event "tokens", op "extra"). The tokens it adds are
part of the same creation event: the engine carries them as a *satellite* event that has
everything the original one had applied to it so far (614.5: each effect applies once to the
event). Effects applied after it apply to all of it — "twice that many" doubles the added Food
too, "that many Squirrels" counts it — while a second "plus an additional Food token" adds one
Food to the event, not one per part of it (a fixed-count addition never applies to a satellite).
The added tokens aren't tapped because the original ones are ("create a tapped Treasure"), and
the order of two such effects is the creating player's (616.1: they're asked when it matters).
"""

from __future__ import annotations

import re
from typing import Any

Definition = dict[str, Any]

_UNDER_YOU = re.compile(r"If one or more tokens would be created under your control, those tokens plus "
                        r"(?P<what>an additional [A-Z][a-z]+ token|a [^.]+? token|that many [^.]+? tokens) are created instead\.")
_YOU_CREATE = re.compile(r"If you would create one or more tokens, instead create those tokens plus "
                         r"(?P<what>an additional [A-Z][a-z]+ token)\.")


def static_definition(text: str) -> Definition | None:
    m = _UNDER_YOU.fullmatch(text.strip()) or _YOU_CREATE.fullmatch(text.strip())
    if m is None:
        return None
    from app.rules import token_grammar

    what = m["what"]
    same = what.startswith("that many ")
    phrase = "create two " + what[len("that many "):] if same else "create a " + re.sub(r"^(?:an additional|a) ", "", what)
    found = token_grammar.parse(phrase)
    if not found or len(found) != 1 or found[0].get("do") != "create_token" or found[0].get("n") != (2 if same else 1):
        return None
    e = found[0]
    if set(e) - {"do", "who", "n", "token"}:
        return None  # (a token "for each …", "where X is …", tapped or attacking: not this template)
    return {"kind": "static", "static": "replace", "event": "tokens", "match": {"who": "you"},
            "op": {"do": "extra", "token": e["token"], "n": "same" if same else 1}, "effects": []}


def applies(c: Any, ev: dict[str, Any]) -> bool:
    """A fixed number of added tokens is added once to the event (not to its added parts)."""
    return not (c.op.get("n") != "same" and ev.get("satellite"))


def apply(c: Any, ev: dict[str, Any]) -> list[dict[str, Any]]:
    n = int(ev["count"]) if c.op.get("n") == "same" else int(c.op.get("n") or 1)
    extra = {**ev, "token": dict(c.op["token"]), "count": n, "tapped": False, "satellite": True}
    return [dict(ev), extra]
