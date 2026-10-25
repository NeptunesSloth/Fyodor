"""-- one-card wordings (wave 110D) --

Requiem Monolith: "{T}: Until end of turn, target creature gains "Whenever this creature is dealt damage, you draw that many cards and lose that much life."
That creature's controller may have this artifact deal 1 damage to it. Activate only as a sorcery." The second sentence is a choice of the TARGET's
controller (608.2d: the player who is told "may" decides); the Monolith is the damage source (120.3, 609.7)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

MONOLITH = ('{T}: Until end of turn, target creature gains "Whenever this creature is dealt damage, you draw that many cards and lose that much life." '
            "That creature's controller may have this artifact deal 1 damage to it. Activate only as a sorcery.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

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


PRIMITIVES: dict[str, Any] = {"may_hit110d": may_hit}
RESUME: dict[str, Any] = {"may_hit110d": resume}
