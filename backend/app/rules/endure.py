"""-- endure (wave 6D) -- "When this creature enters, it endures 2." (Fortress Kin-Guard, Dusyut Earthcarver …)

701.63a: to endure N, the permanent's controller creates an N/N white Spirit creature token unless they put N +1/+1
counters on that permanent. 701.63b: endure 0 does nothing. Researched against CR 2026-09-25.

The choice is made as the instruction is carried out (608.2c). A permanent that is no longer on the battlefield (or
is a new object, 400.7) can't get the counters, so its last controller simply creates the token. The chosen half is
then carried out by the ordinary primitives (``add_counters`` through the counter choke point, ``create_token``
through the token choke point: replacement effects apply, 614), put in the endure effect's place. Only "~" / "it"
meaning this permanent is read (the trigger's own object).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_PATTERN = re.compile(r"^(?P<o>it|~|this creature) endures (?P<n>\d+)$")


def _build(m: re.Match[str]) -> tuple[list[dict[str, Any]], Any]:
    return [{"do": "endure", "who": "it" if m["o"] == "it" else "self", "n": int(m["n"])}], None


TEMPLATES: list[tuple[re.Pattern[str], Any]] = [(_PATTERN, _build)]


def _spirit(n: int) -> dict[str, Any]:
    return {"name": "Spirit", "power": str(n), "toughness": str(n), "colors": ["W"],
            "type_line": "Token Creature — Spirit", "text": ""}


def _carry_out(plan: Plan, ctx: dict[str, Any], e: dict[str, Any], half: dict[str, Any]) -> None:
    """Put the chosen half in the endure effect's place and go on with the resolution."""
    effects = list(ctx["effects"])
    effects[ctx["next"] - 1] = half
    ctx["effects"] = effects
    ctx["next"] -= 1


def endure(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.effects import _cards
    from app.rules.plan import decide

    n = int(e.get("n") or 0)
    if n <= 0:
        return True  # 701.63b
    found = [c for c in _cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    if not found:  # (it left: no counters can be put on it, so the token, 701.63a)
        player = ctx["controller"]
        _carry_out(plan, ctx, e, {"do": "create_token", "who": f"player:{player}", "n": 1, "token": _spirit(n)})
        return True
    card = plan.state.cards[found[0]]
    name = card.name or "It"
    decide(plan, player=card.controller, kind="choose_one", prompt=f"{name} endures {n}: +1/+1 counters or a Spirit token?",
           options=[DecisionOption(id="counters", label=f"Put {n} +1/+1 counter{'s' if n > 1 else ''} on {name}"),
                    DecisionOption(id="token", label=f"Create a {n}/{n} white Spirit token")],
           resume={"step": "endure", "ctx": ctx, "e": e, "card": card.id, "object": plan.oid(card)}, source=card)
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    n = int(e["n"])
    card = plan.state.cards.get(d.resume["card"])
    here = card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == d.resume["object"]
    if chosen and chosen[0] == "counters" and here:
        half = {"do": "add_counters", "who": f"object:{d.resume['object']}", "kind": "+1/+1", "n": n}
    else:
        half = {"do": "create_token", "who": f"player:{d.player}", "n": 1, "token": _spirit(n)}
    _carry_out(plan, ctx, e, half)
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"endure": endure}
