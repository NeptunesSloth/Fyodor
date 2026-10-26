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
