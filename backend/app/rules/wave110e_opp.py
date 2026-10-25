"""Entering choice made by an opponent (wave 110E): "As ~ enters, an opponent chooses a creature type." (Callous Oppressor).

614.12a: the choice is made as the permanent enters. The text says "an opponent", so the controller picks which one
(only asked with 2+ opponents, 800.4: dead players are gone); that opponent then answers."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import Plan

WHO = "chooser110e"


def decider(plan: Plan, controller: str, answers: dict[str, str], out: dict[str, Any]) -> str | None:
    """The opponent who answers, or None while the controller still has to pick one (``out["choice"]`` is then that question)."""
    opponents = [p for p in plan.live() if p != controller]
    if len(opponents) == 1:
        return opponents[0]
    if answers.get(WHO) in opponents:
        return answers[WHO]
    out.setdefault("choice", {"what": WHO})
    return None


def prompt(plan: Plan, card: Any, controller: str) -> tuple[str, list[DecisionOption]]:
    from app.game.rules_state import DecisionOption

    return f"{card.name}: as it enters, choose the opponent who chooses", [DecisionOption(id=p, label=plan.name(p)) for p in plan.live() if p != controller]


# -- cast-time choice (wave 110E) -- "As an additional cost to cast this spell, choose a creature type." (Caller of the Hunt) and "..., choose a creature you
# control or a warped creature card you own in exile." (Close Encounter)
# 601.2b: the caster chooses while announcing the spell (before paying, 601.2h). The spell keeps it (PaymentRecord.pick110e, 400.7: carried to the permanent,
# engine.resolve): a type is shown on the permanent as "Chosen creature type" (which "of the chosen type" reads); a creature / card is a reference
# "card|object|zone" read back as that object (608.2h: last known information once it has left). A permanent put onto the battlefield without being cast has no
# chosen type (its count is then 0).
TYPE_LINE = "As an additional cost to cast this spell, choose a creature type."
OBJECT_LINE = "As an additional cost to cast this spell, choose a creature you control or a warped creature card you own in exile."
CAST_LINE = TYPE_LINE
WAITING = object()


def has_line(ch: Any, line: str = TYPE_LINE) -> bool:
    return any(ab.text == line for ab in ch.abilities)


def _objects(plan: Plan, who: str) -> list[str]:
    """Their creatures on the battlefield and their warped creature cards in exile (702.185b: exiled with warp, still waiting for a later turn)."""
    warped = {p.card for p in plan.rules.permissions if p.label.endswith("(warped)")}
    return [c.id for c in plan.state.cards.values() if "Creature" in plan.ch(c).types and (
        (c.zone == f"{who}:battlefield" and c.controller == who) or (c.zone == f"{who}:exile" and c.owner == who and c.id in warped))]


def announce(plan: Plan, a: Any, card: Any, ch: Any) -> Any:
    """The choice made as the spell is cast (a type, or "card|object|zone"), None when the card has no such line, WAITING while the caster is asked."""
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.plan import decide

    kind = "type" if has_line(ch) else "object" if has_line(ch, OBJECT_LINE) else None
    if kind is None:
        return None
    options = [DecisionOption(id=t, label=t) for t in sorted(CREATURE_TYPES)] if kind == "type" \
        else [DecisionOption(id=c, label=plan.state.cards[c].name) for c in _objects(plan, plan.actor)]
    if a.pick110e is None:
        if not options:
            raise ActionError(f"{ch.name} needs a creature to choose")
        decide(plan, player=plan.actor, kind="choose_one", prompt=f"{ch.name}: choose a creature type" if kind == "type" else f"{ch.name}: choose a creature",
               options=options, resume={"step": "pick110e", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})}, source=card)
        return WAITING
    raw = a.pick110e.split("|")[0]
    if raw not in {o.id for o in options}:
        raise ActionError("Choose a creature type" if kind == "type" else "Choose a creature you control or a warped creature card you own in exile")
    if kind == "type":
        return raw
    chosen = plan.state.cards[raw]
    return f"{raw}|{plan.oid(chosen)}|{chosen.zone}"


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.rules.engine import INTENTS

    intent = A.parse_action(d.resume["intent"])
    intent.pick110e = chosen[0]  # type: ignore[union-attr]
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def bind(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The creature / card the spell's caster chose, as a named object for "the power of the chosen creature or card" (608.2h)."""
    from app.game.rules_state import ObjectRef

    record = plan.rules.payments.get(ctx.get("source_object") or "")
    objects = []
    if record is not None and record.pick110e and "|" in record.pick110e:
        card, oid, zone = record.pick110e.split("|", 2)
        objects = [ObjectRef(card=card, object_id=oid, zone=zone).model_dump(mode="json")]
    ctx.setdefault("refs", {})[e["as"]] = {"kind": "objects", "objects": objects}
    return True


PRIMITIVES = {"pick110e": bind}
