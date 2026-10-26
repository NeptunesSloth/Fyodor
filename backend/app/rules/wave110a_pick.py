"""-- chosen objects (wave 110A) -- "As ~ enters, choose another creature you control." (Dauntless Bodyguard, Tyrannical Pitlord).

614.12a / 614.1c: the choice is made as the permanent enters, by its controller, and is public. The chosen object is remembered by its
object id (``RulesState.chosen_objects``: source card id -> chosen object id), so "the chosen creature" is only that same object: if it
left the battlefield and came back it is a new object (400.7) and no longer the chosen one. The memory is kept by card id after the source
leaves, so a leaves-the-battlefield ability or a sacrifice cost still finds it (608.2h); the source entering again chooses anew.
Read by the selector word "chosen" (selectors: extra ``picked110a``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

WHAT = "pick110a"
TEXTS = {"As ~ enters, choose another creature you control.": "other creature you control"}
LABEL = "Chosen creature"


def definition(text: str) -> dict[str, Any] | None:
    if (phrase := TEXTS.get(text)) is None:
        return None
    from app.rules import selectors

    sel = selectors.parse(phrase)
    assert sel is not None, phrase
    return {"kind": "replacement", "replacement": "enters_choice",
            "effects": [{"do": "choose_value", "who": "you", "what": WHAT, "pick110a": sel.key()}]}


def prompt(plan: Plan, card: CardInstance, controller: str, choice: dict[str, Any]) -> tuple[str, list[DecisionOption]]:
    from app.rules import selectors

    ids = selectors.candidates(plan, selectors.from_key(choice["pick110a"]), controller, card.id)
    if choice["what"] == "exile110o":  # -- (wave 110O) -- Living Lore
        return (f"{plan.ch(card).name or card.name}: as it enters, exile an instant or sorcery card from your graveyard",
                [DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in ids])
    return (f"{plan.ch(card).name or card.name}: as it enters, choose another creature you control",
            [DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in ids])


def record(plan: Plan, card_id: str, choices: dict[str, str] | None) -> None:
    """after_entry: remember the object chosen as it entered (none left to choose: nothing is chosen)."""
    if choices is None or WHAT not in choices:
        return
    value, rules = choices[WHAT], plan.rules
    if value in plan.state.cards:
        rules.chosen_objects[card_id] = plan.oid(plan.state.cards[value])
        plan.do({"type": "set_choice", "card_id": card_id, "key": LABEL, "value": plan.state.cards[value].name}, actor=plan.state.cards[card_id].controller)
    else:
        rules.chosen_objects.pop(card_id, None)


def is_picked(plan: Plan, card: CardInstance, source: str | None) -> bool:
    """Is ``card`` the permanent the source chose as it entered?"""
    return source is not None and card.zone.endswith(":battlefield") and plan.rules.chosen_objects.get(source) == plan.oid(card)
