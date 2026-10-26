"""-- wave 110E -- "Impossible Girl — If Clara Oswald is your commander, choose a color before the game begins. Clara Oswald is the chosen color." (Clara Oswald)

103.6 / 903.3: the choice is made by the commander's owner before the game begins (after the mulligans, before the opening-hand actions), once; it is public. The card
keeps the color wherever it is (an ability that sets its own color works in every zone, 113.6, and a card is the same card in the command zone, on the stack and on the
battlefield): ``RulesState.commander_color110e[card id] = "W" | "U" | "B" | "R" | "G"``, read at the start of the derivation (layers._derive), before every color
effect: this effect has the object's own timestamp, so any later effect that sets or adds colors beats it (613.1e, 613.7).
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

LINE = ("Impossible Girl — If Clara Oswald is your commander, choose a color before the game begins. Clara Oswald is the chosen color.")
COLORS = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}


def definition(text: str) -> dict[str, Any] | None:
    return {"kind": "static", "static": "pregame_color110e", "effects": []} if text.strip() == LINE else None


def pending(plan: Plan, order: list[str]) -> list[str]:
    """The commanders (card ids, in turn order) that still have to choose a color."""
    from app.rules import scripts

    out = []
    for pid in order:
        for card in plan.state.cards.values():
            if card.owner == pid and card.commander_key is not None and card.id not in plan.rules.commander_color110e and any(
                    d.get("static") == "pregame_color110e" for d in scripts.definitions(plan.ch(card)).values()):
                out.append(card.id)
    return out


def ask(plan: Plan, queue: list[str], order: list[str]) -> bool:
    """Ask for the next color; False when none is left to ask."""
    from app.rules.plan import decide

    if not queue:
        return False
    card = plan.state.cards[queue[0]]
    decide(plan, player=card.owner, kind="choose_one", prompt=f"{plan.ch(card).name or card.name}: choose a color before the game begins",
           options=[DecisionOption(id=k, label=v) for k, v in COLORS.items()], source=card,
           resume={"step": "clara110e", "queue": queue, "order": order})
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import opening_hand

    queue = list(d.resume["queue"])
    if chosen and chosen[0] in COLORS and queue[0] in plan.state.cards:
        plan.rules.commander_color110e[queue[0]] = chosen[0]
        plan.note(f"{plan.name(plan.state.cards[queue[0]].owner)} chooses {COLORS[chosen[0]]} for {plan.state.cards[queue[0]].name}", [queue[0]])
    if not ask(plan, queue[1:], d.resume["order"]):
        opening_hand.ask(plan, d.resume["order"])


def apply(plan_state: Any, card: Any, ch: Characteristics) -> Characteristics:
    """layers._derive: the chosen color, while the card still has the ability."""
    rules = plan_state.rules
    color = rules.commander_color110e.get(card.id) if rules is not None else None
    if color is None or not any(a.text == LINE for a in ch.abilities):
        return ch
    return replace(ch, colors=frozenset({color}))
