"""-- crew & saddle (wave 23D) -- the creatures that crew a Vehicle or saddle a Mount, and the saddled designation.
Researched against CR 2026-09-25.

* 702.171a: "Saddle N" means "Tap any number of other untapped creatures you control with total power N or greater: This
  permanent becomes saddled until end of turn. Activate only as a sorcery." Crew's counterpart is app/rules/casting.py ``crew``;
  both tap the creatures as a cost, so a creature that "crews a Vehicle" / "saddles a permanent" is one tapped to pay it
  (702.122b, 702.171c) and a Vehicle / Mount is "crewed by" / "saddled by" it (702.122c).
* 702.171b: saddled is a designation with no rules meaning of its own; it lasts until end of turn or until the permanent leaves the
  battlefield (a new object then). It is read from this turn's log (TurnFact kind "saddled", the Mount's object id), which a new turn
  starts afresh, so nothing has to be cleaned up.
* 702.122e: "Whenever [this Vehicle] becomes crewed" means whenever a crew ability of it resolves (effects.animate emits "crewed").
* "the creatures that crewed / saddled it this turn" (702.122c, 702.171c): this turn's facts "crew" / "saddle" (the creature's object,
  ``source`` the Vehicle's / Mount's object), kept even when a creature has left since (it is then asked for as it last existed).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import TurnFact, emit, turn_log_now
from app.rules.characteristics import Characteristics

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

SADDLE = re.compile(r"^saddle (?P<n>\d+)$", re.IGNORECASE)


def saddle_power(ch: Characteristics, index: int) -> int | None:
    """Saddle N (702.171a) on ability line ``index``: N, or None."""
    for ab in ch.abilities:
        if ab.index == index and ab.kind == "keywords":
            m = SADDLE.fullmatch(ab.text.strip().rstrip("."))
            if m:
                return int(m["n"])
    return None


def tapped_to_pay(plan: Plan, kind: str, creatures: list[str], source: CardInstance) -> None:
    """These creatures were tapped to pay the cost of ``source``'s crew / saddle ability (``kind``: "crew" | "saddle"): the facts
    for "that crewed it this turn" and one event each for "Whenever this creature crews a Vehicle" (702.122b, 702.171c)."""
    log = turn_log_now(plan.state)
    for cid in creatures:
        c = plan.state.cards[cid]
        if log is not None:
            ch = plan.ch(c)  # -- this-turn state (wave 33D) -- what it was as it was tapped: "if an Assassin crewed it this turn" (Adrestia, 702.122c)
            log.facts.append(TurnFact(kind=kind, player=plan.actor, object_id=plan.oid(c), source=plan.oid(source), types=sorted(ch.types),
                                      subtypes=sorted(ch.subtypes), supertypes=sorted(ch.supertypes)))
        emit(plan.state, "crew_tapped" if kind == "crew" else "saddle_tapped", object_id=plan.oid(c), card=cid, player=plan.actor,
             source=plan.oid(source), by_card=source.id)


def became_saddled(plan: Plan, card: CardInstance) -> None:
    """702.171b: the permanent became saddled (its saddle ability resolved)."""
    log = turn_log_now(plan.state)
    if log is not None:
        log.facts.append(TurnFact(kind="saddled", player=card.controller, object_id=plan.oid(card)))
    emit(plan.state, "saddled", object_id=plan.oid(card), card=card.id, player=card.controller)


def is_saddled(plan: Plan, card: CardInstance) -> bool:
    oid = plan.oid(card)
    return plan.rules.turn_log.turn == plan.state.turn.number and any(
        f.kind == "saddled" and f.object_id == oid for f in plan.rules.turn_log.facts)


def tapped_for(plan: Plan, kind: str, creature_oid: str | None, source_oid: str | None) -> bool:
    """Was this creature tapped this turn to pay ``kind`` ("crew" / "saddle") of that Vehicle / Mount?"""
    log = plan.rules.turn_log
    return log.turn == plan.state.turn.number and any(
        f.kind == kind and f.object_id == creature_oid and f.source == source_oid for f in log.facts)


def saddled_effect(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The resolution of a saddle ability: the source becomes saddled (702.171a); gone from the battlefield, it can't."""
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == ctx.get("source_object"):
        became_saddled(plan, card)
    return True


def saddle_it(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """-- trigger other (wave 44B) -- "Whenever a Mount you control enters, it becomes saddled until end of turn." (Kolodin): the designation 702.171b, whichever
    way a permanent gets it; one no longer on the battlefield can't."""
    from app.rules.effects import _cards

    for cid in _cards(plan, ctx, e["who"]):
        card = plan.state.cards.get(cid)
        if card is not None and card.zone.endswith(":battlefield"):
            became_saddled(plan, card)
    return True


PRIMITIVES = {"saddled": saddled_effect, "saddle_it": saddle_it}
