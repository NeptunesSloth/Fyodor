"""-- counters (wave 7C) -- shield counters (CR 2026-09-25).

* 122.1c: one or more shield counters on a permanent create a single replacement effect and a single prevention
  effect: "If this permanent would be destroyed as the result of an effect, instead remove a shield counter from it"
  and "If damage would be dealt to this permanent, prevent that damage and remove a shield counter from it."
* Destruction by lethal damage or by deathtouch (704.5g/h) isn't "as the result of an effect" — the damage was
  prevented already. Indestructible permanents aren't destroyed, so they keep the counter.
* All the damage one simultaneous event batch (120.4b) deals to the permanent is prevented and one counter comes off
  (one prevention effect). Damage that can't be prevented (615.12) is dealt and the counter stays. Other prevention
  and replacement effects are applied first (the permanent's controller would choose them to keep the counter);
  the shield then prevents what is left.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan


def _shielded(plan: Plan, card_id: str) -> bool:
    card = plan.state.cards.get(card_id)
    return card is not None and card.zone.endswith(":battlefield") and card.counters.get("shield", 0) > 0 \
        and not plan.manual(card)


def prevent_damage(plan: Plan, result: list[dict[str, Any]]) -> list[str]:
    """The damage events (final, after the other effects) to shielded permanents become prevented; the permanents
    whose shield counter is used (once each: one batch is one event) are returned."""
    used: list[str] = []
    for ev in result:
        if ev["amount"] > 0 and not ev.get("unpreventable") and _shielded(plan, ev["target"]):
            ev["prevented"] = int(ev.get("prevented") or 0) + int(ev["amount"])
            ev["amount"] = 0
            ev["why"] = [*(ev.get("why") or []), "a shield counter"]
            if ev["target"] not in used:
                used.append(ev["target"])
    return used


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
