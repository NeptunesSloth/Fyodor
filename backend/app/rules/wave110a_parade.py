"""Wave 110A: Starlight Spectacular (Parade!): the controller chooses their creatures one at a time until each has been chosen (101.4: one chooser,
in order); each gets +1/+1 until end of turn for each creature chosen before it (611.2c: the set is fixed on resolution, 608.2h: counts read once)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.plan import decide

Context = dict[str, Any]
TEXT = ("At the beginning of combat on your turn, choose creatures you control one at a time until each creature you control has been chosen. "
        "Each of those creatures gets +1/+1 until end of turn for each creature chosen before it.")


def _next(plan: Any, ctx: Context, left: list[str], order: list[str]) -> bool:
    from app.rules import effects

    left = [c for c in left if c in plan.state.cards and plan.state.cards[c].zone.endswith(":battlefield")]
    while left:
        if len(left) == 1:  # the last one has no choice (it is the one not yet chosen)
            order, left = [*order, left[0]], []
            break
        decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'Parade'}: choose a creature (chosen so far: {len(order)})",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in left], min_choices=1, max_choices=1,
               resume={"step": "parade110a", "ctx": ctx, "left": left, "order": order})
        return False
    for i, c in enumerate(order):
        if i and plan.state.cards[c].zone.endswith(":battlefield"):
            effects.PRIMITIVES["pump"](plan, ctx, {"do": "pump", "who": "object:" + plan.oid(c), "p": i, "t": i})
    return True


def parade(plan: Any, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import characteristics as chars

    mine = [c for c in plan.state.zones.get(f"{ctx['controller']}:battlefield", []) if plan.state.cards[c].controller == ctx["controller"]
            and "Creature" in chars.of(plan.state.cards[c], plan.info).types]
    return _next(plan, ctx, mine, [])


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    r = d.resume
    plan.note(f"{plan.name(d.player)} chooses {plan.state.cards[chosen[0]].name}", chosen, actor=d.player)
    if _next(plan, r["ctx"], [c for c in r["left"] if c != chosen[0]], [*r["order"], chosen[0]]):
        continue_effects(plan, r["ctx"])


SOWER = "Whenever damage is dealt to one of the chosen players, the other chosen player also loses that much life."


def other_loses(plan: Any, ctx: Context, e: dict[str, Any]) -> bool:
    """Sower of Discord: the chosen player who was not dealt the damage loses that much life (120.1; wave110a_pick.pair)."""
    from app.rules import effects, wave110a_pick

    hit = effects._players(plan, ctx, "event_player")
    other = [p for p in wave110a_pick.pair(plan, ctx["source_card"]) if p not in hit]
    return effects.PRIMITIVES["lose_life"](plan, ctx, {**e["loss"], "who": f"player:{other[0]}"}) if len(other) == 1 else True


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if scripts.self_text(ability.text, ch.name) == ("Each player may attack only the nearest opponent in the chosen direction and planeswalkers "
                                                   "controlled by that opponent."):
        return {"kind": "static", "static": "nearest110a", "effects": []}  # Pramikon: the restriction is added by the entering choice (wave110a_pick.record)
    if scripts.self_text(ability.text, ch.name) == SOWER:
        d = scripts.define(replace(ability, text="Whenever damage is dealt to a player, that player loses that much life."), ch)
        if d is None or [e["do"] for e in d["effects"]] != ["lose_life"] or d["cond"].get("subject") != "player":
            return None
        return {**d, "cond": {**d["cond"], "player": "pair110a"}, "effects": [{"do": "other_loses110a", "loss": d["effects"][0]}]}
    if scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    d = scripts.define(replace(ability, text="At the beginning of combat on your turn, draw a card."), ch)
    return None if d is None or [e["do"] for e in d["effects"]] != ["draw"] else {**d, "effects": [{"do": "parade110a"}]}


PRIMITIVES = {"parade110a": parade, "other_loses110a": other_loses}
RESUME = {"parade110a": resume}
