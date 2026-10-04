"""-- triggers (wave 5D) -- "Draw three cards, then put two cards from your hand on top of your library in any order."
(Brainstorm, Brainsurge, Brainstone, Hidetsugu and Kairi, Riverwise Augur) and "put a card from your hand on top of your
library" (Conch Horn, Survivor of the Unseen). Researched against CR 2026-09-25.

* The player chooses the cards from their own hand (a hidden zone, 400.2): a private choice (the decision's options go
  only to that player, app/rules/view.py), never logged by name.
* 401.4: cards put on top of a library together are ordered by their owner, privately ("in any order").
* With fewer cards in hand than asked, all of them go (an instruction is carried out as far as possible, 609.3).
* The moves go hand → library: both hidden zones, so the cards stay anonymous to the other players
  (app/game/views.py: hidden cards are placeholders, nothing links them to cards seen before).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]


def put_back(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.effects import _amount, _players

    # -- trigger tail (wave 16C) -- "Each player puts a card from their hand on top": each in turn order (101.4), one card each
    order = [p for p in plan.apnap() if p in _players(plan, ctx, e["who"])] if e.get("who") else [ctx["controller"]]
    return _next(plan, ctx, _amount(plan, ctx, e["n"]), order)


def _next(plan: Plan, ctx: Context, want: int, order: list[str]) -> bool:
    for i, pid in enumerate(order):
        hand = list(plan.state.zones.get(zone_key(pid, "hand"), []))
        n = min(want, len(hand))
        if n <= 0:
            continue
        if n == len(hand):
            if not _move(plan, ctx, pid, hand):
                return False  # (several cards: their order is asked first; one card each otherwise)
            continue
        decide(plan, player=pid, kind="choose_cards",
               prompt=f"Choose {n} card{'s' if n != 1 else ''} from your hand to put on top of your library",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand],
               min_choices=n, max_choices=n, resume={"step": "put_back", "ctx": ctx, "want": want, "rest": order[i + 1:]})
        return False
    return True


def _move(plan: Plan, ctx: Context, pid: str, cards: list[str]) -> bool:
    """The chosen cards onto the library: one card at once; several in the order their owner chooses (401.4)."""
    from app.rules.effects import _ask_order

    if not cards:
        return True
    plan.note(f"{plan.name(pid)} puts {len(cards)} card{'s' if len(cards) != 1 else ''} from their hand on top of "
              "their library", actor=pid)
    if len(cards) == 1:
        plan.do({"type": "move", "card_ids": cards, "to": {"player": pid, "zone": "library"}, "position": "top"}, actor=pid)
        return True
    _ask_order(plan, ctx, pid, pid, cards, "top")  # (resume_order_library goes on with the resolution)
    return False


def resume_put_back(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    pid = d.player
    cards = [c for c in chosen if c in plan.state.cards and plan.state.cards[c].zone == zone_key(pid, "hand")]
    if _move(plan, ctx, pid, cards) and _next(plan, ctx, d.resume.get("want", 0), d.resume.get("rest") or []):
        continue_effects(plan, ctx)


PRIMITIVES = {"put_back": put_back}
RESUME = {"put_back": resume_put_back}
