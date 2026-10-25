"""-- wave 110N -- exact Oracle wordings of single cards, built from parts of wordings the grammar already reads.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]

_NATIVE_HEA = ("At the beginning of your upkeep, if there are five colors among permanents you control and your life total is greater than or "
               "equal to your starting life total, you win the game.")
_SIX_TYPES: Def = {"value": {"union_types110n": "you"}, "op": ">=", "n": 6}


def _hea(d: Def) -> Def:
    """Happily Ever After: the middle clause joins the native condition, in the trigger's intervening "if" (603.4) and as it resolves."""
    both = {"all": [*d["if"]["all"][:1], _SIX_TYPES, *d["if"]["all"][1:]]}
    return {**d, "if": both, "effects": [{**e, "cond": both} if e.get("do") == "only_if" else e for e in d["effects"]]}


# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    "At the beginning of your upkeep, if there are five colors among permanents you control, there are six or more card types among permanents you "
    "control and/or cards in your graveyard, and your life total is greater than or equal to your starting life total, you win the game.":
        (_NATIVE_HEA, _hea),
}


ROCK_CAST, ROCK_LANDS = "rock_cast110n", "rock_lands110n"
_FLAGS = {"You can't cast Rock Jockey if you've played a land this turn.": ROCK_CAST,
          "You can't play lands if this creature was cast this turn.": ROCK_LANDS}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if (flag := _FLAGS.get(ability.text.strip())) is not None:
        return {"kind": "static", "static": flag, "effects": []}
    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def union_types(plan: Any, ctx: Any, v: Def) -> int:
    """205.2a: the card types shared out among the player's permanents and the cards in their graveyard (a card type, not a subtype)."""
    from app.rules.values import CARD_TYPES

    me = ctx["controller"]
    found: set[str] = set()
    for c in plan.state.cards.values():
        if (c.zone == f"{me}:battlefield" and plan.in_game(c)) or c.zone == f"{me}:graveyard":
            found |= {"Kindred" if t == "Tribal" else t for t in plan.ch(c).types if t in CARD_TYPES}
    return len(found)


_DECREE = ("Counter target spell. If a permanent spell is countered this way, exile it instead of putting it into its owner's graveyard. "
           "You may cast that card without paying its mana cost for as long as it remains exiled.")


def parse(body: str) -> Any:
    """Exact spell bodies: the parts the grammar reads, joined with the card's own step."""
    from app.rules import scripts

    if body.strip() == _DECREE:
        parsed = scripts.parse_effects("Counter target spell. If that spell is countered this way, exile it instead of putting it into its owner's graveyard. "
                                       "You may cast that card without paying its mana cost for as long as it remains exiled.")
        if parsed is not None and len(parsed[0]) == 2 and parsed[0][0].get("do") == "counter":
            effects, target, optional = parsed
            return [{**effects[0], "do": "decree110n"}, effects[1]], target, optional
    return None


def decree(plan: Any, ctx: Any, e: Def) -> bool:
    """Thranduil's Decree: a permanent spell is exiled instead of going to the graveyard (608.2c, 701.6a); only a card that is in exile because of it may then
    be cast (a nonpermanent spell, or one that can't be countered, leaves "that card" nothing to be cast)."""
    from app.rules import context, effects
    from app.rules.values import PERMANENT_TYPES

    sids = effects._stack_targets(plan, ctx, e)
    perm = bool(sids) and bool(plan.ch(plan.state.cards[sids[0]]).types & PERMANENT_TYPES)
    effects.counter(plan, ctx, {**e, "do": "counter", "to": "exile" if perm else None})
    if not (perm and plan.state.cards[sids[0]].zone.endswith(":exile")):
        context.bind_objects(plan, ctx, e["as"], [])  # nothing was exiled by this: no card to cast
    return True


def _willow(d: Def) -> Def:
    return {**d, "effects": [{"do": "willow110n", "who": "target"}]}


_BUILD["{G}: Until end of turn, Autumn Willow can be the target of spells and abilities controlled by target player as though it didn't have shroud."] = (
    "{G}: Target player gains 1 life.", _willow)


def willow(plan: Any, ctx: Any, e: Def) -> bool:
    """609.4: for the turn, the chosen player's spells and abilities may target this object although it has shroud (702.18a); the permission is theirs
    and about this object only (400.7), so it ends with the turn or when the Willow leaves."""
    from app.rules import effects

    src = plan.state.cards.get(ctx.get("source_card", ""))
    if src is None or not src.zone.endswith(":battlefield") or plan.oid(src) != ctx.get("source_object"):
        return True
    for pid in effects._players(plan, ctx, e["who"]):
        plan.rules.cast_limits.append({"shroud_ignore110n": {"card": src.id, "oid": plan.oid(src), "player": pid}, "controller": ctx["controller"],
                                       "until": "turn", "turn": plan.state.turn.number, "spells": False, "label": ctx.get("name") or "Targeting permission"})
        plan.note(f"{plan.name(pid)} may target {src.name} as though it didn't have shroud this turn", actor=ctx["controller"])
    return True


def ignores_shroud(plan: Any, chooser: str, card: Any) -> bool:
    from app.rules import cast_limits

    return any(d["player"] == chooser and d["card"] == card.id and d["oid"] == plan.oid(card)
               for x in plan.rules.cast_limits if (d := x.get("shroud_ignore110n")) and cast_limits._record_live(plan.state, x))


def cast_problem(state: Any, player: str, ch: Any) -> str | None:
    """Rock Jockey: 601.3, the spell can't be cast once its caster has played a land this turn (305.1: played, not put onto the battlefield)."""
    from app.rules import scripts

    r = state.rules
    if r is None or not any(d.get("static") == ROCK_CAST for d in scripts.definitions(ch).values()):
        return None
    return f"{ch.name or 'It'} can't be cast if you've played a land this turn" if r.lands_this_turn(player, state.turn.number) else None


def land_problem(state: Any, player: str, info: Any) -> str | None:
    """Rock Jockey: 305.1, no land may be played by its controller while it is on the battlefield and was cast this turn (its spell left a cast
    record that names the permanent it became, 400.7)."""
    from app.rules import static_perm100d
    from app.rules.plan import Plan

    r = state.rules
    log = r.turn_log if r is not None else None
    if info is None or log is None or log.turn != state.turn.number:
        return None
    plan = Plan.view(state, player, info)
    for c in state.cards.values():
        if c.zone == f"{player}:battlefield" and c.controller == player and plan.in_game(c) and static_perm100d._statics(plan, c, ROCK_LANDS) \
                and any(n.became == plan.oid(c) for n in log.casts):
            return f"{c.name}: you can't play lands, it was cast this turn"
    return None


PRIMITIVES: dict[str, Any] = {"decree110n": decree, "willow110n": willow}
RESUME: dict[str, Any] = {}
