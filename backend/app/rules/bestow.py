"""-- keywords (wave 15E) -- bestow (CR 702.103), researched against the stored Comprehensive Rules (2026-09-25).

* 702.103a — "As you cast this spell, you may choose to cast it bestowed. If you do, you pay [cost] rather than its mana cost": an
  alternative cost (118.9; app/rules/alt_costs.py, tag "bestow").
* 702.103b — as the spell is put onto the stack it becomes an Aura enchantment and gains enchant creature; it is a bestowed Aura
  spell and the permanent it becomes as it resolves a bestowed Aura. Those effects last until it ceases to be bestowed. Here the
  object's rules id is in ``RulesState.bestowed`` and :func:`overlay` is what ``layers`` applies to it (stack and battlefield alike);
  702.103d: only the characteristics so modified are evaluated to cast it (its target is a creature chosen as for any Aura spell).
* 702.103e — as it begins resolving, if its target is illegal it ceases to be bestowed and resolves as a creature spell (engine).
* 702.103f — if a bestowed Aura becomes unattached, or is attached to an illegal object, it becomes unattached and ceases to be
  bestowed: an exception to 704.5m, so it stays on the battlefield as a creature (sba.py). 702.103g (phasing in unattached) isn't
  modelled: phasing here keeps attachments.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from app.rules.oracle import AbilityText

if TYPE_CHECKING:
    from app.game.rules_state import RulesState
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import Characteristics


def overlay(ch: Characteristics) -> Characteristics:
    """The characteristics of a bestowed Aura (702.103b): an Aura enchantment, no longer a creature, with enchant creature."""
    if "Aura" in ch.subtypes and not ch.is_creature:
        return ch
    index = max((a.index for a in ch.abilities), default=-1) + 1
    enchant = AbilityText(index=index, text="Enchant creature", kind="keywords", keywords=("enchant",))
    return replace(ch, types=(ch.types - {"Creature"}) | {"Enchantment"}, subtypes=frozenset({"Aura"}),
                   abilities=(*ch.abilities, enchant))


def is_bestowed(state: GameState, card: CardInstance) -> bool:
    r: RulesState | None = state.rules
    return r is not None and bool(r.bestowed) and r.object_id(card.id) in r.bestowed


def cease(plan, card: CardInstance, why: str) -> None:  # type: ignore[no-untyped-def]
    """The object stops being a bestowed Aura (702.103e-g): it is a creature again."""
    oid = plan.oid(card)
    plan.rules.bestowed = [o for o in plan.rules.bestowed if o != oid]
    plan.note(f"{card.name} ceases to be bestowed ({why}) and is a creature again", [card.id])
