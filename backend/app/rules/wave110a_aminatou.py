"""Wave 110A: Aminatou, the Fateshifter -6 - "Choose left or right. Each player gains control of all nonland permanents other than Aminatou controlled by the next
player in the chosen direction." (613.1b, 800.4 turn order: "left" is the next player in turn order, as in combat_teyo66). All of it is one resolution: the
permanents each player controls are read once (608.2h), one control effect per receiving player."""

from __future__ import annotations

from typing import Any

from app.game.rules_state import DecisionOption
from app.rules.plan import decide

Context = dict[str, Any]
TEXT = ("−6: Choose left or right. Each player gains control of all nonland permanents other than ~ controlled by the next player in the chosen direction.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    if scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    d = scripts.define(replace(ability, text="−6: Draw a card."), ch)
    return None if d is None else {**d, "effects": [{"do": "swap_control110a"}]}


def swap(plan: Any, ctx: Context, e: dict[str, Any]) -> bool:
    live = plan.live()
    if len(live) < 2:
        return True
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'Choose'}: left or right",
           options=[DecisionOption(id=v, label=v.capitalize()) for v in ("left", "right")], resume={"step": "swap_control110a", "ctx": ctx, "e": e})
    return False


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects, layers
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    live = plan.live()
    step = 1 if chosen[0] == "left" else -1
    plan.note(f"{plan.name(ctx['controller'])} chooses {chosen[0]}", actor=ctx["controller"])
    held = {p: [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == p and c.id != ctx["source_card"]
                and not plan.ch(c).is_land] for p in live}  # (read once, before any control changes: 608.2h)
    for i, p in enumerate(live):
        effects._control_effect(plan, ctx, held[live[(i + step) % len(live)]], p, "permanent")
    layers.control_sync(plan)
    continue_effects(plan, ctx)


PRIMITIVES = {"swap_control110a": swap}
RESUME = {"swap_control110a": resume}
