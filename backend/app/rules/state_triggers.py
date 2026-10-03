"""-- state triggers (wave 6D) -- "When you control no Islands, sacrifice this creature." (Dandân, Sea Serpent, Covetous
Dragon, Emperor Crocodile, Porphyry Nodes …), researched against CR 2026-09-25.

603.8: a state trigger triggers as soon as a game state matches its condition (not on an event) and goes on the stack
at the next opportunity. It doesn't trigger again until it has resolved, been countered or otherwise left the stack;
then, if the object is still on the battlefield and the state still matches, it triggers again.

The condition is the ordinary condition grammar (app/rules/conditions.py: "you control no Islands", "there are no
creatures on the battlefield", "you control seven or more Thrulls"), read about the permanent's controller and the
permanent itself ("no other creatures"). It's checked whenever triggers are looked at after the table changed
(triggers.collect). An instance waiting or on the stack is recognised by its first effect, ``state_trigger`` with the
permanent's object id and the ability's index (a new object after a zone change, 400.7, is a different key).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

PATTERN = re.compile(r"^When (?P<cond>you control (?:no|a|an|\w+ or more) [^,]+|there are no [^,]+ on the battlefield|"
                     r"you have \w+ or (?:more|less) life), (?P<body>.+)$")


def condition(text: str) -> dict[str, Any] | None:
    """The state, or None (manual): only one about the controller, the board, or the permanent itself."""
    from app.rules import conditions

    cond = conditions.parse(text)
    if cond is None or set(conditions.objects_in(cond)) - {"self"}:
        return None
    return cond


def _key(oid: str, index: int) -> str:
    return f"{oid}:{index}"


def _waiting(plan: Plan) -> set[str]:
    keys = {str(t.ability["effects"][0].get("key")) for t in plan.rules.pending_triggers
            if t.ability.get("effects") and t.ability["effects"][0].get("do") == "state_trigger"}
    keys |= {str(e.effects[0].get("key")) for e in plan.rules.stack.values()
             if e.effects and e.effects[0].get("do") == "state_trigger"}
    return keys


def check(plan: Plan) -> None:
    """603.8: each state trigger whose state matches and that isn't waiting or on the stack already triggers."""
    from app.rules import conditions, triggers

    watching = triggers._watchers(plan, "state")
    if not watching:
        return
    waiting = _waiting(plan)
    for card, ch, i, d in watching:
        oid = plan.oid(card)
        key = _key(oid, i)
        if key in waiting or card.controller not in plan.live():
            continue
        if not conditions.holds(plan, {"controller": card.controller, "source_card": card.id, "source_object": oid},
                                d["state"]):
            continue
        triggers._add(plan, controller=card.controller, source_card=card.id, source_object=oid, name=ch.name, index=i,
                      definition={**d, "effects": [{"do": "state_trigger", "key": key}, *d["effects"]]})


def state_trigger(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The marker first effect: nothing to do."""
    return True


PRIMITIVES = {"state_trigger": state_trigger}
