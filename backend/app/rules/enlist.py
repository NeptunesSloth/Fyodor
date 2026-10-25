"""-- casting extras (wave 18E) -- enlist (CR 702.154), researched against the stored Comprehensive Rules (2026-09-25).

* 702.154a-b — "As this creature attacks, you may tap up to one untapped creature you control that you didn't choose to attack with and
  that either has haste or has been under your control continuously since this turn began. When you do, this creature gets +X/+0 until end
  of turn, where X is the tapped creature's power." The static half is an optional cost to attack (508.1g), chosen as attackers are
  declared (like exert, ``exert.ask``); the triggered half is reflexive (603.12), linked to it (607.2h).
* 702.154c — a creature can't enlist itself (it is an attacker); 702.154d — each instance is its own optional cost and triggers once,
  only for what it tapped: one question for each instance, and a creature already tapped for one instance isn't offered for the next.

Privacy: every fact is public (the battlefield), so the question is asked whenever the player has something to offer and nothing else
is revealed by it. The power the trigger reads is the tapped creature's (``{"power": "event"}``: the event object, last known
information if it left), as the trigger resolves.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption, ObjectRef, TriggerEvent
from app.game.state import zone_key

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

TRIGGER = {"kind": "triggered", "trigger": "enlist", "optional": False, "target": None,
           "effects": [{"do": "pump", "who": "self", "p": {"power": "event"}, "t": 0}]}


def instances(plan: Plan, card: CardInstance) -> int:
    """How many instances of enlist the attacker has (each keyword line; one per instance, 702.154d)."""
    if plan.manual(card):
        return 0
    return sum(1 for ab in plan.ch(card).abilities if ab.kind == "keywords" and "enlist" in ab.keywords
               for p in re.split(r"[,;]\s*", re.sub(r"\s*\(.*?\)", "", ab.text).strip().rstrip(".")) if p.strip().lower() == "enlist")


def supported(line: str) -> bool:
    pieces = [p.strip().lower() for p in re.split(r"[,;]\s*", re.sub(r"\s*\(.*?\)", "", line).strip().rstrip("."))]
    return bool(pieces) and all(p == "enlist" or not p.startswith("enlist") for p in pieces) and "enlist" in pieces


def _options(plan: Plan, attacker: CardInstance, attackers: set[str], taken: set[str]) -> list[str]:
    """702.154a: untapped creatures its controller controls that didn't attack and aren't summoning sick (haste, or controlled since the
    turn began); never the attacker itself, nor one already tapped for another instance."""
    from app.rules.casting import summoning_sick

    out = []
    for cid in plan.state.zones.get(zone_key(attacker.controller, "battlefield"), []):
        c = plan.state.cards[cid]
        ch = plan.ch(c)
        if cid not in attackers and cid not in taken and cid != attacker.id and c.controller == attacker.controller and not c.tapped \
                and ch.is_creature and plan.in_game(c) and ("haste" in ch.keywords or not summoning_sick(plan.state, c)):
            out.append(cid)
    return out


def ask(plan: Plan, attackers: list[CardInstance], exerted: list[CardInstance], asked: list[list[Any]] | None = None,
        pairs: list[list[str]] | None = None) -> bool:
    """508.1g: ask the attacking player, instance by instance, which creature each enlist taps (True: a question is pending)."""
    asked, pairs = asked or [], pairs or []
    ids = {c.id for c in attackers}
    taken = {t for _, t in pairs}
    for c in attackers:
        for k in range(instances(plan, c)):
            if [c.id, k] in asked or c.id not in plan.state.cards or not plan.state.cards[c.id].zone.endswith(":battlefield"):
                continue
            options = _options(plan, c, ids, taken)
            if not options:
                continue
            from app.rules.plan import decide

            decide(plan, player=plan.active, kind="choose_cards",
                   prompt=f"Enlist for {c.name or 'this creature'}: tap up to one creature you didn't attack with? (it gets +X/+0, X its power)",
                   options=[DecisionOption(id=o, label=plan.state.cards[o].name or "Creature", card_id=o) for o in options],
                   min_choices=0, max_choices=1,
                   resume={"step": "enlist", "attackers": [a.id for a in attackers], "exerted": [e.id for e in exerted],
                           "asked": [*asked, [c.id, k]], "pairs": pairs, "current": c.id})
            return True
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    """The enlist choice made (none is a choice): tap it now (the cost), then the next question, then the attack triggers."""
    r = d.resume
    pairs = [list(p) for p in r["pairs"]]
    if chosen and chosen[0] in plan.state.cards and not plan.state.cards[chosen[0]].tapped:
        plan.do({"type": "tap", "card_ids": [chosen[0]], "tapped": True})
        pairs.append([r["current"], chosen[0]])
        plan.note(f"{plan.name(plan.active)} enlisted {plan.state.cards[chosen[0]].name or 'a creature'} for "
                  f"{plan.state.cards[r['current']].name or 'an attacker'}", [chosen[0], r["current"]])
    attackers = [plan.state.cards[c] for c in r["attackers"] if c in plan.state.cards]
    exerted = [plan.state.cards[c] for c in r["exerted"] if c in plan.state.cards]
    if ask(plan, attackers, exerted, r["asked"], pairs):
        return
    finish(plan, attackers, exerted, pairs)


def finish(plan: Plan, attackers: list[CardInstance], exerted: list[CardInstance], pairs: list[list[str]]) -> None:
    from app.game.rules_state import turn_log_now
    from app.rules import exert, triggers

    log = turn_log_now(plan.state)  # -- trailing & intervening ifs (wave 38A) -- "if it enlisted a creature this combat" (Aradesh): known before the attack triggers
    for attacker_id, _ in pairs:
        if log is not None and attacker_id in plan.state.cards:
            log.enlisted[plan.oid(plan.state.cards[attacker_id])] = plan.rules.combats
    facts = [("enlisted110b", a, plan.ch(a), a.controller, {"oid": plan.oid(a), "actor": a.controller, "amount": 1})  # -- (wave 110B) -- 702.154a: "Whenever ~ enlists a creature"
             for attacker_id, _ in pairs if (a := plan.state.cards.get(attacker_id)) is not None]
    if facts:
        triggers._fire_generic(plan, facts, -1, {})
    exert.finish(plan, attackers, exerted)  # the attack triggers (508.1m) and the exerted creatures' "when you do"
    for attacker_id, tapped_id in pairs:  # 702.154a: "When you do": reflexive, for the creature that enlisted
        a, t = plan.state.cards.get(attacker_id), plan.state.cards.get(tapped_id)
        if a is None or t is None or not a.zone.endswith(":battlefield"):
            continue
        event = TriggerEvent(kind="enlist", count=1, objects=[ObjectRef(card=t.id, object_id=plan.oid(t), zone=t.zone)])
        triggers._add(plan, controller=a.controller, source_card=a.id, source_object=plan.oid(a), name=a.name or "", index=7000,
                      definition=TRIGGER, event=event)
