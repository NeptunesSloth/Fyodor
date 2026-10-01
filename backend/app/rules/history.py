"""This turn's history, for the conditions that look back in time (CR 608.2i): "if you attacked this
turn" (Raid), "if a creature died this turn" (Morbid), "if a permanent left the battlefield under
your control this turn" (Revolt), "if an opponent lost life this turn", "if you gained 3 or more
life this turn", "if you've drawn two or more cards this turn", "if you lost life last turn", "if you
descended this turn" (700.11: a permanent card — never a token — was put into your graveyard from
anywhere, and needn't still be there).

The facts are recorded deterministically as the game happens (app/game/rules_state.py ``TurnLog``:
``track`` / ``emit`` for what the table shows — departures, life, draws — and the declaration of
attackers, 508.1), so they survive saves, undo / redo and replay. This module only reads them:

* an effect like this "is not taking any actions on those objects", so they needn't still be where
  they were, nor meet the criteria now, as long as they did then (608.2i): a creature that died is
  read as it last existed on the battlefield — its last known information, with the card types the
  layers gave it (an animated land or a crewed Vehicle was a creature) when the rules engine moved
  it, else its printed ones;
* a creature put onto the battlefield attacking was never declared as an attacker, so it never
  "attacked" (508.4) — only ``declare_attackers`` records an attack;
* "dies" is being put into a graveyard from the battlefield (700.4); "leaves the battlefield" is
  moving to any other zone — a token counts (it moves before it ceases to exist, 111.7).
"""

from __future__ import annotations

from typing import Any

from app.game.rules_state import Departure, TurnLog
from app.rules import characteristics as chars
from app.rules.characteristics import PERMANENT_TYPES
from app.rules.plan import Plan


def log_for(plan: Plan, last: bool = False) -> TurnLog:
    """This turn's log (or the turn before's); an empty one if nothing was recorded then."""
    rules = plan.rules
    n = plan.state.turn.number
    if last:
        for log in (rules.turn_log, rules.last_turn_log):
            if log is not None and log.turn == n - 1:
                return log
        return TurnLog()
    return rules.turn_log if rules.turn_log.turn == n else TurnLog()


def departed_types(plan: Plan, d: Departure) -> set[str]:
    """What a permanent was as it last existed on the battlefield (608.2i, 700.4)."""
    if d.types is not None:
        return set(d.types)
    snap = plan.rules.lki.get(d.object_id)
    if snap is None:
        return set()
    from app.rules.triggers import _snapshot_card  # (triggers imports the modules that import this one)

    return set(_snapshot_card(plan, snap)[1].types)


def creatures_died(plan: Plan, *, controller: str | None = None, last: bool = False) -> int:
    """How many creatures were put into a graveyard from the battlefield (this turn), optionally only
    those ``controller`` controlled as they died."""
    return sum(1 for d in log_for(plan, last).left
               if d.to == "graveyard" and (controller is None or d.controller == controller)
               and "Creature" in departed_types(plan, d))


def permanent_cards_entered(plan: Plan, player: str, *, last: bool = False) -> int:
    """700.11: how many permanent cards were put into ``player``'s graveyard from anywhere this turn
    ("descended") — counted whether or not they're still there. A token is no card (111.1)."""
    n = 0
    for arrival in log_for(plan, last).entered_graveyard:
        card = plan.state.cards.get(arrival.card)
        if arrival.owner == player and card is not None and chars.of(card, plan.info).types & PERMANENT_TYPES:
            n += 1
    return n


def holds(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    """Is this ``{"history": …}`` condition true for the ability's controller right now?"""
    kind = cond["history"]
    me: str = ctx["controller"]
    n = int(cond.get("n", 1))
    log = log_for(plan, bool(cond.get("last")))
    if kind == "attacked":
        return me in log.attacked
    if kind == "gained":
        return log.gained.get(me, 0) >= n
    if kind == "drew":
        return log.drew.get(me, 0) >= n
    if kind == "spells":
        return plan.rules.spells_this_turn(me, plan.state.turn.number) >= n
    if kind == "lost":
        who = cond.get("who", "you")
        players = [me] if who == "you" else [p for p in plan.live() if p != me] if who == "opponent" else list(plan.live())
        return any(log.lost.get(p, 0) >= n for p in players)
    if kind == "left_graveyard":
        return me in log.left_graveyard
    if kind == "descended":
        return permanent_cards_entered(plan, me, last=bool(cond.get("last"))) >= n
    if kind == "died":
        return creatures_died(plan, controller=me if cond.get("who") == "you" else None, last=bool(cond.get("last"))) >= n
    if kind == "left":
        return sum(1 for d in log.left if cond.get("who") != "you" or d.controller == me) >= n
    if kind == "entered":  # -- refused modal/conditional (wave 3R1) --
        return entered(plan, ctx, cond, log) >= n
    if kind == "entered_self":
        return any(e.object_id == _source_object(plan, ctx) for e in log.entered)
    raise ValueError(f"unknown history condition {cond!r}")


# -- refused modal/conditional (wave 3R1) --
def entered(plan: Plan, ctx: dict[str, Any], cond: dict[str, Any], log: TurnLog) -> int:
    """How many permanents matching ``cond["sel"]`` entered the battlefield under the ability controller's control
    this turn ("another": not the source object itself). 608.2i: read as each was when it entered — its card types
    and subtypes then — and otherwise as it is, or as it last existed if it has left since."""
    from dataclasses import replace

    from app.rules import selectors
    from app.rules.triggers import _snapshot_card  # (triggers imports the modules that import this one)

    sel = selectors.from_key(cond["sel"])
    me = ctx["controller"]
    n = 0
    for e in log.entered:
        if e.controller != me or (cond.get("other") and e.object_id == _source_object(plan, ctx)):
            continue
        card = plan.state.cards.get(e.card)
        if card is not None and plan.oid(card) == e.object_id:
            ch = plan.ch(card)
        else:
            snap = plan.rules.lki.get(e.object_id)
            if snap is None:
                continue  # (gone with no last known information: a token that left, long ago)
            card, ch = _snapshot_card(plan, snap)
        if e.types is not None:
            ch = replace(ch, types=frozenset(e.types), subtypes=frozenset(e.subtypes or ()))
        probe = card.model_copy(update={"zone": f"{me}:battlefield", "controller": me}) \
            if not card.zone.endswith(":battlefield") else card
        if selectors.matches(plan, replace(sel, zones=("battlefield",), controller=None, other=False), probe, ch, me, None):
            n += 1
    return n


def _source_object(plan: Plan, ctx: dict[str, Any]) -> str | None:
    """The source object: given, or — for a static or an activation restriction, which name only the source
    card — the object that card is now."""
    if ctx.get("source_object"):
        return str(ctx["source_object"])
    card = ctx.get("source_card")
    return plan.oid(card) if card and card in plan.state.cards else None
# -- end refused modal/conditional (wave 3R1) --
