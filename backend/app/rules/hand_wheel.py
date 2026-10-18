"""-- trigger other (wave 25B) -- "Put the cards in your hand on the bottom of your library in any order, then draw that many cards."
(Arjun, the Shifting Flame; Mindmoil) and "At the beginning of each player's draw step, that player puts the cards in their hand on
the bottom of their library in any order, then draws that many cards." (Teferi's Puzzle Box). Researched against CR 2026-09-25.

* The first instruction moves every card in the player's hand to the bottom of their library; "that many" (608.2c) is how many cards
  that was, counted when the hand is read: it is bound (``context.bind_amount``) for the draw that follows.
* 401.4: cards put on the bottom of a library together are put there in the order their owner chooses ("in any order"): a private
  choice (the order decision goes to that player only, app/rules/effects.py ``_ask_order``); with one card there is nothing to order.
* A hand and a library are both hidden zones: no card is named in the log, and the cards stay anonymous to the other players.
* The draw is an ordinary draw (the draw choke point and its replacements apply, 121.2); with an empty hand it draws nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key
from app.rules import context
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]


def hand_to_bottom(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules.effects import _ask_order, _players

    players = _players(plan, ctx, e["who"])
    pid = players[0] if players else None
    hand = list(plan.state.zones.get(zone_key(pid, "hand"), [])) if pid is not None else []
    if e.get("any_number") and hand and pid is not None:  # -- wheel (wave 51B) -- "Put any number of cards from your hand on the bottom of your library, then draw that many cards plus one." (Valakut Awakening): their choice, private (101.4a)
        decide(plan, player=pid, kind="choose_cards", prompt="Put any number of cards from your hand on the bottom of your library",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in hand],
               min_choices=0, max_choices=len(hand), resume={"step": "hand_pick", "ctx": ctx, "e": e})
        return False
    context.bind_amount(ctx, e["bind_amount"], int(e.get("plus", 0)) if e.get("any_number") else len(hand))  # (nothing in hand to choose: "that many cards plus one" is one)
    if not hand or pid is None:
        return True
    plan.note(f"{plan.name(pid)} puts the {len(hand)} card{'s' if len(hand) != 1 else ''} in their hand on the bottom of their library", actor=pid)
    if len(hand) == 1:
        plan.do({"type": "move", "card_ids": hand, "to": {"player": pid, "zone": "library"}, "position": "bottom"}, actor=pid)
        return True
    _ask_order(plan, ctx, pid, pid, hand, "bottom")  # (resume_order_library goes on with the resolution)
    return False


def resume_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import _ask_order, continue_effects

    ctx, pid = d.resume["ctx"], d.player
    context.bind_amount(ctx, d.resume["e"]["bind_amount"], len(chosen) + int(d.resume["e"].get("plus", 0)))  # ("that many cards plus one": the draw's amount)
    if chosen:
        plan.note(f"{plan.name(pid)} puts {len(chosen)} card{'s' if len(chosen) != 1 else ''} from their hand on the bottom of their library", actor=pid)
    if len(chosen) > 1:  # 401.4: they order them
        _ask_order(plan, ctx, pid, pid, chosen, "bottom")
        return
    if chosen:
        plan.do({"type": "move", "card_ids": chosen, "to": {"player": pid, "zone": "library"}, "position": "bottom"}, actor=pid)
    continue_effects(plan, ctx)


PRIMITIVES = {"hand_to_bottom": hand_to_bottom}
RESUME = {"hand_pick": resume_pick}
