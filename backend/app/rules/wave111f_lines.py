"""Wave 111F: whole Star Trek lines (trk/trc, Oracle text of 2026-10-30) the grammar reads only in other words.

* "… Then return a land card from your graveyard to your hand. If you can't, create a Treasure token." (Temporal Conqueror): the return is no
  target and not optional (608.2c), so "can't" is that your graveyard holds no such card as it would be returned (after the mill before it);
  then the other instruction instead. (The draw form, Roots of Wisdom and Inventive Iteration, is wave 110D's / 68's.)
"""

from __future__ import annotations

import copy
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_CANT = re.compile(r"^(?P<head>.+\. Then return an? [a-z ]+ card from your graveyard to your hand\.) If you can't, (?P<other>create [^.]+\.)$")
_WORF_HEAD = ("When ~ enters, for each opponent, gain control of up to one target creature that player controls with mana value 3 or less until end of turn. "
              "Untap those creatures.")
WORF = _WORF_HEAD + " Until end of turn, they become Warriors in addition to their other types and gain haste."


def _worf(ability: Any, ch: Any) -> dict[str, Any] | None:
    """Worf, Intelligence Contractor: the native "They gain haste until end of turn." plus the creature type each of those creatures gains (layer 4,
    205.1b "in addition to their other types"), until end of turn, as the grammar's singular "it becomes a Warrior in addition to its other types" is."""
    from app.rules import scripts

    d = scripts.define(replace(ability, text=_WORF_HEAD + " They gain haste until end of turn."), ch)
    if d is None or [e["do"] for e in d["effects"]] != ["gain_control", "untap", "grant"] or len({e["who"] for e in d["effects"]}) != 1:
        return None
    who = d["effects"][0]["who"]
    become = {"do": "become", "who": who, "types": [], "retain": True, "add_creature_types": ["Warrior"], "duration": "end_of_turn"}
    return {**d, "effects": [*d["effects"][:2], become, d["effects"][2]]}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == WORF:
        return _worf(ability, ch)
    m = _CANT.match(text)
    if m is None:
        return None
    d = scripts.define(replace(ability, text=m["head"]), ch)
    other = scripts.parse_effects(m["other"][:1].upper() + m["other"][1:])
    if d is None or other is None or other[1] is not None or not d.get("effects"):
        return None
    last = d["effects"][-1]
    if last.get("do") != "return_choice" or last.get("n") != 1 or last.get("upto") or last.get("to") != "hand":
        return None
    d["effects"][-1] = {"do": "return_or_else111f", "effect": last, "else": copy.deepcopy(other[0])}
    return d


def return_or_else(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Return the card when there is one to return, else carry out the other instruction ("If you can't, …")."""
    from app.rules import selectors

    effect = e["effect"]
    found = selectors.candidates(plan, selectors.from_key(effect["sel"]), ctx["controller"], ctx.get("source_card"))
    ctx["effects"][ctx["next"]:ctx["next"]] = [effect] if found else copy.deepcopy(e["else"])
    return True


PRIMITIVES = {"return_or_else111f": return_or_else}
RESUME: dict[str, Any] = {}
