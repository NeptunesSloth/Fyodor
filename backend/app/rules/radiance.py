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
# -- same name (wave 11D) -- "Destroy target nonland permanent and all other permanents with the same name as that
# permanent." (201.2: names in common; a nameless face-down object has none). The others are not targets: only the one
# target is chosen and checked on resolution (608.2b), the rest are whatever bears that name as the instruction is carried out.
# (wave 26B: "target nonland permanent an opponent controls and all other nonland permanents your opponents control with the same name": Banishment)
# (wave 32A: "target nonland permanent an opponent controls and all tokens that player controls with the same name as that permanent" (Legions
# to Ashes), "target creature and all other creatures its controller controls with the same name as that creature" (Declaration in Stone,
# Legion's End, Deputy of Detention): the others are the target's controller's; "target creature card and all other cards with the same name as
# that card from your graveyard" (Echoing Return, Rat King): the others are cards in that zone)
_SAME_NAME = re.compile(r"\b(?P<t>[Tt]arget (?:[a-z]+ )*?(?P<tn>[a-z]+)(?: an opponent controls)?(?: with mana value \d+ or (?:less|greater))?) and "
                        r"(?:all|each)(?P<other> other)? (?P<noun>(?:nonland )?(?:permanents|creatures|lands|artifacts|enchantments|tokens|cards"
                        r"|creature|land|artifact|enchantment)(?: your opponents control)?)(?P<ctl> (?:its controller|that player) controls)? "
                        r"with the same name as that (?P=tn)(?P<verb> get| gain)?(?=[ .,\"])")
SAME_NAME = "samename:"


def split(body: str) -> tuple[str, str, str] | None:
    """(the body read as an instruction on the one target, the noun's selector key, the binding's prefix), or None (no
    such clause, or more than one: not read)."""
    from app.rules import selectors

    found = list(_CLAUSE.finditer(body)) or list(_SAME_NAME.finditer(body))
    if len(found) != 1 or "target" in body[found[0].end():]:
        return None
    m = found[0]
    prefix = PREFIX if m.re is _CLAUSE else SAME_NAME
    noun, tail = m["noun"], body[m.end():]
    ctl = prefix == SAME_NAME and m["ctl"] is not None
    if prefix == SAME_NAME and noun == "cards":  # (wave 32A) the others are cards in the zone the sentence names after the clause
        zone = re.match(r" from (?:your|a|their) graveyard", tail)
        if zone is None:
            return None
        noun += zone[0]
    sel = selectors.parse(noun)
    if sel is None:
        return None
    text = body[:m.start()] + m["t"] + (m["verb"] + "s" if m["verb"] else "") + body[m.end():]
    if prefix == SAME_NAME:  # (Echoing Truth: "… to their owners' hands" → the one target's owner's hand)
        text = text.replace(" to their owners' hands", " to its owner's hand")
    if m["noun"] == "creature":  # "Untap target creature and each other …. Those creatures get +2/+0": the same ones
        text = _THOSE.sub(lambda g: "That creature " + g["v"] + "s", text)
    return text, ("ctl|" if ctl else "") + sel.key(), prefix


_NOT_READ = object()  # (-- if you do (wave 52A) -- a None leaf, like a token's power in a Clue, is no failure)


def _bind(node: Any, ref: str, sel: str, prefix: str) -> Any:
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "who" and v == ref:
                out[k] = f"{prefix}{ref}|{sel}"
                continue
            if (r := _bind(v, ref, sel, prefix)) is _NOT_READ:
                return _NOT_READ
            out[k] = r
        return out
    if isinstance(node, list):
        out_l = []
        for v in node:
            if (r := _bind(v, ref, sel, prefix)) is _NOT_READ:
                return _NOT_READ
            out_l.append(r)
        return out_l
    if isinstance(node, str) and (node == "target" or node.startswith("target:")):
        return _NOT_READ  # (the target named any other way — a source, an amount: not read)
    return node


def bind(found: tuple[list[dict[str, Any]], Any, bool] | None, sel: str, prefix: str = PREFIX) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if found is None:
        return None
    effects, groups, optional = found
    if optional or not groups or (isinstance(groups, list) and len(groups) != 1) or not effects:
        return None
    bound = _bind(effects, "target", sel, prefix)
    if bound is _NOT_READ or not any(prefix in str(e) for e in bound):
        return None
    return bound, groups, optional


def cards(plan: Any, ctx: dict[str, Any], who: str) -> list[str]:
    """The target and each other object of the selector sharing a color with it (105.4), or bearing its name (201.2)."""
    from app.rules import card_names, effects, selectors

    prefix = SAME_NAME if who.startswith(SAME_NAME) else PREFIX
    ref, _, key = who[len(prefix):].partition("|")
    out = effects._cards(plan, ctx, ref)
    if len(out) != 1:
        return []
    if prefix == SAME_NAME:
        target = plan.state.cards[out[0]]
        ctl = key.startswith("ctl|")  # (wave 32A) "its controller controls": the target's controller, as it is as this is carried out (608.2h)
        sel = selectors.from_key(key.removeprefix("ctl|"))
        return [*out, *(c for c in selectors.candidates(plan, sel, ctx["controller"], ctx.get("source_card"))
                        if c != out[0] and card_names.share(plan.ch(plan.state.cards[c]), plan.ch(target))
                        and (not ctl or plan.state.cards[c].controller == target.controller))]
    colors = plan.ch(plan.state.cards[out[0]]).colors
    if not colors:
        return out
    sel = selectors.from_key(key)
    return [*out, *(c for c in selectors.candidates(plan, sel, ctx["controller"], ctx.get("source_card"))
                    if c != out[0] and plan.ch(plan.state.cards[c]).colors & colors)]
