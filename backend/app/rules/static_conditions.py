"""Conditions of conditional static abilities ("as long as …", wave 4B), researched against CR 2026-09-25.

app/rules/statics.py reads "As long as <condition>, <subject> <predicate>." and "<subject> <predicate> as long
as <condition>."; this module adds the condition shapes that only a static's own context can answer (604.2,
611.3a: a static applies at any moment its condition is true, never locked in):

* ``{"static": "attached_is", "sel": <selector key>, "noun": "creature" | "permanent" | …}`` — "as long as
  equipped creature is legendary", "enchanted creature is white", "enchanted permanent is an Equipment": the
  object the source is attached to (301.5a, 303.4b) matches the selector (read as it is now);
* ``{"static": "designation", "is": "monstrous" | "renowned"}`` — the source has the designation
  (701.37b, 702.112b: kept until it leaves the battlefield); ``{"static": "self", "test": "modified"}``
  (700.9) is answered by statics.holds;
* ``{"static": "zone", "zone": "graveyard"}`` — "as long as this card is in your graveyard": the ability
  states the zone it functions from (113.6b, 604.2); "you" is the card's owner (108.4a);
* ``{"static": "opp_graveyard", "n": N}`` — "an opponent has N or more cards in their graveyard" (some one
  opponent);
* ``{"static": "opp_life", "op": "<=", "n": N}`` — "an opponent has N or less life" (some one opponent);
* ``{"static": "life_vs_start", "op": ">=" | ">" | "<=", "plus": N, "half": bool}`` — your life total
  against your starting life total (119.1, 903.7: 40 in Commander; the game's setting is read);
* ``{"static": "all", "conds": [...]}`` — "this card is in your graveyard and you control a Mountain".

Devotion ("your devotion to red is less than five", 700.5) is a plain ``conditions`` value condition
(``{"value": {"devotion": ["R"]}, "op": "<=", "n": 4}``). Anything else parses to None (manual).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import selectors, values

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

Condition = dict[str, Any]

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_ADJECTIVES = frozenset({"legendary", "white", "blue", "black", "red", "green", "colorless", "multicolored", "snow"})
_ATTACHED = re.compile(r"(?P<who>equipped|enchanted) (?P<noun>creature|permanent|land|artifact) is (?P<desc>.+)")
_DESIGNATION = re.compile(r"(?:~ is|it's|it is) (?P<is>monstrous|renowned)")
_MODIFIED = re.compile(r"(?:~ is|it's|it is) modified")
_IN_GRAVEYARD = re.compile(r"this card is in your graveyard(?: and (?P<rest>.+))?")
_OPP_GRAVEYARD = re.compile(r"an opponent has (?P<n>\w+) or more cards in their graveyard")
_OPP_LIFE = re.compile(r"an opponent has (?P<n>\w+) or less life")
_DEVOTION = re.compile(r"your devotion to (?P<c1>white|blue|black|red|green)(?: and (?P<c2>white|blue|black|red|green))? "
                       r"is less than (?P<n>\w+)")
_START = "your starting life total"
_LIFE_VS_START = {
    f"your life total is greater than {_START}": (">", 0, False),
    f"your life total is greater than or equal to {_START}": (">=", 0, False),
    f"your life total is less than or equal to half {_START}": ("<=", 0, True),
}
_LIFE_MORE = re.compile(r"you have at least (?P<n>\w+) life more than your starting life total"
                        r"|your life total is at least (?P<m>\w+) greater than your starting life total")
_SELF_COUNTERS = re.compile(r"there are (?P<n>\w+) or more (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters on ~")


def _num(word: str | None) -> int | None:
    if word is None:
        return None
    w = word.lower()
    return int(w) if w.isdigit() else values.NUMBERS.get(w)


def attached_selector(desc: str) -> str | None:
    """"legendary" / "white" / "a Human or an Angel" / "a creature" / "an Equipment" / "a basic Mountain" →
    a selector key for one object on the battlefield (no "you": the test is about the object alone)."""
    phrase = re.sub(r"\b(?:a|an) ", "", desc.strip())
    words = phrase.split()
    if not words:
        return None
    if all(w in _ADJECTIVES for w in words):
        phrase += " permanent"
    sel = selectors.parse(phrase)
    if sel is None or sel.player is not None or sel.zones != ("battlefield",) or sel.card or sel.other \
            or sel.controller is not None or sel.owner is not None or sel.extras:
        return None
    if sel.key() == selectors.Selector().key():
        return None  # ("is a permanent": says nothing)
    return sel.key()


def parse(text: str) -> Condition | None:
    """A condition only a static ability's context answers, or None (statics.py tries the others)."""
    t = text.strip()
    m = _ATTACHED.fullmatch(t)
    if m:
        key = attached_selector(m["desc"])
        return {"static": "attached_is", "sel": key, "noun": m["noun"], "who": m["who"]} if key else None
    m = _DESIGNATION.fullmatch(t)
    if m:
        return {"static": "designation", "is": m["is"]}
    if _MODIFIED.fullmatch(t):
        return {"static": "self", "test": "modified"}
    m = _IN_GRAVEYARD.fullmatch(t)
    if m:
        zone: Condition = {"static": "zone", "zone": "graveyard"}
        if not m["rest"]:
            return zone
        from app.rules import statics

        rest = statics.condition(m["rest"])
        if rest is None or rest.get("static") in ("self", "self_counter", "attached_is", "designation", "zone"):
            return None  # (a card in a graveyard is never tapped, attached or monstrous)
        return {"static": "all", "conds": [zone, rest]}
    m = _OPP_GRAVEYARD.fullmatch(t)
    if m:
        n = _num(m["n"])
        return {"static": "opp_graveyard", "n": n} if n is not None else None
    m = _OPP_LIFE.fullmatch(t)
    if m:
        n = _num(m["n"])
        return {"static": "opp_life", "op": "<=", "n": n} if n is not None else None
    m = _DEVOTION.fullmatch(t)
    if m:
        n = _num(m["n"])
        if n is None or n < 1:
            return None
        colors = [_COLORS[c] for c in (m["c1"], m["c2"]) if c]
        return {"value": {"devotion": colors}, "op": "<=", "n": n - 1}  # 700.5: "less than N"
    if t in _LIFE_VS_START:
        op, plus, half = _LIFE_VS_START[t]
        return {"static": "life_vs_start", "op": op, "plus": plus, "half": half}
    m = _LIFE_MORE.fullmatch(t)
    if m:
        n = _num(m["n"] or m["m"])
        return {"static": "life_vs_start", "op": ">=", "plus": n, "half": False} if n is not None else None
    m = _SELF_COUNTERS.fullmatch(t)
    if m:
        n = _num(m["n"])
        return {"static": "self_counter", "counter": m["kind"], "op": ">=", "n": n} if n is not None else None
    return None


KINDS = frozenset({"attached_is", "designation", "zone", "opp_graveyard", "opp_life", "life_vs_start", "all"})


def attached_object(plan: Plan, source: CardInstance) -> CardInstance | None:
    target = plan.state.cards.get(source.attached_to or "")
    if target is None or not target.zone.endswith(":battlefield") or not source.zone.endswith(":battlefield"):
        return None
    return target


def holds(plan: Plan, cond: Condition, *, source: CardInstance, controller: str) -> bool:
    """Is one of this module's conditions true right now (611.3a)?"""
    from app.rules import statics

    kind = cond["static"]
    if kind == "all":
        return all(statics.holds(plan, c, source=source, controller=controller) for c in cond["conds"])
    if kind == "zone":  # 113.6b: the card is in its owner's graveyard
        return source.zone == f"{source.owner}:graveyard"
    if kind == "attached_is":
        target = attached_object(plan, source)
        if target is None:
            return False
        ch = plan.ch(target)
        if cond["noun"] == "creature" and not ch.is_creature:
            return False
        if cond["noun"] == "land" and not ch.is_land:
            return False
        if cond["noun"] == "artifact" and "Artifact" not in ch.types:
            return False
        return selectors.matches(plan, selectors.from_key(cond["sel"]), target, ch, controller, source.id)
    if kind == "designation":  # 701.37b / 702.112b: a designation of this object (a new object has none, 400.7)
        r = plan.rules
        if r is None or not source.zone.endswith(":battlefield"):
            return False
        return r.object_id(source.id) in (r.monstrous if cond["is"] == "monstrous" else r.renowned)
    opponents = [p for p in plan.live() if p != controller]
    if kind == "opp_graveyard":
        return any(len(plan.state.zones.get(f"{p}:graveyard", ())) >= cond["n"] for p in opponents)
    if kind == "opp_life":
        return any(plan.state.players[p].life <= cond["n"] for p in opponents)
    if kind == "life_vs_start":
        life = plan.state.players[controller].life
        start = plan.state.settings.starting_life
        if cond.get("half"):  # "less than or equal to half your starting life total" (no rounding needed: compare doubled)
            return 2 * life <= start
        want = start + int(cond.get("plus") or 0)
        return {">": life > want, ">=": life >= want, "<=": life <= want}[cond["op"]]
    return False


def modified(plan: Plan, card: CardInstance) -> bool:
    """700.9: it has a counter on it, it's equipped, or it's enchanted by an Aura its controller controls."""
    if any(n > 0 for n in card.counters.values()):
        return True
    for c in plan.state.cards.values():
        if c.attached_to != card.id or not c.zone.endswith(":battlefield"):
            continue
        subtypes = plan.ch(c).subtypes
        if "Equipment" in subtypes or ("Aura" in subtypes and c.controller == card.controller):
            return True
    return False
