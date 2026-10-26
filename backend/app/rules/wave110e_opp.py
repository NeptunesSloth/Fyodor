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


# -- entry secret choice (wave 110E) -- "As this creature enters, secretly choose an opponent." (Emissary of Grudges)
# 614.12a: made as it enters, by its controller, and kept like Stalking Leonin's (group_choice.secret_choices, never logged or shown); one opponent left: no question.
SECRET = "secret110e"
SECRET_LINE = "As this creature enters, secretly choose an opponent."


def secret_definition(text: str) -> dict[str, Any] | None:
    if text not in (SECRET_LINE, "As ~ enters, secretly choose an opponent."):
        return None
    return {"kind": "replacement", "replacement": "enters_choice", "effects": [{"do": "choose_value", "who": "you", "what": SECRET}]}


def secret_prompt(plan: Plan, card: Any, controller: str) -> tuple[str, list[DecisionOption]]:
    from app.game.rules_state import DecisionOption

    return f"{card.name}: as it enters, secretly choose an opponent", [DecisionOption(id=p, label=plan.name(p)) for p in plan.live() if p != controller]


def secret_record(plan: Plan, card_id: str, controller: str, choices: dict[str, str] | None) -> None:
    if choices and choices.get(SECRET):
        plan.rules.secret_choices = {k: v for k, v in plan.rules.secret_choices.items() if k.rsplit(".", 1)[0] in plan.state.cards and plan.oid(k.rsplit(".", 1)[0]) == k}
        plan.rules.secret_choices[plan.oid(card_id)] = [controller, choices[SECRET]]


def targets_mine(plan: Plan, ctx: dict[str, Any]) -> bool:
    """"if it targets you or a permanent you control": the first target (a spell or ability on the stack) has you or one of your permanents among its targets."""
    from app.rules import stack_interaction

    sid = next((t["id"] for t in (ctx.get("targets") or []) if t["id"] in plan.state.cards), None)
    entry = stack_interaction.target_entry(plan, sid) if sid else None
    me = ctx["controller"]
    return entry is not None and any(
        t.id == me or ((c := plan.state.cards.get(t.id)) is not None and c.zone.endswith(":battlefield") and c.controller == me) for t in entry.targets)


# -- war or peace (wave 110E) -- "As this creature enters, each player chooses war or peace." (Archangel of Strife)
# 614.12a / 101.4: every player answers as it enters (the active player first); each answer is public. The record "p1:war,p2:peace" is kept by the source in
# ``chosen_objects`` (read by the selector extra ``warpeace110e:<side>``: "creatures controlled by players who chose war").
WAR = "warpeace110e"
WAR_LINE = "As ~ enters, each player chooses war or peace."
WAR_STATICS = {"Creatures controlled by players who chose war get +3/+0.": ("war", "Creatures you control get +3/+0."),
               "Creatures controlled by players who chose peace get +0/+3.": ("peace", "Creatures you control get +0/+3.")}


def war_definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    text = ability.text.strip().replace("this creature", "~")

    def define(t: str) -> dict[str, Any] | None:
        return scripts.define(replace(ability, text=t), ch)

    if text == WAR_LINE:
        return {"kind": "replacement", "replacement": "enters_choice", "effects": [{"do": "choose_value", "who": "each", "what": WAR}]}
    if (static := WAR_STATICS.get(text)) is None or (native := define(static[1])) is None:
        return None
    from app.rules import selectors

    key = selectors.Selector(types=("Creature",), extras=(f"{WAR}:{static[0]}",)).key()
    return {**native, "who": [key] if isinstance(native.get("who"), list) else key}


def war_choices(plan: Plan, controller: str, answers: dict[str, str], out: dict[str, Any]) -> None:
    """entry_plan's part: one question per player still to answer, the active player first (101.4)."""
    order = [plan.active, *(p for p in plan.live() if p != plan.active)] if plan.active in plan.live() else plan.live()
    for pid in order:
        key = f"{WAR}:{pid}"
        if key in answers:
            out.setdefault("choices", {})[key] = answers[key]
        elif "choice" not in out:
            out["choice"] = {"what": key, "decider": pid}


def war_prompt(plan: Plan, card: Any, what: str) -> tuple[str, list[DecisionOption]]:
    from app.game.rules_state import DecisionOption

    return f"{card.name}: as it enters, {plan.name(what.split(':', 1)[1])} chooses war or peace", [DecisionOption(id="war", label="War"), DecisionOption(id="peace", label="Peace")]


def war_record(plan: Plan, card_id: str, choices: dict[str, str] | None) -> None:
    picks = {k.split(":", 1)[1]: v for k, v in (choices or {}).items() if k.startswith(WAR + ":")}
    if picks:
        plan.rules.chosen_objects[card_id] = ",".join(f"{p}:{v}" for p, v in picks.items())
        plan.do({"type": "set_choice", "card_id": card_id, "key": "War or peace", "value": ", ".join(f"{plan.name(p)}: {v}" for p, v in picks.items())},
                actor=plan.state.cards[card_id].controller)


def chose(plan: Plan, card: Any, source: str | None, side: str) -> bool:
    """Is the player who controls ``card`` one of those who chose ``side`` as the source entered?"""
    record = plan.rules.chosen_objects.get(source or "", "")
    return f"{card.controller}:{side}" in record.split(",")
