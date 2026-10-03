"""-- if you do (wave 10C) -- "Reveal any number of green cards in your hand. Target creature gets +X/+X until end of turn, where X is
the number of cards revealed this way." (Scent of Ivy, Ivy Seer, Scent of Nightshade, Nightshade Seer) and "Reveal any number of
white cards in your hand. You gain 2 life for each card revealed this way." (Scent of Jasmine, Jasmine Seer), read against the stored
Comprehensive Rules (2026-09-25):

* 701.20a: to reveal a card is to show it to every player; the revealed cards stay where they are (701.20c: revealing doesn't move
  a card), so the hand keeps them.
* 608.2d: "any number" is the controller's choice as the spell or ability resolves: none is allowed, and only cards that match
  can be chosen. The choice is private until the cards are shown; the cards shown are then public.
* 608.2c / 608.2h: "the number of cards revealed this way" counts what this instruction revealed, once (the binding is read when
  the later instruction is carried out); with no matching card in hand (or an empty hand) zero cards are revealed.

The grammar is ``scripts``' ("reveal any number of <cards> in your hand"); the count is :mod:`app.rules.this_way` (verb "revealed").
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules import characteristics as chars
from app.rules import context, selectors

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]


def _options(plan: Plan, ctx: Context, e: dict[str, Any]) -> list[str]:
    pid = ctx["controller"]
    sel = selectors.from_key(e["sel"])
    hand = plan.state.zones.get(f"{pid}:hand", [])
    return [c for c in hand if selectors.matches(plan, sel, plan.state.cards[c], chars.of(plan.state.cards[c], plan.info), pid,
                                                 ctx.get("source_card"))]


def reveal_hand_cards(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Ask which of the matching cards in the controller's hand to reveal (any number, including none). The question is asked
    even when nothing matches, so that whether it appears tells the other players nothing about the hand."""
    from app.rules.effects import decide

    options = _options(plan, ctx, e)
    pid = ctx["controller"]
    decide(plan, player=pid, kind="choose_cards", prompt=e.get("prompt") or "Reveal any number of cards from your hand",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in options],
           min_choices=0, max_choices=len(options), resume={"step": "reveal_hand_cards", "ctx": ctx, "e": e})
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    picked = [c for c in chosen if c in set(_options(plan, ctx, e))]  # (only what matched, still in the hand)
    if picked:
        plan.do({"type": "reveal", "card_ids": picked}, actor=ctx["controller"])  # to everyone (701.20a)
    if e.get("as"):
        context.bind_objects(plan, ctx, e["as"], picked)
    continue_effects(plan, ctx)
