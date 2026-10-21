"""-- counters (wave 7C) -- shield counters (CR 2026-09-25).

* 122.1c: one or more shield counters on a permanent create a single replacement effect and a single prevention
  effect: "If this permanent would be destroyed as the result of an effect, instead remove a shield counter from it"
  and "If damage would be dealt to this permanent, prevent that damage and remove a shield counter from it."
* Destruction by lethal damage or by deathtouch (704.5g/h) isn't "as the result of an effect" — the damage was
  prevented already. Indestructible permanents aren't destroyed, so they keep the counter.
* One native prevention candidate protects the permanent during a simultaneous damage batch.
  Its controller chooses its order with other replacement/prevention effects (616.1).
  Unpreventable damage is dealt, but the additional counter removal still happens (615.12).
  Counter removal commits once per batch immediately after the original damage, before SBAs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def _shielded(plan: Plan, card_id: str) -> bool:
    card = plan.state.cards.get(card_id)
    return card is not None and card.zone.endswith(":battlefield") and card.counters.get("shield", 0) > 0 \
        and not plan.manual(card)


def damage_candidates(plan: Plan) -> list[Any]:
    from app.rules.replace import Candidate

    return [Candidate(id=f"shieldcounter:{plan.oid(card)}", event="damage",
                      match={"to": {"objects": {"oids": [plan.oid(card)]}}},
                      op={"do": "prevent_all", "prevention": True, "consume_unpreventable": True,
                          "shield_counter": card.id}, controller=card.controller,
                      source_card=card.id, source_oid=plan.oid(card), seq=(0, 5, i),
                      label=f"{plan.ch(card).name}: shield counter")
            for i, card in enumerate(plan.state.cards.values()) if _shielded(plan, card.id)]


def remove(plan: Plan, card_ids: list[str], actor: str | None) -> None:
    for cid in card_ids:
        if cid in plan.state.cards and plan.state.cards[cid].counters.get("shield", 0) > 0:
            plan.do({"type": "counter", "card_ids": [cid], "kind": "shield", "delta": -1}, actor=actor)
            plan.note(f"{plan.state.cards[cid].name}: a shield counter is removed", [cid], actor=actor)


def destroy_survivors(plan: Plan, card_ids: list[str], actor: str | None) -> list[str]:
    """Destroyed "as the result of an effect": a permanent with a shield counter loses one instead."""
    kept = [c for c in card_ids if _shielded(plan, c)]
    remove(plan, kept, actor)
    return [c for c in card_ids if c not in kept]
