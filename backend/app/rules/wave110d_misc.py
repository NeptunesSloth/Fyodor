"""-- one-card wordings (wave 110D) --

Requiem Monolith: "{T}: Until end of turn, target creature gains "Whenever this creature is dealt damage, you draw that many cards and lose that much life."
That creature's controller may have this artifact deal 1 damage to it. Activate only as a sorcery." The second sentence is a choice of the TARGET's
controller (608.2d: the player who is told "may" decides); the Monolith is the damage source (120.3, 609.7)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

MONOLITH = ('{T}: Until end of turn, target creature gains "Whenever this creature is dealt damage, you draw that many cards and lose that much life." '
            "That creature's controller may have this artifact deal 1 damage to it. Activate only as a sorcery.")


ZHALFIR = "I, II — Another target nonland permanent phases out. It can't phase in for as long as you control this Saga."
DACK = "Whenever you cast a spell that targets one or more permanents, gain control of those permanents."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import events, scripts

    if ability.text == ZHALFIR:  # 702.26a, 610.3: phased out, held out for as long as its controller controls the Saga
        d = scripts.define(replace(ability, text="I, II — Another target nonland permanent phases out."), ch)
        if d is not None:
            d["effects"] = [{"do": "phase_hold110d", "who": "target"}]
        return d
    if ability.text == DACK:  # Dack Fayden's emblem (114.1): the cast event's targets (115.9b: departed ones are ignored), permanently
        cond = events.parse_condition("you cast a spell that targets one or more permanents")
        assert cond is not None
        return {"kind": "triggered", "trigger": "event", "cond": cond, "optional": False, "target": None,
                "effects": [{"do": "spell_permanents110d", "selector": cond["targets"], "as": "dack110d"},
                            {"do": "gain_control", "who": "ref:dack110d", "to": "you"}]}
    if ability.text != MONOLITH:
        return None
    d = scripts.define(replace(ability, text=MONOLITH.replace(" That creature's controller may have this artifact deal 1 damage to it.", "")), ch)
    if d is not None:
        d["effects"] += [{"do": "may_hit110d", "bind": "hit110d"}, {"do": "only_if", "cond": {"succeeded": "hit110d"}, "skip": 1},
                         {"do": "damage", "who": "target", "n": 1}]
    return d


def may_hit(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context, effects

    cards = effects._cards(plan, ctx, "target")
    context.bind_payment(ctx, e["bind"], False)
    if not cards or not plan.state.cards[cards[0]].zone.endswith(":battlefield"):
        return True
    who = plan.state.cards[cards[0]].controller
    effects.decide(plan, player=who, kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: have it deal 1 damage to {plan.state.cards[cards[0]].name}?",
                   options=[DecisionOption(id="yes", label="Yes"), DecisionOption(id="no", label="No")],
                   resume={"step": "may_hit110d", "ctx": ctx, "bind": e["bind"]})
    return False


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    if len(chosen) != 1 or chosen[0] not in ("yes", "no"):
        raise ActionError("Choose yes or no")
    context.bind_payment(d.resume["ctx"], d.resume["bind"], chosen[0] == "yes")
    effects.continue_effects(plan, d.resume["ctx"])


def spell_permanents(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, token_copy_sources

    refs = token_copy_sources.spell_targets(plan, ctx, e["selector"])
    context.refs(ctx)[e["as"]] = {"kind": "objects", "objects": [r.model_dump(mode="json") for r in refs]}
    return True


def phase_hold(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import ObjectRef
    from app.rules import effects, phase_lifetimes43

    ids = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    source = ObjectRef(card=ctx["source_card"], object_id=ctx["source_object"])
    phase_lifetimes43.phase_out(plan, source, ids, ctx["controller"], control=ctx["controller"])
    return True


PRIMITIVES: dict[str, Any] = {"phase_hold110d": phase_hold, "may_hit110d": may_hit, "spell_permanents110d": spell_permanents}
RESUME: dict[str, Any] = {"may_hit110d": resume}


CALL = "Choose up to two. Return those cards from your graveyard to your hand."


def modal_lines(lines: list[Any]) -> list[Any]:
    """Call Damage Control: "Choose up to two. Return those cards from your graveyard to your hand. • Target artifact card. • ..." is up to two modes
    (700.2), each returning its one targeted card (the common instruction acts on each target on its own, 608.2b), as "Choose up to two — • Return
    target artifact card from your graveyard to your hand. • ..."."""
    if len(lines) < 3 or lines[0].text != CALL or not all(x.text.startswith("• Target ") and x.text.endswith(" card.") for x in lines[1:]):
        return lines
    return [replace(lines[0], text="Choose up to two —"),
            *(replace(x, text=x.text[:-1].replace("• Target ", "• Return target ") + " from your graveyard to your hand.") for x in lines[1:])]
