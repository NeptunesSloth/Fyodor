"""-- Learn replacement (wave 110C) -- Retriever Phoenix: "As long as this card is in your graveyard, if you would learn, you may instead return this
card to the battlefield."

701.48a: Learn is "you may discard a card. If you do, draw a card" here (903.11: no sideboard, so no Lesson import). Every Learn goes through the
``learn110c`` instruction, which first offers each graveyard card of its controller with this static (614.1: a replacement effect the controller
chooses, 616.1; the card is in the graveyard it works from, 113.6k); declining (or having none) is the plain Learn. The card is a new object
once it returns (400.7), and it enters under its owner's control, which is the controller of the Learn (the graveyard is theirs)."""

from __future__ import annotations

import re
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.plan import Plan, decide

STATIC = "learn_instead110c"
_TEXT = re.compile(r"^as long as (?:~|this card) is in your graveyard, if you would learn, you may instead return (?:~|this card) to the battlefield$", re.IGNORECASE)
PLAIN = "You may discard a card. If you do, draw a card."


def definition(text: str) -> dict[str, Any] | None:
    return {"kind": "static", "static": STATIC, "effects": []} if _TEXT.fullmatch(text.strip().rstrip(".")) else None


def _pool(plan: Plan, me: str) -> list[str]:
    from app.rules import scripts

    return [c for c in plan.state.zones.get(f"{me}:graveyard", []) if (card := plan.state.cards[c]) is not None and not plan.manual(card)
            and any(d.get("static") == STATIC for d in scripts.definitions(plan.ch(card)).values())]


def _plain(ctx: dict[str, Any]) -> None:
    from app.rules import scripts

    found = scripts.parse_effects(PLAIN)
    assert found is not None
    ctx["effects"][ctx["next"]:ctx["next"]] = found[0]


def learn(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    me = ctx["controller"]
    pool = _pool(plan, me)
    if not pool:
        _plain(ctx)
        return True
    decide(plan, player=me, kind="choose_one", prompt="Learn: return a card to the battlefield instead?",
           options=[*(DecisionOption(id=c, label=f"Return {plan.state.cards[c].name} to the battlefield instead", card_id=c) for c in pool),
                    DecisionOption(id="learn", label="Learn (you may discard a card, then draw a card)")],
           resume={"step": "learn110c", "ctx": ctx}, source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def resume_learn(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    cid = chosen[0]
    if cid == "learn" or cid not in _pool(plan, ctx["controller"]):
        _plain(ctx)
    elif not effects._return_cards(plan, ctx, {"do": "return_card", "to": "battlefield", "tapped": False, "under": "you", "who": "x"}, [cid]):
        return
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"learn110c": learn}
RESUME = {"learn110c": resume_learn}
