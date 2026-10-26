"""-- Cosima, God of the Voyage // The Omenkeel (wave 110C) --

* Cosima: the upkeep ability exiles Cosima (an optional "may", 603.5) and from then on the exiled object has the granted landfall trigger. The granted trigger
  is a second ability line of the card that works only from exile while the "Voyaging" mark is on that object (611.2a: the grant lasts while it stays exiled;
  400.7: a new object has no mark, nor do the voyage counters stay).
* The landfall trigger: 603.4 intervening "if Cosima is exiled"; the controller may put a voyage counter (122.1); if they don't, Cosima returns to the battlefield
  with X +1/+1 counters (122.6) and its controller draws X cards, X = voyage counters on it as it was in exile (608.2h).
* The Omenkeel: 510.2 damage dealt by a Vehicle; the damaged player exiles that many cards from the top of their library (701.13), face up; 305.1 and 400.7:
  the controller may play lands from among those cards while they remain exiled.
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

UPKEEP = ('At the beginning of your upkeep, you may exile Cosima. If you do, it gains "Whenever a land you control enters, if Cosima is exiled, you may put a voyage '
          'counter on it. If you don\'t, return Cosima to the battlefield with X +1/+1 counters on it and draw X cards, where X is the number of voyage counters on it."')
LINES = ["At the beginning of your upkeep, you may exile Cosima.",
         "Whenever a land you control enters, if Cosima is exiled, you may put a voyage counter on it. If you don't, return Cosima to the battlefield with X +1/+1 "
         "counters on it and draw X cards, where X is the number of voyage counters on it."]
_OMENKEEL = ("Whenever a Vehicle you control deals combat damage to a player, that player exiles that many cards from the top of their library. You may play lands "
             "from among those cards for as long as they remain exiled.")
MARK = "Voyaging"


def _norm(text: str) -> str:
    return text.replace("Cosima", "~").replace("this creature", "~")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    t = _norm(ability.text)
    if t == _norm(LINES[0]):
        native = scripts.define(replace(ability, text="At the beginning of your upkeep, you may gain 1 life."), ch)
        return None if native is None else {**native, "effects": [{"do": "cosima_exile110c"}]}
    if t == _norm(LINES[1]):
        native = scripts.define(replace(ability, text="Whenever a land you control enters, you gain 1 life."), ch)
        if native is None:
            return None
        return {**native, "optional": False, "ex110b": True, "if": {"object": "self", "test": "voyaging110c"}, "effects": [{"do": "cosima_land110c"}]}
    if ability.text == _OMENKEEL:
        native = scripts.define(replace(ability, text="Whenever a Vehicle you control deals combat damage to a player, you gain 1 life."), ch)
        if native is None:
            return None
        return {**native, "effects": [{"do": "exile_top", "n": {"event_amount": 1}, "player": "event_player", "face_down": False, "as": "e0"},
                                      {"do": "grant_play", "who": "ref:e0", "play": True, "cast": False, "until": "permanent", "optional": True}]}
    return None


def split(lines: list[str]) -> None:
    """oracle.parse_abilities: the one printed paragraph is two abilities (the second is the one the first grants)."""
    for i, line in enumerate(lines):
        if _norm(line) == _norm(UPKEEP):
            lines[i:i + 1] = LINES


def cosima_exile(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != ctx.get("source_object"):
        return True  # (400.7: a Cosima that left is not the object that can be exiled)
    owner = card.owner
    plan.do({"type": "move", "card_ids": [card.id], "to": {"zone": "exile"}}, actor=ctx["controller"])
    moved = plan.state.cards[card.id]
    if moved.zone == f"{owner}:exile":
        plan.do({"type": "set_choice", "card_id": card.id, "key": MARK, "value": "1"}, actor=ctx["controller"])
        plan.note(f"{moved.name} is exiled and gains its voyage ability", [card.id])
    return True


def holds(plan: Plan, ctx: dict[str, Any]) -> bool:
    card = plan.state.cards.get(ctx.get("source_card") or "")
    return card is not None and card.zone == f"{card.owner}:exile" and plan.oid(card) == ctx.get("source_object") and MARK in card.choices


def cosima_land(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    if not holds(plan, ctx):
        return True
    decide(plan, player=ctx["controller"], kind="choose_one", prompt="Put a voyage counter on Cosima? (If you don't, it returns and you draw)",
           options=[DecisionOption(id="yes", label="Yes, put a voyage counter"), DecisionOption(id="no", label="No, return Cosima")],
           resume={"step": "cosima_land110c", "ctx": ctx}, source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def resume_cosima_land(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    at = ctx["next"]
    if holds(plan, ctx):  # (it may have left in response? the choice is made as the ability resolves: no window, but stay safe)
        if chosen[0] == "yes":
            ctx["effects"][at:at] = [{"do": "add_counters", "who": "self_exile", "kind": "voyage", "n": 1}]
        else:
            x = plan.state.cards[ctx["source_card"]].counters.get("voyage", 0)
            back: dict[str, Any] = {"do": "return_card", "who": "self_exile", "to": "battlefield", "tapped": False}
            if x:
                back.update(counter="+1/+1", counter_n=x)
            ctx["effects"][at:at] = [back, *([{"do": "draw", "who": "you", "n": x}] if x else [])]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"cosima_exile110c": cosima_exile, "cosima_land110c": cosima_land}
RESUME = {"cosima_land110c": resume_cosima_land}
