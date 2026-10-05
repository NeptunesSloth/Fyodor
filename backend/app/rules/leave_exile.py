"""-- zone replacements (wave 22C) -- "If it would leave the battlefield, exile it instead of putting it anywhere else."

A sentence after an instruction that put a permanent onto the battlefield (Whip of Erebos, Gruesome Encore, Moira and Teshar,
From the Catacombs, Dreams of the Dead, Isareth the Awakener, …): a replacement effect (614.1a) of that object for as long as
it stays on the battlefield (611.2a, 400.7: a new object elsewhere). It is the same record unearth uses (702.84a,
``RulesState.exile_if_leaves``), applied to every move off the battlefield but into exile by ``replacements.zone_candidates``
(616.1: it agrees with the other "exile instead" effects, and differs from a shuffle or a library replacement, which asks).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_SENTENCE = re.compile(r"^if (?P<o>it|that creature|the creature|that permanent|that land|that token) would leave the battlefield, "
                       r"exile it instead(?: of putting it anywhere else)?$")


def sentence(text: str) -> list[dict[str, Any]] | None:
    """The effect of a sentence "If it would leave the battlefield, exile it instead …" (the pronoun is resolved by
    scripts.resolve_it against what the instruction before put onto the battlefield), or None."""
    return [{"do": "exile_if_leaves", "who": "it"}] if _SENTENCE.match(text) else None


def exile_if_leaves(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules.effects import _cards

    for cid in _cards(plan, ctx, e["who"]):
        card = plan.state.cards.get(cid)
        if card is not None and card.zone.endswith(":battlefield"):
            plan.rules.exile_if_leaves.append(plan.oid(card))
    return True


PRIMITIVES = {"exile_if_leaves": exile_if_leaves}
