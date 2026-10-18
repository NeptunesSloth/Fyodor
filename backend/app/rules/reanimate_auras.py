"""-- reanimation Auras (wave 51F) -- Animate Dead, Dance of the Dead ("Enchant creature card in a graveyard") and Necromancy, researched against CR 2026-09-25.

* The Aura spell targets a creature card in any graveyard (303.4a, 115.1b: ``attachments.GRAVE``) and enters "attached" to it (608.3c). That card is not a permanent, so the
  link is ``RulesState.aura_links`` (``attachments.attach``), not ``attached_to``; while the card is still that object in a graveyard the Aura stays (704.5m, sba.py), otherwise it
  goes to the graveyard (303.4c). Protection and hexproof don't function in a graveyard, so any creature card there may be chosen (Animate Dead's rulings, 2016-06-08).
* The enters trigger ("if it's on the battlefield", 603.4: checked as it resolves, ``{"test": "on_battlefield"}``) makes the Aura lose "enchant creature card in a graveyard" and gain
  "enchant creature put onto the battlefield with this Aura" (Necromancy becomes an Aura with it): one continuous effect without a duration (613.1d, 613.1f, ``effects.become``).
  Then the creature card (the enchanted one, 303.4m; Necromancy's target) is put onto the battlefield under your control and the Aura is attached to it (701.3): the new
  enchant ability allows exactly that object (``attachments.PUT_WITH``), which is why Aura Graft can't move the Aura. A creature that can't be enchanted (protection from black),
  or that didn't enter, leaves the Aura unattached: it goes to the graveyard (704.5m).
* "When this Aura leaves the battlefield, that creature's controller sacrifices it" is a delayed triggered ability the enters trigger creates as it resolves (603.7a, e): it
  triggers once (603.7b), for that Aura leaving, and sacrifices the creature only while it is still that object on the battlefield (603.7c, 400.7), whoever controls it then (701.21a).
  If the Aura isn't on the battlefield as the trigger resolves, none of this happens (2016-06-08).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.rules import attachments, delayed

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

Context = dict[str, Any]
_QUOTED = r"\"enchant creature put onto the battlefield with (?:~|‹granter›)\.\" "
_LOSES = re.compile(r"^When ~ enters, if it's on the battlefield, it loses \"enchant creature card in a graveyard\" and gains " + _QUOTED
                    + r"(?:Return enchanted creature card to|Put enchanted creature card onto) the battlefield(?P<tapped> tapped)? under your control and attach ~ to it\. "
                    r"When ~ leaves the battlefield, that creature's controller sacrifices it\.$")
_BECOMES = re.compile(r"^When ~ enters, if it's on the battlefield, it becomes an Aura with " + _QUOTED
                      + r"Put target creature card from a graveyard onto the battlefield under your control and attach ~ to it\. "
                      r"When ~ leaves the battlefield, that creature's controller sacrifices it\.$")
LABEL = "an Aura that can enchant only a creature it put onto the battlefield"


def define(text: str, ch: Characteristics) -> dict[str, Any] | None:
    """The enters trigger of Animate Dead / Dance of the Dead (the enchanted card) or Necromancy (a target), or None for any other wording."""
    loses = _LOSES.match(text)
    if loses is None and _BECOMES.match(text) is None:
        return None
    swap: dict[str, Any] = {"do": "become", "who": "self", "abilities": [f"Enchant creature put onto the battlefield with {ch.name}"], "duration": "permanent",
                            "label": LABEL, "marker": "enchants only a creature it put onto the battlefield"}
    if loses is not None:
        gone = [a.index for a in ch.abilities if a.kind == "keywords" and "enchant" in a.keywords]
        if len(gone) != 1:
            return None
        back: dict[str, Any] = {"do": "return_enchanted", "tapped": bool(loses["tapped"]), "as": "e0"}
        swap["lose_index"] = gone
    else:
        back = {"do": "return_card", "who": "target", "to": "battlefield", "tapped": False, "under": "you", "as": "e0"}
        swap["add_creature_types"] = ["Aura"]
    leaves = delayed.wrap_when([{"do": "sacrifice", "who": "ref:e0", "by": "controller"}], {"kind": "event", "event": "leave", "open": True}, who="self")
    return {"kind": "triggered", "trigger": "enters_self", "optional": False, "target": None if loses is not None else {"what": attachments.GRAVE},
            "effects": [{"do": "only_if", "cond": {"object": "self", "test": "on_battlefield"}}, swap, back, {"do": "attach_returned"}, *leaves]}


def return_enchanted(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Return enchanted creature card to the battlefield under your control" (303.4m): the card in a graveyard this Aura enchants, if it is still there."""
    from app.rules import effects

    src = plan.state.cards.get(ctx.get("source_card") or "")
    cards = attachments.enchanted_cards(plan, src) if src is not None else []
    return effects._return_cards(plan, ctx, {"to": "battlefield", "under": "you", "tapped": e["tapped"], "as": e["as"]}, cards)


def attach_returned(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"... and attach this Aura to it" (701.3): the creature it put onto the battlefield (the object it became there, 400.7) is the one its new enchant ability allows."""
    from app.rules import effects

    mine, new = effects._cards(plan, ctx, "self"), effects._cards(plan, ctx, "ref:e0")
    if mine and new:
        plan.rules.aura_links[plan.oid(mine[0])] = [plan.oid(c) for c in new]
        attachments.attach(plan, mine[0], new[0], ctx["controller"])  # (doesn't move if it can't be enchanted, 303.4j: 704.5m then ends it)
    return True


PRIMITIVES = {"return_enchanted": return_enchanted, "attach_returned": attach_returned}
