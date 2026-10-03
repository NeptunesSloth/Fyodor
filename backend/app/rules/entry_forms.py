"""-- entry forms (wave 5F) -- how a permanent enters, researched against CR 2026-09-25.

* "When this land enters untapped, …" (Mystic Sanctuary, Witch's Cottage, Dwarven Mine, Gingerbread Cabin) and
  "Whenever a permanent you control enters tapped, untap it." (Amulet of Vigor): whether the permanent entered tapped
  is part of the trigger event (603.2; app/rules/events.py ``entered_tapped``). It is read from this turn's log of
  what entered (``Entry.tapped``, recorded as the permanent arrived: tapped status is part of the move itself, a
  permanent never enters untapped and then becomes tapped by an "enters tapped" replacement, 614.1d/614.12).
* "This land enters tapped. As it enters, choose a color [other than blue]." (the Thriving lands, Valgavoth's Lair):
  two static abilities on one line (603.6d): "enters tapped" (614.1d) and "As it enters, choose …" (614.1c; 614.12a:
  the choice is made before it enters). One "enters_choice" replacement that also says the permanent enters tapped;
  "a color other than blue" offers the four other colors (105.1) and is recorded as the permanent's chosen color.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def entered_tapped(plan: Plan, info: dict[str, Any]) -> bool | None:
    """Did the object of an "enter" fact enter tapped? None when nothing says (it then doesn't match either way)."""
    oid = info.get("oid")
    log = plan.rules.turn_log
    if oid and log is not None:
        for entry in reversed(log.entered):
            if entry.object_id == oid:
                return entry.tapped
    return None


_COLORS = ("white", "blue", "black", "red", "green")
_TAPPED_CHOICE = re.compile(r"^~ enters tapped\. As (?:it|~) enters, choose a color(?P<other> other than "
                            r"(?P<c>white|blue|black|red|green))?\.$")
OTHER_THAN = "color other than "
CHOICE_LABELS = {OTHER_THAN + c: "Chosen color" for c in _COLORS}


def tapped_choice(text: str) -> dict[str, Any] | None:
    m = _TAPPED_CHOICE.fullmatch(text)
    if m is None:
        return None
    what = OTHER_THAN + m["c"] if m["other"] else "color"
    return {"kind": "replacement", "replacement": "enters_choice", "tapped": True,
            "effects": [{"do": "choose_value", "who": "you", "what": what, "remember": True}]}


# -- static statics (wave 10B) -- "As this land enters, choose a color other than green." on a line of its own (Manor Gate and
# the other Gates, with "This land enters tapped." as another line): the same choice (614.1c, 614.12a), no tapped part —
# "enters tapped" is its own replacement (614.1d) that applies to the same entering.
_STANDALONE = re.compile(r"^As (?:it|~) enters, choose a color other than (?P<c>white|blue|black|red|green)\.$")


def standalone_choice(text: str) -> dict[str, Any] | None:
    m = _STANDALONE.fullmatch(text)
    if m is None:
        return None
    return {"kind": "replacement", "replacement": "enters_choice",
            "effects": [{"do": "choose_value", "who": "you", "what": OTHER_THAN + m["c"], "remember": True}]}


# -- "When Enduring Curiosity dies, if it was a creature, return it to the battlefield under its owner's control. It's an
# enchantment." (the Enduring cycle): 611.2e — a resolving ability that puts a nontoken permanent onto the battlefield and
# says it "is [characteristic]" has that effect apply simultaneously with its entering: it never enters as a creature
# ("whenever a creature enters" doesn't see it; the turn log records it as an enchantment). Card types SET (205.1a: its
# creature types go with the creature type, 205.1b's "in addition" isn't said); for as long as it is that object (611.2a,
# 400.7). "if it was a creature" reads the object as it last existed (603.4, 608.2h: once returned as an enchantment it
# doesn't come back again).
def enters_as(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    cards = [c for c in effects._cards(plan, ctx, e["who"])
             if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")]
    if not cards:
        return True
    effects.become(plan, ctx, {"who": e["who"], "types": list(e["types"]), "duration": "permanent"})
    log = plan.rules.turn_log
    for cid in cards:  # (611.2e: what it entered as)
        card = plan.state.cards[cid]
        now = plan.ch(card)
        for entry in log.entered if log is not None else []:
            if entry.card == cid and entry.object_id == plan.oid(card):
                entry.types, entry.subtypes = sorted(now.types), sorted(now.subtypes)
    return True


PRIMITIVES = {"enters_as": enters_as}


def enters_as_bound(effects: list[dict[str, Any]]) -> bool:
    """Is every "It's an enchantment." about the card the instruction just before it returned to the battlefield?"""
    for i, e in enumerate(effects):
        if e.get("do") != "enters_as":
            continue
        prev = effects[i - 1] if i else {}
        if prev.get("do") != "return_card" or prev.get("to") != "battlefield" or not prev.get("as") \
                or e.get("who") != "ref:" + prev["as"]:
            return False
    return True


def color_options(what: str) -> list[str] | None:
    """The colors "a color other than <color>" offers (None: not that choice)."""
    if not what.startswith(OTHER_THAN) or what[len(OTHER_THAN):] not in _COLORS:
        return None
    return [c.capitalize() for c in _COLORS if c != what[len(OTHER_THAN):]]
