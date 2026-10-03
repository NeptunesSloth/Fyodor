"""Exert as it attacks (wave 6E): "You may exert this creature as it attacks. When you do, it gets +2/+2 until end of
turn." (Hooded Brawler, Glorybringer, Ahn-Crop Crasher, Tah-Crop Elite).

701.43d: "You may exert [this creature] as it attacks" is an optional cost to attack (508.1g), linked (607.2h) to the
reflexive "when you do" ability printed with it (603.12). The attacking player chooses which attackers to exert as the
attackers are declared, before any ability triggers on attackers being declared (508.1m); an exerted permanent doesn't
untap during its controller's next untap step (701.43a, the same bookkeeping as an exert cost: ``rules.exerted``).
The "when you do" ability is read like "Whenever ~ attacks, …" and triggers only for an exerted attacker.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules.oracle import AbilityText
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

TRIGGER = "exerted_self"
_EXERT = re.compile(r"^You may exert (?:~|this creature) as it attacks\. When you do, (?P<body>.+)$")


def definition(text: str, ch: Characteristics, index: int) -> dict[str, Any] | None:
    """The linked "when you do" ability of an exert line (``text`` with the card's name as ~), or None."""
    from app.rules import scripts  # (scripts imports this module)

    m = _EXERT.match(text)
    if m is None:
        return None
    probe = AbilityText(index=index, text=f"Whenever ~ attacks, {m['body']}", kind="triggered")
    d = scripts.define(probe, ch)
    if d is None or d.get("kind") != "triggered" or d.get("trigger") != "attacks_self":
        return None
    return {**d, "trigger": TRIGGER}


def _exertable(plan: Plan, card: CardInstance) -> bool:
    from app.rules import triggers

    return not plan.manual(card) and bool(triggers.abilities(plan, plan.ch(card), TRIGGER))


def ask(plan: Plan, attackers: list[CardInstance]) -> bool:
    """508.1g: ask the attacking player which of the attackers that may be exerted they exert (True: asked)."""
    able = [c for c in attackers if _exertable(plan, c)]
    if not able:
        return False
    decide(plan, player=plan.active, kind="choose_cards",
           prompt="Exert any of these creatures as they attack? (701.43d: they won't untap during your next untap step)",
           options=[DecisionOption(id=c.id, label=c.name or "Creature", card_id=c.id) for c in able],
           min_choices=0, max_choices=len(able),
           resume={"step": "exert_attackers", "attackers": [c.id for c in attackers]})
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The exert choice made: the attack triggers (508.1m), then each exerted creature's "when you do" ability."""
    attackers = [plan.state.cards[c] for c in d.resume["attackers"] if c in plan.state.cards]
    exerted = [c for c in attackers if c.id in chosen and c.zone.endswith(":battlefield")]
    for card in exerted:  # 701.43a
        plan.rules.exerted[plan.oid(card)] = card.controller
        plan.note(f"{plan.name(card.controller)} exerted {card.name or 'it'} as it attacked", [card.id])
    finish(plan, attackers, exerted)


def finish(plan: Plan, attackers: list[CardInstance], exerted: list[CardInstance]) -> None:
    from app.rules import triggers

    triggers.attacked(plan, attackers)
    for card in exerted:
        ch = plan.ch(card)
        for i, d in triggers.abilities(plan, ch, TRIGGER):
            triggers._add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name,
                          index=i, definition=d)
    plan.rules.priority = plan.active
    plan.rules.passed = []
