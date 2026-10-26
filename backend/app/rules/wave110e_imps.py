"""Nettling Imp / Norritt (wave 110E): "{T}: Choose target non-Wall creature the active player has controlled continuously since the beginning of the turn.
That creature attacks this turn if able. Destroy it at the beginning of the next end step if it didn't attack this turn. Activate only [during an opponent's
turn, ]before attackers are declared."

508.1d / 508.1a: the requirement is the existing must_attack restriction; 603.7 the end-step destroy is a delayed trigger of the same target and its "if" is
checked as it resolves (history "attacked": declared as an attacker this turn, 508.1). The target is a non-Wall creature the active player (not necessarily the
controller) has controlled since the turn began (302.6 style continuous control: selectors controlled_since_turn_start69)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

_HEAD = ("{T}: Choose target non-Wall creature the active player has controlled continuously since the beginning of the turn. That creature attacks this turn if able. "
         "Destroy it at the beginning of the next end step if it didn't attack this turn. Activate only ")
_TAILS = {"during an opponent's turn, before attackers are declared.": True, "before attackers are declared.": False}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors
    from app.rules.controller_turn_history69 import EXTRA

    if (grp := group_definition(ability, ch)) is not None or (grp := vec_definition(ability, ch)) is not None:
        return grp
    text = ability.text.strip()
    if not text.startswith(_HEAD) or text[len(_HEAD):] not in _TAILS:
        return None
    opponents_only = _TAILS[text[len(_HEAD):]]
    base = scripts.define(replace(ability, text="{T}: Target non-Wall creature attacks this turn if able. Activate only before attackers are declared."), ch)
    kill = scripts.parse_effects("Target creature attacks this turn if able. At the beginning of the next end step, destroy it.")
    if base is None or kill is None or len(kill[0]) != 3:
        return None
    sel = selectors.from_key(base["target"]["what"])
    sel = replace(sel, controller="active", extras=(*sel.extras, EXTRA))
    delayed = {**kill[0][1], "n": 2}  # 603.4: the "if" is checked again as the delayed trigger resolves
    effects = [*base["effects"], delayed, {"do": "deferred:didnt_attack110e", "who": "target"}, kill[0][2]]
    restriction = [*base["restriction"], *([{"kind": "opponents_turn"}] if opponents_only else [])]
    return {**base, "effects": effects, "restriction": restriction, "target": {**base["target"], "what": sel.key()}}


_GROUP = ("{T}: Non-Wall creatures the active player controls attack this turn if able. At the beginning of the next end step, destroy each of those creatures that "
          "didn't attack this turn. Activate only during an opponent's turn and only before combat.")


def group_definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    """Maddening Imp: 508.1d the requirement binds the non-Wall creatures the active player controls as it resolves (611.2c: "those creatures"); the end-step
    destroy keeps only those that didn't attack (603.7, the delayed trigger reads the turn's attack history as it resolves)."""
    from app.rules import scripts, selectors

    if ability.text.strip() != _GROUP:
        return None
    base = scripts.define(replace(ability, text="{T}: Target non-Wall creature attacks this turn if able. Activate only during an opponent's turn, before attackers are declared."), ch)
    if base is None:
        return None
    who = replace(selectors.from_key(base["target"]["what"]), controller="active").key()
    steps = [{**r, "phases": [p for p in r["phases"] if p != "begin_combat"]} if r["kind"] == "step" else r for r in base["restriction"]]  # "only before combat": not in the beginning of combat step
    return {**base, "target": None, "restriction": steps, "effects": [
        {"do": "restrict", "who": who, "rules": ["must_attack"], "note_group": {"as": "imp110e", "who": who}},
        {"do": "delayed", "when": {"kind": "step", "step": "end", "whose": "next"}, "n": 1},
        {"do": "destroy_unattacked110e", "who": "ref:imp110e"}]}


_VEC = ("{T}: Target opponent chooses any number of creatures they control. During that player's next turn, the chosen creatures attack if able, and other creatures can't "
        "attack. At the beginning of that turn's end step, destroy each of the chosen creatures that didn't attack this turn. Activate only during your turn.")


def vec_definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    """Oracle en-Vec: the target opponent's choice (not a target), then rules for that player's next turn (508.1d must attack, 508.1c can't attack) and a delayed
    end-step destroy of the chosen creatures that didn't attack."""
    from app.rules import scripts

    if ability.text.strip() != _VEC:
        return None
    base = scripts.define(replace(ability, text="{T}: Target opponent chooses up to ten creatures they control. Activate only during your turn."), ch)
    if base is None or base["effects"][0].get("do") != "player_chooses":
        return None
    pick = {**base["effects"][0], "n": 99, "as": "vec110e", "optional": True}  # (always asks: choosing none is allowed)
    return {**base, "effects": [pick, {"do": "vec_rules110e", "who": "ref:vec110e", "player": "target"}]}


def vec_rules(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """508.1d / 508.1c: both rules begin as the target's next turn does (attack_destinations.begin_window) and end with it; the chosen creatures carry a marker that
    exempts them from "other creatures can't attack" (combat.attack_forbidden). 603.7: the end-step trigger is the target's next end step."""
    import secrets

    from app.rules import delayed, effects, layers, selectors

    source = ctx.get("source_object") or ""
    for pid in effects._players(plan, ctx, e["player"]):
        eid = secrets.token_hex(4)
        chosen = effects._cards(plan, ctx, e["who"])
        layers.add_effect(plan, affected=[plan.oid(c) for c in chosen], layer="6", source=source, controller=ctx["controller"], duration="permanent",
                          imposes=("must_attack", f"vec110e:{eid}"), declaration_window="next_turn", declaration_player=pid)
        layers.add_effect(plan, affected=[], who=selectors.Selector(types=("Creature",)).key(), layer="6", source=source, controller=ctx["controller"],
                          duration="permanent", imposes=(f"cant_attack_unless_vec110e:{eid}",), declaration_window="next_turn", declaration_player=pid)
        sub = {**ctx, "effects": [{"do": "deferred:destroy_unattacked110e", "who": e["who"]}], "next": 0}
        delayed.create(plan, sub, {"do": "delayed", "when": {"kind": "step", "step": "end", "whose": "payer", "player": pid}, "n": 1})
    return True


def destroy_unattacked(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The delayed trigger: destroy each bound creature that wasn't declared as an attacker this turn (508.1; the bound objects, 400.7)."""
    from app.rules import conditions, context, effects

    doomed = []
    for cid in effects._cards(plan, ctx, e["who"]):
        context.bind_objects(plan, ctx, "imp_one110e", [cid])
        if conditions.holds(plan, ctx, {"history": "object", "object": "ref:imp_one110e", "what": "attacked", "negate": True}):
            doomed.append(cid)
    context.bind_objects(plan, ctx, "imp_kill110e", doomed)
    return bool(doomed) and effects.PRIMITIVES["destroy"](plan, ctx, {"do": "destroy", "who": "ref:imp_kill110e"})


def didnt_attack(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The delayed trigger's intervening "if it didn't attack this turn" (603.4): the next effect happens only then. ``who`` is the target, bound as the trigger was
    created (delayed._bind_now), so it is the very object that was chosen (400.7: a creature that left and came back is not it)."""
    from app.rules import conditions

    if not conditions.holds(plan, ctx, {"history": "object", "object": e["who"], "what": "attacked", "negate": True}):
        ctx["next"] += 1
    return True


PRIMITIVES = {"didnt_attack110e": didnt_attack, "destroy_unattacked110e": destroy_unattacked, "vec_rules110e": vec_rules}
