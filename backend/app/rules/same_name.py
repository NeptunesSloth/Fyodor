"""-- tutor (wave 26D) -- "Search your library for a card with the same name as that creature / target creature / another creature you
control / a card in your graveyard" (Remembrance, Verdant Succession, Pack Hunt, Bifurcate, Pattern Matcher, Frostpyre Arcanist).

CR 201.2: two objects have the same name when their names are identical. The name read is the one the object had (608.2h: its last known
information once it left, e.g. the creature that died). "Another creature you control" / "a card in your graveyard" don't pick one
object: a card qualifies if its name is the name of *any* such object. 701.23b: a search for cards with a stated quality may find fewer,
so a name nothing in the library has finds nothing. A token's name counts like any other (201.2); a face-down object has none (708.2a)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.rules import selectors

if TYPE_CHECKING:
    from app.rules.effects import Context
    from app.rules.plan import Plan


def names(plan: Plan, ctx: Context, spec: Any) -> set[str]:
    """The (lower-case) names a searched card may have."""
    from app.rules import card_names, context
    from app.rules.effects import target_refs

    found: list[str] = []
    if spec == "event":
        got = context.info(plan, ctx, context.EVENT)
        found = card_names.reference_names(got[1]) if got is not None else []
    elif spec == "target":
        for t in target_refs(ctx, "target"):
            card = plan.state.cards.get(t["id"])
            if card is not None and plan.oid(card) == t.get("object_id"):
                found.extend(card_names.reference_names(plan.ch(card)))
            elif (snap := plan.rules.lki.get(t.get("object_id") or "")) is not None:
                found.extend(n.strip() for n in snap.name.split(" // ") if n.strip())
    elif isinstance(spec, dict):
        sel = selectors.from_key(spec["sel"])
        found = [n for c in selectors.candidates(plan, sel, ctx["controller"], ctx.get("source_card"))
                 for n in card_names.reference_names(plan.ch(plan.state.cards[c]))]
    return {n.lower() for n in found if n}
