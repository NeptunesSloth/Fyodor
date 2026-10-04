"""-- casting extras (wave 18E) -- miracle (CR 702.94), researched against the stored Comprehensive Rules (2026-09-25).

* 702.94a — "You may reveal this card from your hand as you draw it if it's the first card you've drawn this turn. When you reveal this
  card this way, you may cast it by paying [cost] rather than its mana cost." A static ability linked to a reflexive trigger (603.11).
* 702.94b — the card is revealed (701.20a) until it leaves the hand, the trigger resolves, or it leaves the stack.

Privacy (the point of this design): whether the card just drawn has miracle is hidden information, and a question put only when it does
would show the table that it does ("p1 is making a choice"). So no question is asked. A drawn first card with miracle opens a *window*
(``RulesState.miracle``, never sent to anyone but its owner: ``view.hints``) in which the owner may take the ``miracle_reveal`` action;
nothing at the table changes for anyone else whether or not a window is open. The window closes at the owner's next game action, when the
stack resolves or the step changes (``clear``), or when the card leaves the hand. The reveal is an action taken as the card is drawn,
so the owner needs the chance to act: a stop in their draw step (the existing stops preference) or any priority after an instant-speed draw.

The reflexive trigger is the one madness uses (the free-cast machinery, ``RulesState.free_casts`` / ``alt_costs``): once it resolves, a
choice to cast the card (public now) for the miracle cost, from the hand, at any time (it ignores timing: it is cast as the trigger resolves).
A miracle cost with {X} (Entreat the Angels, Bonfire of the Damned) isn't read: the X would have to be announced as the free cast begins.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.errors import ActionError
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.game import actions as A
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

_LINE = re.compile(r"^miracle (?P<cost>(?:\{[^}X]+\})+)$", re.IGNORECASE)


def cost_of(ch: Characteristics) -> str | None:
    """The mana cost of the card's one "Miracle {cost}" line (no X), or None."""
    lines = [a for a in ch.abilities if a.kind == "keywords" and "miracle" in a.keywords]
    m = _LINE.fullmatch(re.sub(r"\s*\(.*?\)", "", lines[0].text).strip().rstrip(".")) if len(lines) == 1 else None
    return m["cost"] if m else None


def on_draw(plan: Plan, player: str, drawn: list[str]) -> None:
    """The cards ``player`` just drew, in order (replace.do_draws): the first card of the turn with miracle opens its window."""
    r = plan.rules
    first = r.miracle_turn.get(player) != plan.state.turn.number
    r.miracle_turn[player] = plan.state.turn.number
    card = plan.state.cards.get(drawn[0]) if first and drawn else None
    if card is not None and card.zone == zone_key(player, "hand") and not plan.manual(card) and cost_of(plan.ch(card)) is not None:
        r.miracle.append(card.id)


def clear(plan: Plan) -> None:
    """The moment to reveal has passed (the next action, the stack resolving, the step changing)."""
    plan.rules.miracle = []


def reveal(plan: Plan, a: A.MiracleReveal) -> None:
    """702.94a: reveal the card (public), and the reflexive trigger that offers the cast goes on the stack."""
    from app.rules.engine import require_no_decision
    from app.rules.triggers import _add

    require_no_decision(plan)
    r = plan.rules
    card = plan.state.cards.get(a.card_id)
    cost = cost_of(plan.ch(card)) if card is not None and a.card_id in r.miracle else None
    if card is None or card.owner != plan.actor or card.zone != zone_key(plan.actor, "hand") or cost is None:
        raise ActionError("You can't reveal that card for miracle now")
    r.miracle = []
    plan.do({"type": "reveal", "card_ids": [card.id]}, actor=plan.actor)
    plan.note(f"{plan.name(plan.actor)} reveals {card.name} (miracle)", [card.id])
    r.free_casts.append(card.id)
    r.alt_costs[card.id] = cost
    r.miracled.append(card.id)
    _add(plan, controller=plan.actor, source_card=card.id, source_object=plan.oid(card), name=card.name, index=8001,
         definition={"kind": "triggered", "trigger": "miracle", "optional": False, "target": None,
                     "effects": [{"do": "miracle_offer", "card": card.id, "cost": cost}]})


def offer(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """702.94a: "When you reveal this card this way, you may cast it by paying [cost] rather than its mana cost." """
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    cid = e["card"]
    card = plan.state.cards.get(cid)
    if card is None or card.zone != zone_key(card.owner, "hand") or cid not in plan.rules.free_casts:
        done(plan, cid)
        return True
    decide(plan, player=card.owner, kind="choose_one", prompt=f"Miracle: cast {card.name} for {e['cost']}?",
           options=[DecisionOption(id="yes", label=f"Cast it for {e['cost']}"), DecisionOption(id="no", label="Keep it in your hand")],
           resume={"step": "suspend_cast", "ctx": ctx, "card": cid, "decline": "miracle"}, source=card)
    return False


def done(plan: Plan, cid: str) -> None:
    """The trigger is over (resolved, declined, or the card left the hand): no longer a miracle cast, no longer revealed (702.94b)."""
    r = plan.rules
    r.free_casts = [c for c in r.free_casts if c != cid]
    r.miracled = [c for c in r.miracled if c != cid]
    r.alt_costs.pop(cid, None)
    card = plan.state.cards.get(cid)
    if card is not None and card.zone.endswith(":hand"):
        plan.do({"type": "hide", "card_ids": [cid]}, actor=card.owner)
