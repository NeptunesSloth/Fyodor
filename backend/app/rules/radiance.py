"""-- radiance (wave 9C) -- "Target creature and each other creature that shares a color with it …" (Cleansing Beam,
Wojek Siren, Surge of Zeal, Leave No Trace, Incite Hysteria, Wojek Embermage, Rally the Righteous).

"Radiance" is an ability word (207.2c): no rules meaning of its own. The instruction affects the target and every other
permanent of the named type that shares a color with it (105.4: sharing a color = at least one color in common; a
colorless target shares none, so only it is affected). Who shares is judged as the instruction is carried out (608.2h),
with the target's colors as it is then. The sentence is read as the plain one-target instruction, and its objects
become ``who: "radiance:<target ref>|<selector>"`` (effects._cards).
"""

from __future__ import annotations

import re
from typing import Any

_CLAUSE = re.compile(r"(?P<t>\b[Tt]arget (?P<noun>creature|enchantment|artifact)) and each other (?P=noun) that shares a color "
                     r"with it(?P<verb> get| gain)?(?=[ .,\"])", re.IGNORECASE)
_THOSE = re.compile(r"\b(?:Those|those) creatures (?P<v>get|gain)\b")
PREFIX = "radiance:"


def split(body: str) -> tuple[str, str] | None:
    """(the body read as an instruction on the one target, the noun's selector key), or None (no such clause, or
    more than one: not read)."""
    from app.rules import selectors

    found = list(_CLAUSE.finditer(body))
    if len(found) != 1 or "target" in body[found[0].end():]:
        return None
    m = found[0]
    sel = selectors.parse(m["noun"])
    if sel is None:
        return None
    text = body[:m.start()] + m["t"] + (m["verb"] + "s" if m["verb"] else "") + body[m.end():]
    if m["noun"] == "creature":  # "Untap target creature and each other …. Those creatures get +2/+0": the same ones
        text = _THOSE.sub(lambda g: "That creature " + g["v"] + "s", text)
    return text, sel.key()


def _bind(node: Any, ref: str, sel: str) -> Any | None:
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "who" and v == ref:
                out[k] = f"{PREFIX}{ref}|{sel}"
                continue
            if (r := _bind(v, ref, sel)) is None:
                return None
            out[k] = r
        return out
    if isinstance(node, list):
        out_l = []
        for v in node:
            if (r := _bind(v, ref, sel)) is None:
                return None
            out_l.append(r)
        return out_l
    if isinstance(node, str) and (node == "target" or node.startswith("target:")):
        return None  # (the target named any other way — a source, an amount: not read)
    return node


def bind(found: tuple[list[dict[str, Any]], Any, bool] | None, sel: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if found is None:
        return None
    effects, groups, optional = found
    if optional or not groups or (isinstance(groups, list) and len(groups) != 1) or not effects:
        return None
    bound = _bind(effects, "target", sel)
    if bound is None or not any(PREFIX in str(e) for e in bound):
        return None
    return bound, groups, optional


def cards(plan: Any, ctx: dict[str, Any], who: str) -> list[str]:
    """The target and each other object of the selector sharing a color with it (105.4)."""
    from app.rules import effects, selectors

    ref, _, key = who[len(PREFIX):].partition("|")
    out = effects._cards(plan, ctx, ref)
    if len(out) != 1:
        return []
    colors = plan.ch(plan.state.cards[out[0]]).colors
    if not colors:
        return out
    sel = selectors.from_key(key)
    return [*out, *(c for c in selectors.candidates(plan, sel, ctx["controller"], ctx.get("source_card"))
                    if c != out[0] and plan.ch(plan.state.cards[c]).colors & colors)]
