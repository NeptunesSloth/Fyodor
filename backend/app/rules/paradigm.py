"""-- keywords (wave 50H) -- paradigm (CR 702.192), researched against the stored Comprehensive Rules (2026-09-25).

* 702.192a — "Paradigm" is two spell abilities: "Exile this spell." and "If this is the first time a spell you control with this spell's name has resolved this game,
  at the beginning of each of your precombat main phases for the rest of the game, create a copy of this object in exile. You may cast the copy without paying its mana
  cost." The spell gets one more instruction at its end (oracle.parse_abilities: "Set up the paradigm of ~."): the card is exiled instead of going to the
  graveyard (614.1a, engine.leave_stack ``exile_if_graveyard``), and the first time its controller resolves a spell of that name the card is remembered
  (``RulesState.paradigm``); a copy (cast from exile, 707.12) resolving later is not the first time, and it ceases to exist (704.5e).
* The delayed trigger: :func:`main_phase` (engine, the first main phase) puts the trigger of each remembered card of the active player on the stack: copy the card in
  exile (copying.copy_cards, 707.12) and cast the copy for free (permissions: "you may cast the copy without paying its mana cost"); a copy not cast ceases to exist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.state import zone_key

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
INDEX = 5003


def paradigm(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The spell's last instruction: exile it (as it leaves the stack) and, the first time its controller resolves a spell of this name, remember it."""
    r = plan.rules
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is None or not card.card_id or card.is_token or card.copy_of is not None:
        return True  # (a copy of the spell: it ceases to exist, and it is never the first time)
    pid, key = str(ctx["controller"]), f"{ctx['controller']}:{plan.ch(card).name or card.name}"
    if key not in r.paradigm_seen:
        r.paradigm_seen.append(key)
        r.paradigm.append({"player": pid, "card": card.id})
    if plan.oid(card) not in r.exile_if_graveyard:
        r.exile_if_graveyard.append(plan.oid(card))
    return True


def main_phase(plan: Plan) -> None:
    """702.192a: at the beginning of each of the active player's precombat main phases, a trigger for each card of theirs that was exiled by a paradigm."""
    from app.rules import permissions, triggers

    r = plan.rules
    for entry in list(r.paradigm):
        card = plan.state.cards.get(entry["card"])
        if entry["player"] != plan.active:
            continue
        cast = permissions.parse_clause("you may cast the copy without paying its mana cost")
        if card is None or cast is None:
            continue
        effects = [{"do": "copy_cards", "who": "event", "as": "p0"}, *({**e, "who": "ref:p0"} for e in cast[0])]  # ("the copy": what the instruction before made, as scripts binds it)
        if card.zone != zone_key(card.owner, "exile"):  # -- review 43 -- the 2026-03-20 ruling: once it has resolved, the card leaving exile doesn't matter; the copy (in exile) is made by hand
            effects = [{"do": "room_by_hand", "text": f"Create a copy of {plan.ch(card).name or card.name} in exile. You may cast the copy without paying its mana cost."}]
        triggers.paradigm_trigger(plan, card, entry["player"], {"kind": "triggered", "trigger": "main_you", "optional": False, "target": None, "effects": effects})


PRIMITIVES = {"paradigm": paradigm}
