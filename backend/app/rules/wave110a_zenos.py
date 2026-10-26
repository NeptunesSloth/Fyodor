"""-- wave 110A -- Zenos yae Galvus // Shinryu, Transcendent Rival.

Front: "When ~ enters, choose a creature an opponent controls. Until end of turn, creatures other than ~ and the chosen creature get -2/-2." The choice is made
as the trigger resolves (608.2c) and is public; it is remembered like an entering choice (wave110a_pick: RulesState.chosen_objects, by object id, 400.7) and
the set of creatures that get -2/-2 is fixed as the effect begins (611.2c). "When the chosen creature leaves the battlefield, transform ~" looks back at the
chosen object (603.10a).
Back: "As this creature transforms into Shinryu, choose an opponent." is made as the card turns over, before state-based actions (701.28, a replacement-like
step like Curse of Leeches, transform_emblems.apply); the player is remembered as "Chosen opponent" (chosen.record), and "When the chosen player loses the game,
you win the game" (603.10f look-back, 104.2b) reads it."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

ETB = "When ~ enters, choose a creature an opponent controls. Until end of turn, creatures other than ~ and the chosen creature get -2/-2."
LEAVES = "When the chosen creature leaves the battlefield, transform ~."
AS = "As this creature transforms into Shinryu, choose an opponent."
CHAINS = "When the chosen player loses the game, you win the game."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text == ETB:
        pump = selectors.Selector(types=("Creature",), other=True, extras=("not_picked110a",))
        return {"kind": "triggered", "trigger": "enters_self", "optional": False, "target": None,
                "effects": [{"do": "zenos_choose110a"}, {"do": "pump", "who": pump.key(), "p": -2, "t": -2}]}
    if text == LEAVES:
        native = scripts.define(replace(ability, text="When another creature you control leaves the battlefield, transform ~."), ch)
        if native is None:
            return None
        return {**native, "cond": {**native["cond"], "sel": selectors.parse("chosen creature").key()}}  # type: ignore[union-attr]
    if text == AS or ability.text.strip() == AS:
        return {"kind": "static", "static": "as_transform_choose110a", "effects": []}
    if text == CHAINS:
        native = scripts.define(replace(ability, text="When ~ transforms into ~, you win the game."), ch)
        return None if native is None else {**native, "cond": {"event": "lose_game", "subject": "player", "player": "chosen"}}
    return None


def choose(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import selectors
    from app.rules.plan import decide

    src = plan.state.cards.get(ctx.get("source_card") or "")
    sel = selectors.Selector(types=("Creature",), controller="opponent")
    ids = selectors.candidates(plan, sel, ctx["controller"], ctx.get("source_card"))
    if not ids or src is None:
        return True  # nothing to choose: the -2/-2 hits every other creature
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or src.name}: choose a creature an opponent controls", source=src,
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in ids], resume={"step": "zenos_choose110a", "ctx": ctx})
    return False


def resume_choose(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import wave110a_pick
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    src = plan.state.cards.get(ctx.get("source_card") or "")
    plan.note(f"{plan.name(d.player)} chooses {plan.state.cards[chosen[0]].name}", [chosen[0]], actor=d.player)
    if src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
        wave110a_pick.record(plan, src.id, {wave110a_pick.WHAT: chosen[0]})
    ctx["zenos_chosen"] = chosen[0]
    continue_effects(plan, ctx)


def transform_choose(plan: Plan, card: CardInstance) -> None:
    """As it turns over into Shinryu its controller chooses an opponent (a pause before state-based actions, like Curse of Leeches)."""
    from app.game.rules_state import DecisionOption
    from app.rules import scripts
    from app.rules.plan import decide

    if plan.manual(card) or not any(d.get("static") == "as_transform_choose110a" for d in scripts.definitions(plan.ch(card)).values()):
        return
    opponents = [p for p in plan.live() if p != card.controller]
    if opponents:
        decide(plan, player=card.controller, kind="choose_one", prompt=f"{card.name}: choose an opponent", source=card,
               options=[DecisionOption(id=p, label=plan.name(p)) for p in opponents], resume={"step": "zenos_opponent110a", "card": card.id})


def resume_opponent(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import chosen as picked

    card = plan.state.cards[d.resume["card"]]
    plan.note(f"{plan.name(d.player)} chooses {plan.name(chosen[0])}", actor=d.player)
    plan.do({"type": "set_choice", "card_id": card.id, "key": "Chosen opponent", "value": plan.name(chosen[0])}, actor=d.player)
    picked.record(plan, card.id, chosen[0])


PRIMITIVES: dict[str, Any] = {"zenos_choose110a": choose}
RESUME: dict[str, Any] = {"zenos_choose110a": resume_choose, "zenos_opponent110a": resume_opponent}
