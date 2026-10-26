"""Wave 110J last cards: exact Oracle wordings settled by their official rulings (scratchpad rul/final11.json)."""
from __future__ import annotations

from typing import Any

from app.game.errors import ActionError
from app.game.rules_state import DecisionOption
from app.rules.plan import Plan, decide

Context = dict[str, Any]

# -- Contractual Safeguard -- the addendum (702 "Addendum" ability word: an "if you cast this spell during your main phase" condition) puts a shield
# counter first, so the second part may choose it (ruling 2022-04-29). "Choose a kind of counter on a creature you control" picks a creature and one
# kind of counter on it (608.2d); "each other creature you control" is every creature you control other than that creature.
SAFEGUARD = "Choose a kind of counter on a creature you control. Put a counter of that kind on each other creature you control."


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    if body.strip() == SAFEGUARD:  # the addendum paragraph before it is read natively (an "only_if" main-phase cast condition)
        return ([{"do": "safeguard110j"}], None, False)
    return None


def _yours(plan: Plan, pid: str) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.zone == f"{pid}:battlefield" and "Creature" in plan.ch(c).types]


def safeguard(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    pid = ctx["controller"]
    options = [DecisionOption(id=f"{c}|{k}", card_id=c, label=f"{k} counter on {plan.ch(plan.state.cards[c]).name}")
               for c in _yours(plan, pid) for k, n in sorted(plan.state.cards[c].counters.items()) if n > 0]
    if not options:  # no creature you control has a counter: nothing to choose
        return True
    decide(plan, player=pid, kind="choose_one", prompt="Choose a kind of counter on a creature you control", options=options,
           resume={"step": "safeguard110j", "ctx": ctx}, source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def resume_safeguard(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import context, effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one of the counters offered")
    cid, kind = chosen[0].split("|", 1)
    plan.note(f"{plan.name(d.player)} chooses {kind} counters", actor=d.player)
    others = [c for c in _yours(plan, d.player) if c != cid]
    context.bind_objects(plan, ctx, "safeguard110j", others)
    at = ctx["next"]
    ctx["effects"][at:at] = [{"do": "add_counters", "who": "ref:safeguard110j", "kind": kind, "n": 1}]
    effects.continue_effects(plan, ctx)


PRIMITIVES = {"safeguard110j": safeguard}
RESUME = {"safeguard110j": resume_safeguard}


# -- Captain America, First Avenger -- Throw: the damage equals the mana value of the Equipment unattached as a cost. 601.2b (602.2b): when a value
# in the text is defined by a choice the player would make later in the announcement, that choice is made at this time instead, so the Equipment
# is chosen before the targets and the division (601.2c-d, Gatherer rulings 2026-06-19: the targets and the division are chosen on activation,
# each target gets at least 1). At resolution the division stays and damage to an illegal target isn't dealt (608.2b, the same rulings).
CAPTAIN = ("Throw ... — {3}, Unattach an Equipment from Captain America: He deals damage equal to that Equipment's mana value divided as you "
           "choose among one, two, or three targets.")
_CAP_COMPONENT = 1  # the cost's parts: {3}, then the Equipment


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    if ability.kind != "activated" or ability.text != CAPTAIN:
        return None
    return {"kind": "activated", "cost": "{3}, Unattach an Equipment from ~", "effects": [{"do": "damage", "who": "target:0", "n": {"divided": 0}}],
            "target": None, "targets": [{"what": "any", "min": 1, "max": 3, "divide": {"what": "damage", "total": {"x": 1}, "value": {"cap110j": 1}}}],
            "delegated_target": "cap110j"}


def _equipment(plan: Plan, source: str) -> list[str]:
    return [c.id for c in plan.state.cards.values() if c.attached_to == source and c.zone.endswith(":battlefield") and "Equipment" in plan.ch(c).subtypes]


def cap_total(plan: Plan, source: str | None) -> int:
    """The total being divided: the chosen Equipment's mana value (while the ability is announced), else the largest one attached (an estimate for listings)."""
    chosen = getattr(plan, "cap110j", None)
    if chosen is not None:
        return int(chosen)
    return max((int(plan.ch(plan.state.cards[c]).mana_value) for c in _equipment(plan, source or "")), default=0)


def cap_announce(plan: Plan, a: Any, definition: dict[str, Any], what: str) -> Any:
    from app.game import actions as A
    from app.rules import casting

    if not isinstance(a, A.ActivateAbility):
        raise ActionError("Unsupported delegated target announcement")
    equips = _equipment(plan, a.card_id)
    given = next((c.cards for c in a.cost_choices if c.component == _CAP_COMPONENT), None)
    if given is not None and (len(given) != 1 or given[0] not in equips):
        raise ActionError("Choose one Equipment attached to it")
    if not equips:
        raise ActionError("No Equipment is attached to it")  # 118.3
    values = {int(plan.ch(plan.state.cards[c]).mana_value) for c in ([given[0]] if given else equips)}
    if len(values) > 1:  # which Equipment fixes the amount: asked now (601.2b)
        decide(plan, player=plan.actor, kind="choose_one", prompt=f"{what}: choose the Equipment to unattach (its mana value is the damage)",
               options=[DecisionOption(id=c, card_id=c, label=f"{plan.ch(plan.state.cards[c]).name} (mana value {plan.ch(plan.state.cards[c]).mana_value:g})") for c in equips],
               resume={"step": "cap110j", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}), "actor": plan.actor})
        return None
    total = values.pop()
    if total < 1:  # 601.2d: each of the one to three targets must receive at least 1 of it
        raise ActionError("That Equipment's mana value is 0: there is no damage to divide among one, two, or three targets")
    plan.cap110j = total  # type: ignore[attr-defined]
    try:
        return casting.choose_targets(plan, a, {k: v for k, v in definition.items() if k != "delegated_target"}, what)
    finally:
        plan.cap110j = None  # type: ignore[attr-defined]


def resume_cap(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.rules.engine import INTENTS

    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one Equipment")
    raw = d.resume["intent"]
    raw["cost_choices"] = [c for c in raw.get("cost_choices") or [] if c["component"] != _CAP_COMPONENT] + [{"component": _CAP_COMPONENT, "cards": chosen}]
    intent = A.parse_action({**raw, "actor": d.resume["actor"]})
    actor = plan.actor
    plan.actor = d.resume["actor"]
    plan.rules.priority, plan.rules.passed = d.resume["actor"], []
    try:
        INTENTS[intent.type](plan, intent)
    finally:
        plan.actor = actor


RESUME["cap110j"] = resume_cap
