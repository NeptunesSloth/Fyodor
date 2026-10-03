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


def color_options(what: str) -> list[str] | None:
    """The colors "a color other than <color>" offers (None: not that choice)."""
    if not what.startswith(OTHER_THAN) or what[len(OTHER_THAN):] not in _COLORS:
        return None
    return [c.capitalize() for c in _COLORS if c != what[len(OTHER_THAN):]]
