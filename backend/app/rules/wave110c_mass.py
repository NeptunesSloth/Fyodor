"""-- mass library effects (wave 110C) -- every player reveals from the top of their library and the permanents enter together.

* Over the Top: "Each player reveals a number of cards from the top of their library equal to the number of nonland permanents they control, puts
  all permanent cards they revealed this way onto the battlefield, and puts the rest into their graveyard." The counts are fixed before anything
  is revealed (608.2h); a reveal shows the cards to everyone (701.20a); the permanent cards (110.4: not instants or sorceries) enter at the same
  time (603.6a, 614.12), an Aura that isn't being cast has its controller choose what it enchants, never a permanent entering with it (303.4f), and
  one with nothing to enchant stays in the library (303.4g); then everything revealed that did not enter goes to its owner's graveyard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
REVEALED = "_revealed110c"


def reveal_tops(plan: Plan, ctx: Context, counts: dict[str, int]) -> dict[str, list[str]]:
    """Each player's top ``counts[p]`` cards revealed (all of them, if the library has fewer); bound as the objects revealed this way."""
    from app.game.state import zone_key
    from app.rules import context

    out: dict[str, list[str]] = {}
    for pid in plan.apnap():
        top = plan.state.zones.get(zone_key(pid, "library"), [])[: max(0, counts.get(pid, 0))]
        if top:
            plan.do({"type": "reveal_top", "player": pid, "count": len(top), **({"source": str(ctx["name"])[:200]} if ctx.get("name") else {})}, actor=ctx["controller"])
        out[pid] = list(top)
    context.bind_objects(plan, ctx, REVEALED, [c for p in out for c in out[p]])
    return out


def enter_permanents(plan: Plan, ctx: Context, revealed: dict[str, list[str]]) -> bool:
    """Every player puts the permanent cards they revealed onto the battlefield together; the rest follow (``rest_to_graveyard110c``)."""
    from app.rules import attachments
    from app.rules.characteristics import PERMANENT_TYPES

    entries = [{"card": c, "player": p, "actor": ctx["controller"], "tapped": False} for p in revealed for c in revealed[p]
               if plan.ch(plan.state.cards[c]).types & PERMANENT_TYPES]
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "rest_to_graveyard110c"}]
    return attachments.enter(plan, entries, ctx) if entries else True


def over_the_top(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    counts = {p: sum(1 for c in plan.state.cards.values() if c.controller == p and c.zone.endswith(":battlefield") and plan.in_game(c)
                     and not plan.ch(c).is_land) for p in plan.live()}
    return enter_permanents(plan, ctx, reveal_tops(plan, ctx, counts))


def rest_to_graveyard(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The revealed cards that are still in a library (not the same object after they entered) go to their owners' graveyards."""
    from app.rules import context

    rest = [c for c in context.objects(plan, ctx, REVEALED) if plan.state.cards[c].zone.endswith(":library")]
    for pid in plan.apnap():
        mine = [c for c in rest if plan.state.cards[c].owner == pid]
        if mine:
            plan.do({"type": "move", "card_ids": mine, "to": {"player": pid, "zone": "graveyard"}}, actor=ctx["controller"])
    return True


PRIMITIVES = {"over_the_top110c": over_the_top, "rest_to_graveyard110c": rest_to_graveyard}
