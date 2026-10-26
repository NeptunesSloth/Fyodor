"""-- "any opponent may [cost]. If they do, ..." (wave 110C) -- 118.12, 101.4: every opponent is offered the payment in turn order (as Desecration Demon,
counters100j.demon); what follows happens once if any paid.

* Transforming Flourish: "…its controller exiles cards from the top of their library until they exile a nonland card, then they may cast that card without paying
  its mana cost." The destroyed permanent's controller (not the spell's) is "you" for the cast (608.2g, 118.9; ``as_ref110c`` + tempting.as_player_end).
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


_FLOURISH = ("Destroy target artifact or creature you don't control. If that permanent is destroyed this way, its controller exiles cards from the top of their "
             "library until they exile a nonland card, then they may cast that card without paying its mana cost.")


def flourish() -> Any:
    from app.rules import wave110c_core

    es, target, flag = wave110c_core.read(_FLOURISH.split(", then they may")[0] + ".")
    assert [e["do"] for e in es] == ["destroy", "only_if", "exile_top"]
    es[1]["skip"] = 4  # the exile, the switch of "you", the cast and the switch back all depend on "destroyed this way"
    es += [{"do": "as_ref110c", "who": es[2]["player"]}, {"do": "free_cast", "zone": "found", "filter": None, "mv": None, "optional": True}, {"do": "as_player_end"}]
    return es, target, flag


def as_ref(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The next instructions (up to ``as_player_end``) are done by the player the reference names, as "you" (they are the controller of what was destroyed)."""
    from app.rules import effects

    ctx.setdefault("controllers", []).append(ctx["controller"])
    ctx["controller"] = effects._players(plan, ctx, e["who"])[0]
    return True


def any_opp(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """One optional payment per opponent in turn order, then the next ``skip`` effects only if some opponent paid."""
    opponents = [p for p in plan.apnap() if p != ctx["controller"] and p in plan.live()]
    binds = [f"any110c_{p}" for p in opponents]
    pays = [{"do": "optional_payment", "who": f"player:{p}", "cost": e["cost"], "bind": b} for p, b in zip(opponents, binds, strict=True)]
    ctx["effects"][ctx["next"]:ctx["next"]] = [*pays, {"do": "only_if", "cond": {"any_paid100j": binds}, "skip": e["skip"]}]
    return True


PRIMITIVES = {"any_opp110c": any_opp, "as_ref110c": as_ref}
