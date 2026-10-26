"""-- wave 110A final pass -- exact wordings of the last PARTIAL cards of the bucket, read onto existing machinery.

* Damping Engine (116.2d, 601.3, 305.1): the static is a cast_limit (who "each", mostperm110a) that engine.play_land_problem also reads; the sacrifice that ignores it
  is the special action ``end_effect`` (licids): any time its player has priority, no stack, once per turn per Engine (ruling 2008-08-01), only while it applies.
* Ice Cave (118.12 / 101.4 / 107.3h): each player but the caster is offered, in turn order, the mana cost of the spell on the stack (its X as chosen)."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.plan import Plan

DAMPING = ("A player who controls more permanents than each other player can't play lands or cast artifact, creature, or enchantment spells. "
           "That player may sacrifice a permanent of their choice for that player to ignore this effect until end of turn.")
TYPES = frozenset({"Artifact", "Creature", "Enchantment"})
ICE_CAVE = "Whenever a player casts a spell, any other player may pay that spell's mana cost. If a player does, counter the spell."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == DAMPING:
        return {"kind": "static", "static": "cast_limit", "who": "each", "when": None, "filter": None, "from": None, "act": None, "max": None, "mostperm110a": True, "effects": []}
    if text == ICE_CAVE:
        d = scripts.define(replace(ability, text="Whenever a player casts a spell, any opponent may pay {1}. If a player does, counter that spell."), ch)
        if d is None or [(e["do"], e.get("who"), e.get("cost")) for e in d["effects"]] != [("each_may", "each_opponent", "{1}")]:
            return None
        return {**d, "effects": [{**d["effects"][0], "who": "each_other_than_event", "cost": "{1}", "spell_cost110a": True}]}
    return None


def _count(state: GameState, player: str) -> int:
    return sum(1 for c in state.cards.values() if c.zone.endswith(":battlefield") and c.controller == player)


def ignoring(state: GameState, player: str, src: CardInstance) -> bool:
    r = state.rules
    return r is not None and any(x["what"] == "damping110a" and x["player"] == player and x["src"] == r.object_id(src.id) and x["turn"] == state.turn.number for x in r.results)


def applies(state: GameState, src: CardInstance, player: str) -> bool:
    """601.3 / 305.1: ``player`` controls strictly more permanents than each other player still in the game, and has not paid to ignore this Engine this turn."""
    from app.rules.plan import live_players

    others = [p for p in live_players(state) if p != player]
    mine = _count(state, player)
    return player in live_players(state) and bool(others) and all(mine > _count(state, p) for p in others) and not ignoring(state, player, src)


def cast_hit(state: GameState, src: CardInstance, player: str, types: Any) -> bool:
    return bool(TYPES & set(types)) and applies(state, src, player)


def land_barred(state: GameState, info: Any, player: str) -> CardInstance | None:
    from app.rules import cast_limits

    return next((src for src, d in cast_limits._statics(state, info, "cast_limit") if d.get("mostperm110a") and applies(state, src, player)), None)


def is_engine(plan: Plan, card: CardInstance) -> bool:
    from app.rules import scripts

    return card.zone.endswith(":battlefield") and any(d.get("mostperm110a") for d in scripts.definitions(plan.ch(card)).values())


def sacrifice_start(plan: Plan, card: CardInstance) -> None:
    """The special action's cost: choose a permanent (of the player's own) to sacrifice, then it is sacrificed and the Engine is ignored until end of turn."""
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    me = plan.actor
    if not applies(plan.state, card, me):
        raise ActionError(f"{card.name} does not stop you now")
    options = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == me]
    decide(plan, player=me, kind="choose_cards", prompt=f"{card.name}: sacrifice a permanent to ignore it until end of turn",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Permanent", card_id=c) for c in options], min_choices=1, max_choices=1,
           resume={"step": "damping110a", "engine": card.id})


def resume_sacrifice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    src = plan.state.cards[d.resume["engine"]]
    me = d.player
    effects._sacrifice_cards(plan, chosen, me)
    turn = plan.state.turn.number
    plan.rules.results = [x for x in plan.rules.results if x["turn"] == turn]
    plan.rules.results.append({"player": me, "what": "damping110a", "src": plan.oid(src), "turn": turn})
    plan.note(f"{plan.name(me)} sacrifices a permanent to ignore {src.name} until end of turn", [src.id], actor=me)
    plan.rules.passed = []


def choose_order(plan: Plan, ctx: dict[str, Any], frame: dict[str, Any]) -> bool:
    """Chaotic Transformation (ruling 2022-09-09): when its controller has several of the exiled permanents left to consider, they choose which one is next (a decision, True)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    rest = frame["rows"][frame["next"]:]
    same = [r for r in rest if r["controller"] == rest[0]["controller"]]
    if len(same) < 2 or frame.get("asked") == frame["next"]:
        return False
    decide(plan, player=rest[0]["controller"], kind="choose_cards", prompt="Chaotic Transformation: choose which exiled permanent to consider next",
           options=[DecisionOption(id=r["object"], label=r["name"] or "Permanent") for r in same], min_choices=1, max_choices=1,
           resume={"step": "chaotic_order110a", "ctx": ctx})
    return True


def resume_order(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    frame = ctx["polymorph102"]
    i = frame["next"]
    pick = next(j for j in range(i, len(frame["rows"])) if frame["rows"][j]["object"] == chosen[0])
    frame["rows"].insert(i, frame["rows"].pop(pick))
    frame["asked"] = i
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "polymorph_walk102"}]
    continue_effects(plan, ctx)


PRIMITIVES: dict[str, Any] = {}
RESUME: dict[str, Any] = {"damping110a": resume_sacrifice, "chaotic_order110a": resume_order}
