"""-- (wave 110B) -- Tahngarth, First Mate: "Whenever an opponent attacks with one or more creatures, if Tahngarth is tapped, you may have that opponent gain
control of Tahngarth until end of combat. If you do, choose a player or planeswalker that opponent is attacking. Tahngarth is attacking that player or
planeswalker."

* 508.4: a creature put onto the battlefield (or here, made) attacking was never declared as an attacker, so attack triggers don't see it (rulings 2019-08-23);
  its controller (the opponent) chooses what it attacks among what that opponent is attacking (a player or planeswalker, not a battle).
* 613.1b control effect until end of combat (it does not untap Tahngarth); 603.4 the intervening "if" is checked on trigger and again on resolution.
* No player or planeswalker to choose (their attackers left combat): the control still changes but Tahngarth isn't attacking (ruling 2019-08-23).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_TEXT = ("Whenever an opponent attacks with one or more creatures, if ~ is tapped, you may have that opponent gain control of ~ until end of combat. "
         "If you do, choose a player or planeswalker that opponent is attacking. ~ is attacking that player or planeswalker.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ch.name != "Tahngarth, First Mate" or ability.text.replace("Tahngarth", "~") != _TEXT:
        return None
    base = scripts.define(replace(ability, text="Whenever an opponent attacks with one or more creatures, if ~ is tapped, you draw a card."), ch)
    if base is None or len(base.get("effects", [])) != 2:
        return None
    return {**base, "optional": True, "effects": [base["effects"][0], {"do": "tahngarth110b", "say110n": "have that opponent gain control of Tahngarth until end of combat"}]}


def _options(plan: Plan, opp: str, me: str) -> list[Any]:
    from app.game.rules_state import DecisionOption

    out: dict[str, Any] = {}
    for c in plan.state.cards.values():
        if c.id != me and c.controller == opp and c.attacking is not None and c.zone.endswith(":battlefield"):
            t = c.attacking
            if t.id in out or t.id not in (plan.live() if t.kind == "player" else plan.state.cards):
                continue
            if t.kind == "player":
                out[t.id] = DecisionOption(id=t.id, label=plan.name(t.id))
            elif "Planeswalker" in plan.ch(plan.state.cards[t.id]).types:
                out[t.id] = DecisionOption(id=t.id, label=plan.state.cards[t.id].name or "Planeswalker", card_id=t.id)
    return list(out.values())


def run(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects, layers
    from app.rules.plan import decide

    card = plan.state.cards.get(ctx.get("source_card") or "")
    opp = plan.active
    if card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != ctx.get("source_object") or not card.tapped or opp == ctx["controller"]:
        return True
    effects._control_effect(plan, ctx, [card.id], opp, "end_of_combat")
    layers.control_sync(plan)
    options = _options(plan, opp, card.id)
    if len(options) > 1:
        decide(plan, player=opp, kind="choose_one", prompt=f"{card.name}: choose a player or planeswalker you are attacking for it to attack",
               options=options, resume={"step": "tahngarth110b", "ctx": ctx, "card": card.id})
        return False
    if options:
        _attack(plan, card.id, options[0].id, opp)
    return True


def _attack(plan: Plan, cid: str, target: str, opp: str) -> None:
    kind = "player" if target in plan.state.players else "card"
    plan.do({"type": "attack", "card_ids": [cid], "target": {"kind": kind, "id": target}}, actor=opp)


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one of the options offered")
    _attack(plan, d.resume["card"], chosen[0], d.player)
    effects.continue_effects(plan, d.resume["ctx"])


PRIMITIVES = {"tahngarth110b": run}
RESUME = {"tahngarth110b": resume}
