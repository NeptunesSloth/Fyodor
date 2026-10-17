"""-- keywords (wave 50H) -- haunt (CR 702.55), researched against the stored Comprehensive Rules (2026-09-25).

* 702.55a — "Haunt" on a permanent is "When this permanent is put into a graveyard from the battlefield, exile it haunting target creature."
  (``keyword_triggers.MEANINGS``; the effect is :func:`haunt`). Haunt on an instant or sorcery isn't read: the card stays manual.
* 702.55b — the card in exile "haunts" the creature that ability targeted, whether or not it is still a creature: ``RulesState.haunting`` maps the
  haunting card's object in exile to the object it haunts. If the target is illegal as the ability resolves, nothing happens: the card stays put.
* 702.55c — "When the creature it haunts dies" functions in exile (triggers._watchers, subject "haunted"): the haunted object's death is matched by
  its object id, so a card that left exile and came back (a new object, 400.7) haunts nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]


def parse(target: str) -> tuple[list[dict[str, Any]], Any] | None:
    """"target creature" → the effect and its target group, or None (manual)."""
    from app.rules import selectors
    from app.rules.copying import _target_group

    group = _target_group(target)
    if group is None or group["max"] != 1 or "another" in group or not group["what"].startswith(selectors.PREFIX):
        return None
    sel = selectors.from_key(group["what"])
    if sel.player is not None or sel.zones != ("battlefield",) or sel.card or sel.ability is not None or sel.types != ("Creature",):
        return None
    return [{"do": "haunt", "who": "target"}], group


def haunt(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """702.55a-b: exile the source card (the one the ability is of, in its owner's graveyard now) haunting the target."""
    from app.rules import effects

    targets = effects._cards(plan, ctx, str(e.get("who") or "target"))
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if targets and card is not None and card.zone.endswith(":graveyard"):
        effects.exile_cards(plan, ctx, {}, [card.id])
        if plan.state.cards[card.id].zone.endswith(":exile"):
            plan.rules.haunting[plan.oid(card.id)] = plan.oid(targets[0])
            plan.note(f"{card.name} haunts {plan.state.cards[targets[0]].name or 'a creature'}", [card.id, targets[0]])
    return True


def haunted(plan: Plan, watcher_id: str) -> str | None:
    """The object the card in exile haunts (702.55b), or None."""
    return plan.rules.haunting.get(plan.oid(watcher_id))


PRIMITIVES = {"haunt": haunt}
