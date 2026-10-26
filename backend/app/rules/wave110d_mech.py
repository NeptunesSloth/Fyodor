"""-- Mechtitan Core and The Enigma Jewel // Locus of Enlightenment (wave 110D) -- "{5}, Exile this Vehicle and four other artifact creatures and/or Vehicles you control: Create Mechtitan, a legendary 10/10 Construct artifact
creature token with flying, vigilance, trample, lifelink, and haste that's all colors. When that token leaves the battlefield, return all cards exiled with this Vehicle except this
card to the battlefield tapped under their owners' control."

602.2: the cost is "Exile ~" plus "Exile four other artifact creatures and/or Vehicles you control" (a union selector, costs._selector). 607.2a: the cards exiled as the cost are
the ones "exiled with this Vehicle" (linked by the ability's own exile instruction); the Core itself is the one excluded ("except this card"), so only the others are recorded
(exiled_with.record). 603.7: the delayed trigger of the token's leaving returns the still-exiled ones tapped (400.7: a card that left exile is another object; a token ceased to exist).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.rules.plan import Plan

LINE = ("{5}, Exile ~ and four other artifact creatures and/or Vehicles you control: Create Mechtitan, a legendary 10/10 Construct artifact creature token with flying, vigilance, "
        "trample, lifelink, and haste that's all colors. When that token leaves the battlefield, return all cards exiled with ~ except this card to the battlefield tapped under their owners' control.")
COST = "{5}, Exile ~, Exile four other artifact creatures and/or Vehicles you control"


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    base = LINE.split(": ")[1].split(" When that")[0]
    plain = COST.replace(" and/or Vehicles", "")  # (the union selector is only in the cost the definition is given back)
    d = scripts.define(replace(ability, text=f"{plain}: {base} When that token leaves the battlefield, draw a card.", cost=plain), ch)
    if d is None or d["effects"][-1].get("do") != "deferred:draw":
        return None
    back = {"do": "deferred:return_card", "who": "exiled_with", "to": "battlefield", "tapped": True, "under": "owner"}
    return {**d, "cost": COST, "effects": [{"do": "mech_link110d"}, *d["effects"][:-1], back]}


LOCUS = "~ has each activated ability of the exiled cards used to craft it. You may activate each of those abilities only once each turn."


def locus(ability: Any, ch: Any) -> dict[str, Any] | None:
    """The Enigma Jewel // Locus of Enlightenment: 113.10 / 613.1f, each activated ability of the materials (702.167c) lent like Myr Welder's, each once a turn (602.5b)."""
    from app.rules import scripts

    d = scripts.define(replace(ability, text="~ has all activated abilities of all cards exiled with it."), ch)
    if d is None or not d.get("abilities_of"):
        return None
    return {**d, "abilities_of": {**d["abilities_of"], "linked": False, "crafted": True, "once": True}}


def link(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import exiled_with

    paid = plan.rules.payments.get(plan.oid(ctx["stack_id"])) if ctx.get("stack_id") else None
    if paid is not None:
        exiled_with.record(plan, ctx, [c for c in paid.exiled if c != ctx.get("source_card")])
    return True


PRIMITIVES = {"mech_link110d": link}
