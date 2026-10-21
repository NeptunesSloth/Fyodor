"""Random modal tokens and exact block-event consequences use native resolution."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_OUTLAWS = "At the beginning of your upkeep, choose one at random. Create a red and white creature token with those characteristics."
_ROWS = [
    "• 3/1 Human Warrior with trample and haste.",
    "• 2/1 Human Cleric with lifelink and haste.",
    '• 1/2 Human Rogue with haste and "When this token enters, it deals 1 damage to any target."',
]
_CREATES = [
    "Create a 3/1 red and white Human Warrior creature token with trample and haste.",
    "Create a 2/1 red and white Human Cleric creature token with lifelink and haste.",
    'Create a 1/2 red and white Human Rogue creature token with haste and "When this token enters, it deals 1 damage to any target."',
]
_YDWEN = "Flip a coin. If you lose the flip, remove ~ from combat and it can't block this turn. Creatures it was blocking that had become blocked by only ~ this combat become unblocked."


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    text = " ".join(body.split())
    text = text[:1].upper() + text[1:]
    if text == _YDWEN:
        return (
            [{"do": "coin_flip", "n": 1}, {"do": "random_characteristic_choice", "kind": "ydwen"}],
            None,
            False,
        )
    return None


def merge_lines(ch: Any, out: dict[int, Any]) -> None:
    from app.rules import modal_abilities

    for offset, ab in enumerate(ch.abilities):
        if ab.text != _OUTLAWS:
            continue
        rows = ch.abilities[offset + 1 : offset + 4]
        if [row.text for row in rows] != _ROWS:
            continue
        header = replace(ab, text="At the beginning of your upkeep, choose one at random —")
        bullets = [replace(row, text="• " + text) for row, text in zip(rows, _CREATES, strict=True)]
        rewritten = replace(
            ch,
            abilities=tuple(
                header if a.index == ab.index else next((b for b in bullets if b.index == a.index), a)
                for a in ch.abilities
            ),
        )
        found = modal_abilities.definitions(header, rewritten)
        if found:
            out.update(found)


def freeze_trigger(plan: Plan, definition: dict[str, Any], source_object: str) -> dict[str, Any]:
    """Freeze block declaration while all original participants still exist (603.2)."""
    if not any(
        e.get("do") == "random_characteristic_choice" and e.get("kind") == "ydwen" and "combat" not in e
        for e in definition.get("effects") or []
    ):
        return definition
    source = next((c for c in plan.state.cards.values() if plan.oid(c) == source_object), None)
    if source is None:
        from app.game.errors import ActionError

        raise ActionError("The original blocking event is unavailable for Ydwen Efreet")
    refs = []
    for cid in [source.blocking, *source.blocking_more]:
        attacker = plan.state.cards.get(cid or "")
        if attacker is None:
            continue
        if any(c.id != source.id and c.blocks(attacker.id) for c in plan.state.cards.values()):
            continue
        refs.append({"card": attacker.id, "object_id": plan.oid(attacker)})
    return {
        **definition,
        "effects": [
            {**e, "combat": plan.rules.combats, "attackers": refs}
            if e.get("do") == "random_characteristic_choice" and e.get("kind") == "ydwen"
            else e
            for e in definition["effects"]
        ],
    }


def consume(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import coin_recipes

    if e["kind"] == "ydwen" and not ctx.get("coin"):
        coin_recipes.insert(
            ctx,
            [
                {"do": "remove_from_combat", "who": "self"},
                {"do": "restrict", "who": "self", "rules": ["cant_block"]},
                {**e, "kind": "ydwen_unblock"},
            ],
        )
    elif e["kind"] == "ydwen_unblock" and plan.rules.combats == e["combat"]:
        for ref in e["attackers"]:
            card = plan.state.cards.get(ref["card"])
            if (
                card is not None
                and plan.oid(card) == ref["object_id"]
                and card.is_attacking
                and not any(c.blocks(card.id) for c in plan.state.cards.values())
            ):
                plan.rules.blocked = [cid for cid in plan.rules.blocked if cid != card.id]
    return True


PRIMITIVES = {"random_characteristic_choice": consume}
