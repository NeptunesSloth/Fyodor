"""-- if you do (wave 8C) -- "You may sacrifice a creature. If you do, … that creature's mana value" / "You may exile a
creature card from your graveyard. If you do, create a token that's a copy of that card": the object a payment made as
the ability resolves (118.12) is something the "If you do" clause can refer to.

The payment binds the objects it used (context.bind_payment): where they went (400.7j: the exiled card is a new object
in exile, so a copy of it is made from there) and as they were (608.2h: a sacrificed creature's mana value is its last
known information). The wording is read only when it names that object outright — "the sacrificed creature", "that
creature" after a sacrifice, "the exiled card", "that card" after an exile — and only when no trigger event could be the
thing "that creature" means (a trigger about an object keeps its old reading: ``it`` is then "event"/"event_gone"/…).
Anything else about the paid object stays manual."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any

from app.rules import costs as C
from app.rules import optional_payment

_EVENT_LIKE = ("event", "event_gone", "event_spell", "event_all")
_STAT = r"(?P<stat>power|toughness|mana value)"
_KIND = r"(?:creature|artifact|permanent|land|enchantment)"
PLACEHOLDER = "pay_exiled"  # (a copy source "the exiled card": bound to the payment below; refused if left unbound)


def kind(pay: dict[str, Any]) -> str | None:
    """"sacrificed" / "exiled" / "discarded" when the payment is exactly one chosen permanent sacrificed, card exiled or card discarded."""
    cost = optional_payment.parse(str(pay.get("cost") or "")) if not pay.get("alts") else None
    if cost is None:
        return None
    if len(cost.components) == 2 and cost.components[0].kind == C.MANA and cost.components[1].kind == C.DISCARD:
        cost = replace(cost, components=cost.components[1:])  # -- as long as (wave 9B) -- "pay {1}{R} and discard a card"
    if len(cost.components) != 1:
        return None
    comp = cost.components[0]
    if comp.selector is None or comp.amount != 1 or comp.alt is not None:
        return None
    if comp.kind == C.SACRIFICE:
        return "sacrificed"
    if comp.kind == C.DISCARD:  # -- as long as (wave 9B) -- "you may pay {1}{R} and discard a card. If you do, … the discarded card's mana value"
        return "discarded"
    return "exiled" if comp.kind in (C.EXILE_FROM_GRAVEYARD, "EXILE_FROM_HAND") else None


def rewrite(text: str, pay: dict[str, Any], antecedent: str | None) -> str:
    """The clause with the paid object's statistics worded the way the value grammar reads them
    ("that creature's mana value" → "the sacrificed creature's mana value")."""
    what = kind(pay)
    if what is None:
        return text
    event = antecedent in _EVENT_LIKE
    if what == "sacrificed":
        text = re.sub(rf"\bthe {_STAT} of (?:the sacrificed|that) ({_KIND})\b", r"the sacrificed \2's \1", text)
        if not event:
            text = re.sub(rf"\bthat ({_KIND})'s {_STAT}\b", r"the sacrificed \1's \2", text)
        return text
    if event:
        return text
    text = re.sub(rf"\bthe {_STAT} of (?:the exiled|that) card\b", r"the exiled card's \1", text)
    text = re.sub(rf"\bthat card's {_STAT}\b", r"the exiled card's \1", text)
    return re.sub(r"\bcopy of that card\b", "copy of the exiled card", text)


def bind(inner: tuple[list[dict[str, Any]], Any], pay: dict[str, Any]) -> tuple[list[dict[str, Any]], Any] | None:
    """The clause's effects with the paid object read from the payment's binding; None when the clause still names it
    some way this can't read."""
    what = kind(pay)
    raw = json.dumps(inner, default=str)
    if what is None:
        return None if "cost:exiled" in raw or PLACEHOLDER in raw else inner
    name = f"ref:{pay['bind']}"
    if what == "discarded":  # -- as long as (wave 9B) -- language._stat's "it:discarded": the card the payment discarded
        raw = raw.replace('"it:discarded"', json.dumps(name))
        return (found := json.loads(raw))[0], found[1]
    raw = raw.replace('"cost:sacrificed"' if what == "sacrificed" else '"cost:exiled"', json.dumps(name))
    if what == "exiled":
        raw = raw.replace(json.dumps(PLACEHOLDER), json.dumps(name))
    elif PLACEHOLDER in raw:
        return None
    if '"cost:' in raw and (what == "exiled" or "cost:exiled" in raw):
        return None
    found = json.loads(raw)
    return found[0], found[1]


def leftover(effects: Any) -> bool:
    """A placeholder no payment bound (the wording isn't after a payment): the ability isn't read."""
    raw = json.dumps(effects, default=str)
    return PLACEHOLDER in raw or '"cost:exiled"' in raw
