"""Wave 110A: Nicol Bolas, Dragon-God +1 - "You draw a card. Each opponent exiles a card from their hand or a permanent they control." (101.4: each opponent
chooses, in turn order, then the exiling happens at once; the chosen hand card stays hidden from the other choosers). The static "has all loyalty abilities of all
other planeswalkers on the battlefield" is app/rules/abilities_of.py (LOYALTY_ALL)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.plan import decide

Context = dict[str, Any]
TEXT = "+1: You draw a card. Each opponent exiles a card from their hand or a permanent they control."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    d = scripts.define(replace(ability, text="+1: You draw a card."), ch)
    return None if d is None or [e["do"] for e in d["effects"]] != ["draw"] else {**d, "effects": [*d["effects"], {"do": "exile_hand_or_permanent110a"}]}


def _next(plan: Any, ctx: Context, turns: list[str], picked: list[str]) -> bool:
    from app.rules import effects

    while turns:
        p, turns = turns[0], turns[1:]
        options = [*plan.state.zones.get(f"{p}:hand", []), *(c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == p and plan.in_game(c))]
        if options:
            decide(plan, player=p, kind="choose_cards", prompt=f"{ctx.get('name') or 'Exile'}: exile a card from your hand or a permanent you control",
                   options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in options], min_choices=1, max_choices=1,
                   resume={"step": "exile_hand_or_permanent110a", "ctx": ctx, "rest": turns, "picked": picked})
            return False
    return effects.exile_cards(plan, ctx, {"do": "exile"}, picked) if picked else True


def exile_each(plan: Any, ctx: Context, e: dict[str, Any]) -> bool:
    return _next(plan, ctx, [p for p in plan.apnap() if p != ctx["controller"] and p in plan.live()], [])


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    r = d.resume
    plan.note(f"{plan.name(d.player)} chooses a card or permanent to exile", actor=d.player)  # (not which: it may be a hand card, 101.4)
    if _next(plan, r["ctx"], r["rest"], [*r["picked"], *chosen]):
        continue_effects(plan, r["ctx"])


PRIMITIVES = {"exile_hand_or_permanent110a": exile_each}
RESUME = {"exile_hand_or_permanent110a": resume}
