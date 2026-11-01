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
Anything else the creating effect specified (tapped, attacking, "that token gains haste") applies to the
added tokens too (Chatterfang, Peregrin Took and Mondrak rulings: "applies to both the original tokens and
the Squirrels"), and the order of two such effects is the creating player's (616.1: they're asked when it matters).
"""

from __future__ import annotations

import re
from typing import Any

Definition = dict[str, Any]

# -- ability words (wave 9C) -- of one kind: "creature tokens" (Queen Allenal), "artifact tokens" (Stridehangar Automaton,
# Worldwalker Helm): the replacement applies to a creation event of tokens that are (also) of that card type
_UNDER_YOU = re.compile(r"If one or more (?P<kind>creature |artifact )?tokens would be created under your control, those tokens plus "
                        r"(?P<what>(?:an additional|a) [^.]+? token(?: with [a-z]+)?|that many [^.]+? tokens) "
                        r"are created instead\.")
_YOU_CREATE = re.compile(r"If you would create one or more (?P<kind>artifact )?tokens, instead create those tokens plus "
                         r"(?P<what>an additional [A-Z][a-z]+ token)\.")


# -- token swaps (wave 35C) -- 614.1a, 111.2: "If one or more creature tokens would be created under your control, that many 4/4 white Angel creature tokens
# with flying and vigilance are created instead." (Divine Visitation; artifact tokens → 5/5 red Dragons: Draconic Visitor): the tokens' characteristics are
# entirely replaced (Gatherer rulings) — everything else the effect said (tapped, attacking, "that token gains haste") still applies; "If you would create a
# Clue, Food, or Treasure token, instead create one of each." (Academy Manufactor): that many of each; "If you would create a Food token, instead create a
# Food token and a Treasure token." (Bilbo, Fellow Conspirator): that many Food and that many Treasure. Judged on the kind of token as it would be created
# (a noncreature token that becomes a creature only as it enters is not a creature token yet).
# (-- token swaps (wave 111B) -- of any kind: "If one or more tokens would be created under your control, that many 3/3 colorless Illusion artifact creature
# tokens are created instead." (Holo-Engineer): every token creation event of yours, Treasures and copies too)
_SWAP = re.compile(r"If one or more (?:(?P<kind>creature|artifact) )?tokens would be created under your control, that many (?P<tok>[^,.]+?) tokens"
                   r"(?P<more> with [^,.]+?)? are created instead\.")
_EACH_OF = re.compile(r"If you would create a Clue, Food, or Treasure token, instead create one of each\.")
_AND_ALSO = re.compile(r"If you would create an? (?P<kind>[A-Z][a-z]+) token, instead create an? (?P=kind) token and an? (?P<more>[A-Z][a-z]+) token\.")


def _one_token(phrase: str) -> dict[str, Any] | None:
    from app.rules import token_grammar

    found = token_grammar.parse(phrase)
    if not found or len(found) != 1 or found[0].get("do") != "create_token" or found[0].get("n") != 1:
        return None
    e = found[0]
    if set(e) - {"do", "who", "n", "token"} or any(isinstance(e["token"].get(k), dict) for k in ("power", "toughness")):
        return None
    return dict(e["token"])


def swap_definition(text: str) -> Definition | None:
    text = text.strip()
    tail: dict[str, Any] | None = None
    if (m := _SWAP.fullmatch(text)) is not None:
        token = _one_token("create a " + m["tok"] + " token" + (m["more"] or ""))
        tail = None if token is None else {"match": {"who": "you", **({"types": [m["kind"].capitalize()]} if m["kind"] else {})},  # (wave 111B: any kind)
                                           "op": {"do": "replace", "token": token}}
    elif _EACH_OF.fullmatch(text):
        tail = {"match": {"who": "you", "subtypes": ["Clue", "Food", "Treasure"]}, "op": {"do": "each_of"}}
    elif (m := _AND_ALSO.fullmatch(text)) is not None and m["kind"] in ("Food", "Clue", "Treasure", "Blood", "Map", "Gold", "Powerstone"):
        token = _one_token(f"create a {m['more']} token")
        tail = None if token is None else {"match": {"who": "you", "subtypes": [m["kind"]]}, "op": {"do": "extra", "token": token, "n": "same"}}
    return None if tail is None else {"kind": "static", "static": "replace", "event": "tokens", **tail, "effects": []}


_EACH_KINDS = ("Clue", "Food", "Treasure")


def swap(c: Any, ev: dict[str, Any]) -> list[dict[str, Any]]:
    """The events a token swap leaves of one creation event: the same count of the other kind of token (op ``replace``), or that many of each of the
    three (op ``each_of``: the event's own token stays, the other two are satellites that carry what was applied so far, like an added token)."""
    if c.op["do"] == "replace":
        return [{**ev, "token": dict(c.op["token"])}]
    from app.rules import token_grammar

    mine = next((k for k in _EACH_KINDS if k in str(ev["token"].get("type_line") or "")), None)
    root = ev.get("root") or dict(ev["token"])
    out = [{**ev, "root": root}]
    for kind in (k for k in _EACH_KINDS if k != mine):
        found = token_grammar.parse(f"create a {kind} token")
        if found and len(found) == 1 and found[0].get("do") == "create_token":
            out.append({**ev, "token": dict(found[0]["token"]), "satellite": True, "root": root})
    return out


def static_definition(text: str) -> Definition | None:
    if (swapped := swap_definition(text)) is not None:
        return swapped
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
    if set(e) - {"do", "who", "n", "token"} or any(isinstance(e["token"].get(k), dict) for k in ("power", "toughness")):  # (X/X: wave 4K)
        return None  # (a token "for each …", "where X is …", tapped or attacking: not this template)
    match: dict[str, Any] = {"who": "you"}
    if m["kind"]:
        match["types"] = [m["kind"].strip().capitalize()]
    return {"kind": "static", "static": "replace", "event": "tokens", "match": match,
            "op": {"do": "extra", "token": e["token"], "n": "same" if same else 1}, "effects": []}


def applies(c: Any, ev: dict[str, Any], sim: dict[str, Any] | None = None, matches: Any = None) -> bool:
    """A fixed number of added tokens is added once to the event, not once per part of it. A satellite (a part another
    effect added) can take a fixed addition only if this effect did not match the event's own tokens (it applies there
    instead, 614.5) and has not been applied to another added part yet: "creature tokens plus a Soldier" (Queen Allenal)
    after "artifact tokens plus a Thopter" (Stridehangar Automaton) on a Treasure, where the Thopter is what makes the
    event one of creature tokens (616.1: an effect applies once the modified event is one it applies to)."""
    if c.op.get("n") == "same" or not ev.get("satellite"):
        return True
    if sim is None or matches is None or c.id in (sim.get("sat_done") or ()):
        return False
    root = ev.get("root")
    return root is not None and not matches(c, root)


def apply(c: Any, ev: dict[str, Any], sim: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    n = int(ev["count"]) if c.op.get("n") == "same" else int(c.op.get("n") or 1)
    root = ev.get("root") or dict(ev["token"])
    if ev.get("satellite") and sim is not None and c.op.get("n") != "same":
        sim.setdefault("sat_done", []).append(c.id)
    extra = {**ev, "token": dict(c.op["token"]), "count": n, "satellite": True, "root": root}
    return [{**ev, "root": root}, extra]
