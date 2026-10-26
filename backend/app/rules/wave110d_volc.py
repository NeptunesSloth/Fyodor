"""Wave 110D: spells with several "target ... of an opponent's choice" groups mixed with the caster's own groups (Volcanic Offering).

* Ruling 2014-11-07 (Volcanic Offering): the opponents are chosen as it is cast (not targeted), the same one or different ones, and may pick the same target as you.
* 115.1, 601.2c: the caster announces the own targets; for each "of an opponent's choice" group the caster picks which opponent chooses
  (one opponent: no question) and that opponent picks the target. The caster still pays and owns cancellation.
* 115.3: each instance of the word "target" is its own group, so both lands (or both creatures) may be the same object.
* Several opponents: which opponent chooses is asked per group, so different opponents may choose (no ruling forces one opponent for all).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import DecisionOption

if TYPE_CHECKING:
    from app.rules.plan import Plan

MARK = "groups110d"
OPP, PICK = "opp_groups110d", "pick_groups110d"
LINES = {  # exact spell line -> the line read with every group the caster's (the groups in the list are the opponent's choice)
    "Destroy target nonbasic land you don't control and target nonbasic land of an opponent's choice you don't control.":
        ("Destroy target nonbasic land you don't control and target nonbasic land you don't control.", [1]),
    "Volcanic Offering deals 7 damage to target creature you don't control and 7 damage to target creature of an opponent's choice you don't control.":
        ("Volcanic Offering deals 7 damage to target creature you don't control and 7 damage to target creature you don't control.", [1]),
}


def line(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    if ability.kind != "spell" or (hit := LINES.get(ability.text.split(" (")[0])) is None:
        return None
    d = scripts.define(replace(ability, text=hit[0]), ch)
    return {**d, "delegated_target": MARK, "dgroups110d": hit[1]} if d else None


def _source(plan: Plan, a: Any) -> Any:
    from app.rules import casting

    return casting._target_source(plan, a)


def _legal(plan: Plan, res: dict[str, Any], g: int) -> list[str]:
    from app.rules import targets

    a = A.parse_action(res["intent"])
    return targets.legal_targets(plan, res["specs"][g]["what"], res["actor"], _source(plan, a), a.card_id)  # type: ignore[union-attr]


def announce(plan: Plan, a: A.CastSpell | A.ActivateAbility, definition: dict[str, Any], what: str) -> Any:
    from app.rules import casting, flagbearer86, scripts

    if not isinstance(a, A.CastSpell):
        raise ActionError("Unsupported delegated target announcement")
    specs = scripts.target_groups(definition)
    dg = sorted(definition["dgroups110d"])
    own = [s for i, s in enumerate(specs) if i not in dg]
    found = casting.choose_groups(plan, own, plan.actor, _source(plan, a), a.card_id, list(a.targets), list(a.target_counts), list(a.division),
                                  a.x_value, what, (), required_any=frozenset(flagbearer86.current(plan)))
    if found.ask is not None:
        casting.ask_targets(plan, plan.actor, found, own, what, casting._announcing(plan, "cast_group", a, counts=found.counts))
        return None
    picks = getattr(plan, "delegated110d", None)
    if not isinstance(picks, dict):  # the own targets are announced: now the opponents' groups
        res = {"intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"}), "actor": plan.actor, "specs": specs, "dgroups": dg,
               "picks": {}, "opponent": None, "name": what}
        if not all(_legal(plan, res, g) for g in dg):
            raise ActionError(f"{what} has no legal target")
        _next(plan, res)
        return None
    own_groups = iter(found.groups)
    groups = [[casting.target_ref(plan, picks[i])] if i in dg else [casting.target_ref(plan, t) for t in next(own_groups)] for i in range(len(specs))]
    return casting.ChosenTargets(flat=[t for g in groups for t in g], groups=groups, specs=specs, division=found.division)


def _next(plan: Plan, res: dict[str, Any]) -> None:
    from app.rules.plan import decide

    todo = [g for g in res["dgroups"] if str(g) not in res["picks"]]
    if not todo:
        _finish(plan, res)
        return
    opponents = [pid for pid in plan.live() if pid != res["actor"]]
    if not opponents:
        raise ActionError("There is no opponent to select the target")
    if len(opponents) == 1:
        _ask(plan, {**res, "opponent": opponents[0]}, todo[0])
        return
    decide(plan, player=res["actor"], kind="choose_one", prompt=f"Choose an opponent to select target {todo[0] + 1} for {res['name']}",
           options=[DecisionOption(id=pid, label=plan.name(pid)) for pid in opponents], resume={"step": OPP, **res})


def _ask(plan: Plan, res: dict[str, Any], g: int) -> None:
    from app.rules import casting
    from app.rules.plan import decide

    decide(plan, player=res["opponent"], kind="choose_one", prompt=f"Choose a target for {res['name']}",
           options=[DecisionOption(id=cid, label=casting.target_label(plan, cid), card_id=cid if cid in plan.state.cards else None)
                    for cid in _legal(plan, res, g)], resume={"step": PICK, "group": g, **res})


def _res(d: Any) -> dict[str, Any]:
    return {k: v for k, v in d.resume.items() if k not in ("step", "group")}


def resume_opponent(plan: Plan, d: Any, chosen: list[str]) -> None:
    res = _res(d)
    if d.player != res["actor"] or len(chosen) != 1 or chosen[0] == res["actor"] or chosen[0] not in plan.live():
        raise ActionError("Choose an opponent still in the game")
    _ask(plan, {**res, "opponent": chosen[0]}, next(g for g in res["dgroups"] if str(g) not in res["picks"]))


def resume_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    res = _res(d)
    g = d.resume["group"]
    if d.player != res["opponent"] or plan.actor != res["opponent"]:
        raise ActionError("Only the chosen opponent may select the target")
    if len(chosen) != 1 or chosen[0] not in _legal(plan, res, g):
        raise ActionError("That is not a legal target")
    _next(plan, {**res, "picks": {**res["picks"], str(g): chosen[0]}, "opponent": None})


def _finish(plan: Plan, res: dict[str, Any]) -> None:
    from app.rules.engine import INTENTS

    intent = A.parse_action({**res["intent"], "actor": res["actor"]})
    actor = plan.actor
    plan.actor, plan.delegated110d = res["actor"], {int(k): v for k, v in res["picks"].items()}
    plan.rules.priority, plan.rules.passed = res["actor"], []
    try:
        INTENTS[intent.type](plan, intent)
    finally:
        plan.actor, plan.delegated110d = actor, None


RESUME = {OPP: resume_opponent, PICK: resume_pick}
