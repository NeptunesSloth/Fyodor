"""-- optional graveyard replacements (wave 110C) -- 614.1a, 616.1: "you may" put a card on top of its owner's library instead of into the graveyard.
Library of Leng / Nephalia Academy: a discard caused by an effect (701.9; the table sets ``plan.discarding`` around an effect's discard move, so a cost,
the cleanup step and a "put into a graveyard" are no discard effects). Pulmonic Sliver (granted): any permanent going to a graveyard.
A "may" replacement is a Cand with ``may``; declining is one more candidate (outcome "graveyard"), so the 616.1 question carries the choice."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan
    from app.rules.replacements import Cand

LENG = "If an effect causes you to discard a card, discard it, but you may put it on top of your library instead of into your graveyard."
NEPHALIA = ("If a spell or ability an opponent controls causes you to discard a card, you may reveal that card and put it on top of your library "
            "instead of putting it anywhere else.")
SLIVER = "If this permanent would be put into a graveyard, you may put it on top of its owner's library instead."
STATIC = "discard_top_may110c"


def definition(text: str) -> dict[str, Any] | None:
    if text == LENG:
        return {"kind": "static", "static": STATIC, "effects": [], "by": "any"}
    if text == NEPHALIA:
        return {"kind": "static", "static": STATIC, "effects": [], "by": "opponent"}
    if text.replace("~", "this permanent") == SLIVER:
        return {"kind": "replacement", "replacement": "library_may110c", "from": "battlefield", "effects": []}
    return None


def discard_candidates(plan: Plan, card: CardInstance, actor: str | None) -> list[Cand]:
    """The discard replacements of the permanents their owner controls: a token is no card (108.2a), a hand card is its owner's to discard."""
    from app.rules import scripts
    from app.rules.replacements import Cand

    if not getattr(plan, "discarding", False) or card.is_token:
        return []
    return [Cand(s.name or "a static ability", "library:top", may=True) for s in plan.state.cards.values()
            if s.controller == card.owner and s.zone.endswith(":battlefield") and not s.face_down and plan.in_game(s) and not plan.manual(s)
            for d in scripts.definitions(plan.ch(s)).values()
            if d.get("static") == STATIC and (d["by"] == "any" or actor not in (None, card.owner))]


def with_decline(cands: list[Cand]) -> list[Cand]:
    """When every replacement that applies is optional, declining all of them is a result too (the card goes to the graveyard as asked)."""
    from app.rules.replacements import Cand

    if cands and all(c.may or c.outcome == "graveyard" for c in cands) and not any(c.outcome == "graveyard" for c in cands):
        return [*cands, Cand("Decline", "graveyard", may=True)]
    return cands
