"""-- "any opponent may [cost]. If they do, ..." (wave 110C) -- 118.12, 101.4: every opponent is offered the payment in turn order (as Desecration Demon,
counters100j.demon); what follows happens once if any paid.

* Transforming Flourish: read by wave110k_cards (its parse runs first).
* Vraska, the Silencer: "return that card to the battlefield tapped under your control. It's a Treasure artifact with "{T}, Sacrifice this artifact: Add one mana
  of any color," and it loses all other card types." — set as it enters (611.2e, 205.1a), entry_characteristics.from_become; its creature subtypes go with the type (205.3d).
* Reservoir Kraken: "…, if this creature is untapped, any opponent may tap an untapped creature they control. If they do, tap this creature and create a
  1/1 blue Fish creature token with "This token can't be blocked."" (the intervening "if" is checked on trigger and on resolution, 603.4)
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.oracle import AbilityText

_KRAKEN = ("At the beginning of each combat, if this creature is untapped, any opponent may tap an untapped creature they control. If they do, tap this "
           "creature and create a 1/1 blue Fish creature token with \"This token can't be blocked.\"")
_KRAKEN_NATIVE = ("At the beginning of each combat, if this creature is untapped, tap this creature and create a 1/1 blue Fish creature token with "
                  "\"This token can't be blocked.\"")


_VRASKA = ("Whenever a nontoken creature an opponent controls dies, you may pay {1}. If you do, return that card to the battlefield tapped under your control. "
           "It's a Treasure artifact with \"{T}, Sacrifice this artifact: Add one mana of any color,\" and it loses all other card types.")


def _vraska(ability: AbilityText, ch: Any) -> dict[str, Any] | None:
    from app.rules import granted, scripts

    native = scripts.define(replace(ability, text=_VRASKA.split(" It's a Treasure")[0]), ch)
    if native is None or [e.get("do") for e in native["effects"]] != ["optional_payment", "only_if", "return_card"]:
        return None
    back = {**native["effects"][2], "as": "ret110c"}
    become = {"do": "become", "who": "ref:ret110c", "types": ["Artifact"], "artifact_types": ["Treasure"], "creature_types": [], "duration": "permanent",
              "entry_as": True, "abilities": [granted.quote("{T}, Sacrifice this artifact: Add one mana of any color")]}
    return {**native, "effects": [*native["effects"][:2], back, become]}


def definition(ability: AbilityText, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text == _VRASKA:
        return _vraska(ability, ch)
    if ability.text.replace(ch.name or "~", "this creature") != _KRAKEN:
        return None
    native = scripts.define(replace(ability, text=_KRAKEN_NATIVE), ch)
    if native is None or [e.get("do") for e in native["effects"]] != ["only_if", "tap", "create_token"]:
        return None
    guard, *rest = native["effects"]  # the resolution check of the "if" also skips the offers (skip 3 = the offer, the tap and the Fish)
    return {**native, "effects": [{**guard, "skip": 3}, {"do": "any_opp110c", "cost": "Tap an untapped creature you control", "skip": 2}, *rest]}


def any_opp(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """One optional payment per opponent in turn order, then the next ``skip`` effects only if some opponent paid."""
    opponents = [p for p in plan.apnap() if p != ctx["controller"] and p in plan.live()]
    binds = [f"any110c_{p}" for p in opponents]
    pays = [{"do": "optional_payment", "who": f"player:{p}", "cost": e["cost"], "bind": b} for p, b in zip(opponents, binds, strict=True)]
    ctx["effects"][ctx["next"]:ctx["next"]] = [*pays, {"do": "only_if", "cond": {"any_paid100j": binds}, "skip": e["skip"]}]
    return True


PRIMITIVES = {"any_opp110c": any_opp}
