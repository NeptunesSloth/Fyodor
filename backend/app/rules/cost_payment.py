"""Paying the parts of an activation cost that aren't mana (app/rules/costs.py components).

CR 602.2b applies 601.2b-i to activated abilities: the total cost is locked in, then paid all at
once (601.2h: "Partial payments are not allowed. Unpayable costs can't be paid."). 118.3: a player
can't pay a cost without the resources to pay it fully — an untapped permanent to untap, a
creature to sacrifice, a card to discard. So:

* :func:`problem` says why a cost can't be paid right now (activation hints and refusals);
* :func:`choose` validates the objects the player chose for each part (``cost_choices`` on the
  intent) or opens a private ``choose_cards`` decision for the next part that needs a choice.
  Nothing has moved yet; choosing no cards cancels (the table is left exactly as it was);
* :func:`pay` carries out every non-mana part once the mana payment has been found.

Hidden information: the options of a discard choice are cards in the payer's hand, so the
decision (like every decision's options) goes only to the payer; the discarded card is public
once it's in the graveyard (701.9a).
"""

from __future__ import annotations

import secrets
from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption, PaymentRecord
from app.game.state import CardInstance, zone_key
from app.rules import costs as C
from app.rules import selectors
from app.rules.costs import AbilityCost, CostComponent
from app.rules.plan import Plan, decide

_VERBS = {C.SACRIFICE: "sacrifice", C.DISCARD: "discard", C.EXILE_FROM_GRAVEYARD: "exile",
          C.RETURN_PERMANENT: "return to its owner's hand", C.TAP_OTHER: "tap", C.REMOVE_COUNTER: "remove counters from"}


def _reserved(cost: AbilityCost, comp: CostComponent, source: CardInstance) -> set[str]:
    """Objects a part can't use because another part of the same cost already does: the source
    when it's tapped ({T}) or leaves (sacrificed / exiled / returned) as part of the cost."""
    leaves = cost.sacrifice_self or any(c.selector is None and c.kind in (C.EXILE, C.RETURN_PERMANENT, C.EXILE_FROM_GRAVEYARD)
                                        for c in cost.components)
    if leaves or (comp.kind == C.TAP_OTHER and cost.tap) or (comp.kind == C.TAP_OTHER and cost.untap):
        return {source.id}
    return set()


def candidates(plan: Plan, comp: CostComponent, player: str, source: CardInstance) -> list[str]:
    """Objects that could pay ``comp`` (one part of a cost), in a stable order."""
    assert comp.selector is not None
    sel = selectors.from_key(comp.selector)
    if comp.kind == C.DISCARD:
        zone = zone_key(player, "hand")
    elif comp.kind == C.EXILE_FROM_GRAVEYARD:
        zone = zone_key(player, "graveyard")
    else:
        zone = zone_key(player, "battlefield")
    out = []
    for cid in plan.state.zones.get(zone, []):
        card = plan.state.cards.get(cid)
        if card is None or (zone.endswith(":battlefield") and (card.controller != player or not plan.in_game(card))):
            continue
        if cid == source.id and not zone.endswith(":battlefield"):
            continue  # -- costs (wave 3$) -- a spell's additional cost can't discard / exile the spell being cast (601.2a)
        if not selectors.matches(plan, sel, card, plan.ch(card), player, source.id):
            continue
        if comp.kind == C.REMOVE_COUNTER and card.counters.get(comp.counter or "", 0) < comp.amount:
            continue
        out.append(cid)
    return out


def problem(plan: Plan, cost: AbilityCost, card: CardInstance, player: str) -> str | None:
    """Why the non-mana parts of ``cost`` can't be paid now (118.3), or None."""
    from app.rules.casting import summoning_sick  # casting imports this module

    name = card.name or "It"
    for comp in cost.components:
        if comp.kind == C.UNTAP:  # 107.6: an untapped permanent can't be untapped to pay; 302.6 / 602.5a
            if not card.tapped:
                return f"{name} isn't tapped"
            ch = plan.ch(card)
            if ch.is_creature and "haste" not in ch.keywords and summoning_sick(plan.state, card):
                return f"{name} has summoning sickness"
        elif comp.kind == C.PAY_ENERGY and plan.state.players[player].resources.get("energy", 0) < comp.amount:
            return f"You don't have {comp.amount} energy to pay"
        elif comp.selector is not None:
            usable = [c for c in candidates(plan, comp, player, card) if c not in _reserved(cost, comp, card)]
            if len(usable) < comp.amount:
                return f"You can't pay “{comp.text}”"
    return None


def choose(plan: Plan, a: A.ActivateAbility | A.CastSpell, cost: AbilityCost, card: CardInstance, what: str) -> dict[int, list[str]] | None:
    """The validated objects for every part of ``cost`` that needs a choice, by component index;
    None while waiting for the payer's (private) choice. Each object pays for one part only."""
    given: dict[int, list[str]] = {}
    for c in a.cost_choices:
        if c.component in given:
            raise ActionError("Choose the objects for each part of the cost once")
        given[c.component] = list(c.cards)
    parts = dict(cost.choices)
    if set(given) - set(parts):
        raise ActionError("That ability's cost has no such part to choose for")
    out: dict[int, list[str]] = {}
    used: set[str] = set()
    for i, comp in cost.choices:
        usable = [c for c in candidates(plan, comp, plan.actor, card) if c not in _reserved(cost, comp, card) and c not in used]
        if i in given:
            chosen = given[i]
            if len(chosen) != comp.amount or len(set(chosen)) != len(chosen) or any(c not in usable for c in chosen):
                raise ActionError(f"Choose {comp.amount} to pay “{comp.text}”" + (" (each object pays one part of the cost)"
                                                                                  if any(c in used for c in chosen) else ""))
        elif len(usable) < comp.amount:
            raise ActionError(f"You can't pay “{comp.text}”")  # 118.3
        elif len(usable) == comp.amount:
            chosen = usable  # (no choice to make)
        else:
            verb = _VERBS.get(comp.kind, "use")
            decide(plan, player=plan.actor, kind="choose_cards",
                   prompt=f"{what}: choose {comp.amount} to {verb} (“{comp.text}”), or none to cancel",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in usable],
                   min_choices=0, max_choices=comp.amount,
                   resume={"step": "ability_cost", "component": i, "amount": comp.amount,
                           "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})},
                   source=card)
            return None
        out[i] = list(chosen)
        used |= set(chosen)
    return out


def resume_choice(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The payer chose the objects for one part (or none: cancel — nothing was paid)."""
    from app.rules.engine import INTENTS  # the engine imports this module

    assert d.resume is not None
    plan.rules.priority = d.player
    if not chosen:
        plan.note(f"{plan.name(d.player)} cancelled")
        plan.hold = d.player
        return
    if len(chosen) != d.resume["amount"]:
        raise ActionError(f"Choose {d.resume['amount']}")
    intent = A.parse_action(d.resume["intent"])
    assert isinstance(intent, A.ActivateAbility | A.CastSpell)
    intent.cost_choices = [*intent.cost_choices, A.CostChoice(component=d.resume["component"], cards=chosen)]
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def excluded(cost: AbilityCost, card: CardInstance, chosen: dict[int, list[str]]) -> tuple[str, ...]:
    """Permanents that can't also pay mana: the source when it taps, untaps or leaves as part of
    the cost, and every object chosen for another part (it's sacrificed, tapped, returned …)."""
    out = [c for ids in chosen.values() for c in ids]
    if cost.tap or cost.untap or _reserved(cost, CostComponent(C.OTHER), card):
        out.append(card.id)
    return tuple(dict.fromkeys(out))


def pay(plan: Plan, cost: AbilityCost, card: CardInstance, chosen: dict[int, list[str]], record: PaymentRecord) -> None:
    """Carry out the non-mana parts other than {T}, loyalty, life and the source's own counters
    (the caller pays those as before), recording what was used (the payment record)."""
    player = plan.actor
    sacrifice: list[str] = [card.id] if cost.sacrifice_self else []
    for i, comp in enumerate(cost.components):
        ids = chosen.get(i, [])
        if comp.kind == C.UNTAP:
            plan.do({"type": "tap", "card_ids": [card.id], "tapped": False})
        elif comp.kind == C.PAY_ENERGY:
            plan.do({"type": "resource", "player": player, "key": "energy", "delta": -comp.amount})
        elif comp.kind == C.TAP_OTHER:
            plan.do({"type": "tap", "card_ids": ids, "tapped": True})
            record.tapped_for_cost += ids
        elif comp.kind == C.REMOVE_COUNTER and comp.selector is not None:
            plan.do({"type": "counter", "card_ids": ids, "kind": comp.counter, "delta": -comp.amount})
        elif comp.kind == C.SACRIFICE and comp.selector is not None:
            sacrifice += ids
        elif comp.kind == C.DISCARD:
            if comp.random:  # (the choice is recorded as the move, so replays repeat it)
                pool = [c for c in candidates(plan, comp, player, card)]
                if len(pool) < comp.amount:
                    raise ActionError(f"You can't pay “{comp.text}”")
                ids = secrets.SystemRandom().sample(pool, comp.amount)
            plan.do({"type": "move", "card_ids": ids, "to": {"zone": "graveyard"}})  # 701.9a
            record.discarded += ids
        elif comp.kind in (C.EXILE, C.EXILE_FROM_GRAVEYARD):
            ids = ids if comp.selector is not None else [card.id]
            plan.do({"type": "move", "card_ids": ids, "to": {"zone": "exile"}})
            record.exiled += ids
        elif comp.kind == C.RETURN_PERMANENT:
            ids = ids if comp.selector is not None else [card.id]
            plan.do({"type": "move", "card_ids": ids, "to": {"zone": "hand"}})
            record.returned += ids
    if sacrifice:  # 701.21a: to their owners' graveyards, all at once
        from app.rules.triggers import sacrificing  # (the event "whenever you sacrifice …" triggers on)

        sacrificing(plan, sacrifice)
        record.sacrificed_objects += [plan.oid(c) for c in sacrifice]  # (wave 3D: "the sacrificed creature's power", 608.2h)
        plan.do({"type": "move", "card_ids": sacrifice, "to": {"zone": "graveyard"}})
        record.sacrificed += sacrifice
