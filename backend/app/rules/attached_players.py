"""-- attached events (wave 4L) -- Curses that share: "Whenever enchanted player is attacked, create a Gold token.
Each opponent attacking that player does the same." (Curse of Opulence, Verbosity, Disturbance, Vitality),
researched against CR 2026-09-25 and the Wizards rulings on these Curses (2017-08-25).

* The trigger (508.3b, app/rules/events.py) fires once per declaration in which a creature attacks the enchanted
  player — not only a planeswalker they control (ruling).
* "Each opponent attacking that player": each opponent of the Curse's controller who, as the ability resolves,
  controls a creature attacking the enchanted player (ruling: "A player is attacking another player if they control
  a creature that's attacking that player. If no creatures are attacking the enchanted player as a Curse's ability
  resolves …, only the Curse's controller performs its actions."). "does the same": the same instructions with that
  player as "you", after the Curse's controller (608.2c: in the order written).
* The enchanted player is the one the Curse is attached to as the ability resolves, or as it last was on the
  battlefield (608.2h) if it left.

Only instructions that name no target and are done by "you" are repeated ("create a Gold token", "you draw a
card", "you gain 2 life"); anything else leaves the ability manual. The players are the effect's ``who``:
``"attacking_opponents"`` (app/rules/effects.py ``_players``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_SAME = " Each opponent attacking that player does the same."


def split_same(body: str, cond: dict[str, Any] | None) -> tuple[bool, str]:
    """(does the body end with the sharing sentence on an "enchanted player is attacked" trigger, the rest)."""
    if body == "untap all nonland permanents you control. Each opponent attacking that player untaps all nonland permanents they control.":
        body = body.removesuffix(" Each opponent attacking that player untaps all nonland permanents they control.") + _SAME  # (wave 110D: Curse of Bounty, the same in other words)
    if not body.endswith(_SAME) or cond is None or cond.get("event") != "you_attack" \
            or cond.get("defender") != "enchanted_player":
        return False, body
    return True, body[: -len(_SAME)]


_ONE_PLAYER = {"create_token", "draw", "gain_life", "lose_life", "scry", "surveil", "mill"}


def does_the_same(parsed: tuple[list[dict[str, Any]], Any, bool]) -> tuple[list[dict[str, Any]], Any, bool] | None:
    effects, target, optional = parsed
    if not target and not optional and len(effects) == 1 and effects[0].get("do") == "untap" and '"controller":"you"' in str(effects[0].get("who")):
        # -- Curse of Bounty (wave 110D) -- "untap all nonland permanents you control": each attacking opponent's own (selector read as that player's)
        return [*effects, {"do": "untap_each110d", "who": effects[0]["who"]}], target, optional
    if target or optional or not effects or any(e.get("do") not in _ONE_PLAYER or e.get("who") != "you" for e in effects):
        return None
    return effects + [{**e, "who": "attacking_opponents"} for e in effects], target, optional


def enchanted_player(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    """The Aura's player now, or its last attachment for the exact departed source object (608.2h)."""
    src = plan.state.cards.get(ctx.get("source_card") or "")
    if src is not None and src.zone.endswith(":battlefield") and (ctx.get("source_object") is None or plan.oid(src) == ctx["source_object"]):
        player = src.attached_player
    else:
        snap = plan.rules.lki.get(ctx.get("source_object") or "")
        player = snap.attached_player if snap is not None else None
    return [player] if player is not None and player in plan.live() else []


def attacking_opponents(plan: Plan, ctx: dict[str, Any]) -> list[str]:
    me = ctx["controller"]
    players = enchanted_player(plan, ctx)
    if len(players) != 1:
        return []
    enchanted = players[0]
    live = plan.live()
    return [p for p in plan.state.seat_order if p in live and p != me and any(
        c.controller == p and c.attacking is not None and c.attacking.kind == "player" and c.attacking.id == enchanted
        and c.zone.endswith(":battlefield")
        for c in plan.state.cards.values())]
