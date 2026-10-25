"""Kusari-Gama (wave 110C): "Whenever equipped creature deals damage to a blocking creature, this Equipment deals that much damage to each other
creature defending player controls." 120.1, 508.5 (the defending player is the one the damaging attacker attacks), 509.1g (a blocking creature).

The trigger is the plain "deals damage to a creature" one, narrowed by cond ``blocking110c`` (triggers.py): the event then names the blocker
(``other``) and the attacker's defending player. "Each other creature" is every creature that player controls except the damaged blocker.
"""

from __future__ import annotations

from typing import Any

from app.rules.plan import Plan

_TEXT = ("Whenever equipped creature deals damage to a blocking creature, this Equipment deals that much damage to each other creature "
         "defending player controls.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.text != _TEXT:
        return None
    from dataclasses import replace

    from app.rules import scripts

    native = scripts.define(replace(ability, text="Whenever equipped creature deals damage to a creature, this Equipment deals that much damage to each other creature."), ch)
    if native is None or [e.get("do") for e in native["effects"]] != ["damage"]:
        return None
    native["cond"] = {**native["cond"], "blocking110c": True}
    native["effects"] = [{**native["effects"][0], "do": "kusari110c"}]
    return native


def kusari(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    ev = ctx.get("event") or {}
    other, defended = ev.get("other"), ev.get("defended")
    amount = int(ev.get("amount") or 0)
    if not other or not defended or amount <= 0:
        return True
    keep = [c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == defended
            and plan.ch(c).is_creature and plan.oid(c) != other.get("object_id")]
    if keep:
        effects.PRIMITIVES["damage"](plan, ctx, {**e, "do": "damage", "who": "union:" + "+".join(f"object:{plan.oid(c)}" for c in keep), "n": amount})
    return True


PRIMITIVES = {"kusari110c": kusari}
