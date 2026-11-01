"""Wave 111F: whole Star Trek lines (trk/trc, Oracle text of 2026-10-30) the grammar reads only in other words.

* "… Then return a land card from your graveyard to your hand. If you can't, create a Treasure token." (Temporal Conqueror): the return is no
  target and not optional (608.2c), so "can't" is that your graveyard holds no such card as it would be returned (after the mill before it);
  then the other instruction instead. (The draw form, Roots of Wisdom and Inventive Iteration, is wave 110D's / 68's.)
"""

from __future__ import annotations

import copy
import re
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

_CANT = re.compile(r"^(?P<head>.+\. Then return an? [a-z ]+ card from your graveyard to your hand\.) If you can't, (?P<other>create [^.]+\.)$")
_WORF_HEAD = ("When ~ enters, for each opponent, gain control of up to one target creature that player controls with mana value 3 or less until end of turn. "
              "Untap those creatures.")
WORF = _WORF_HEAD + " Until end of turn, they become Warriors in addition to their other types and gain haste."


def _worf(ability: Any, ch: Any) -> dict[str, Any] | None:
    """Worf, Intelligence Contractor: the native "They gain haste until end of turn." plus the creature type each of those creatures gains (layer 4,
    205.1b "in addition to their other types"), until end of turn, as the grammar's singular "it becomes a Warrior in addition to its other types" is."""
    from app.rules import scripts

    d = scripts.define(replace(ability, text=_WORF_HEAD + " They gain haste until end of turn."), ch)
    if d is None or [e["do"] for e in d["effects"]] != ["gain_control", "untap", "grant"] or len({e["who"] for e in d["effects"]}) != 1:
        return None
    who = d["effects"][0]["who"]
    become = {"do": "become", "who": who, "types": [], "retain": True, "add_creature_types": ["Warrior"], "duration": "end_of_turn"}
    return {**d, "effects": [*d["effects"][:2], become, d["effects"][2]]}


BLUFF = ("Choose target noncreature spell an opponent controls. That player may exile it. If they don't, you may cast a noncreature spell from your hand "
         "without paying its mana cost.")


def _bluff(ability: Any, ch: Any) -> dict[str, Any] | None:
    """Brazen Bluff: the target spell's controller chooses whether to exile it (608.2d: a choice made as the spell resolves, by the player the
    instruction names); if they don't, its caster may cast a noncreature spell from their hand without paying its mana cost (608.2g: during the
    resolution, timing permissions ignored)."""
    from app.rules import scripts

    head = scripts.define(replace(ability, text="Exile target noncreature spell an opponent controls."), ch)
    cast = scripts.parse_effects("You may cast a noncreature spell from your hand without paying its mana cost.")
    if head is None or cast is None or cast[1] is not None or [e["do"] for e in head["effects"]] != ["exile"] or [e["do"] for e in cast[0]] != ["free_cast"]:
        return None
    return {**head, "effects": [{"do": "bluff_offer111f", "bind": "bluff111f"}, {"do": "only_if", "cond": {"succeeded": "bluff111f", "negate": True}, "skip": 1},
                                copy.deepcopy(cast[0][0])]}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == WORF:
        return _worf(ability, ch)
    if text == BLUFF and ability.kind == "spell":
        return _bluff(ability, ch)
    m = _CANT.match(text)
    if m is None:
        return None
    d = scripts.define(replace(ability, text=m["head"]), ch)
    other = scripts.parse_effects(m["other"][:1].upper() + m["other"][1:])
    if d is None or other is None or other[1] is not None or not d.get("effects"):
        return None
    last = d["effects"][-1]
    if last.get("do") != "return_choice" or last.get("n") != 1 or last.get("upto") or last.get("to") != "hand":
        return None
    d["effects"][-1] = {"do": "return_or_else111f", "effect": last, "else": copy.deepcopy(other[0])}
    return d


def return_or_else(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Return the card when there is one to return, else carry out the other instruction ("If you can't, …")."""
    from app.rules import selectors

    effect = e["effect"]
    found = selectors.candidates(plan, selectors.from_key(effect["sel"]), ctx["controller"], ctx.get("source_card"))
    ctx["effects"][ctx["next"]:ctx["next"]] = [effect] if found else copy.deepcopy(e["else"])
    return True


def bluff_offer(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Ask the target spell's controller whether they exile it (Brazen Bluff)."""
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.effects import _cards
    from app.rules.plan import decide

    spells = [c for c in _cards(plan, ctx, "target") if plan.state.cards[c].zone == "stack"]
    if not spells:  # (an illegal target: the spell doesn't resolve at all, 608.2b; nothing to offer)
        context.refs(ctx)[e["bind"]] = {"kind": "payment", "ok": True}
        return True
    spell = plan.state.cards[spells[0]]
    src = plan.state.cards.get(ctx.get("source_card") or "")
    decide(plan, player=spell.controller, kind="choose_one",
           prompt=f"{ctx.get('name') or 'Brazen Bluff'}: exile {spell.name}? If you don't, {plan.name(ctx['controller'])} may cast a noncreature spell "
                  "from their hand without paying its mana cost",
           options=[DecisionOption(id="exile", label=f"Exile {spell.name}"), DecisionOption(id="keep", label="Don't exile it")],
           resume={"step": "bluff_offer111f", "ctx": ctx, "e": e, "spell": spell.id}, source=src)
    return False


def resume_bluff(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context
    from app.rules.effects import continue_effects, exile

    if chosen not in (["exile"], ["keep"]):
        raise ActionError("Choose whether to exile the spell")
    ctx = d.resume["ctx"]
    context.refs(ctx)[d.resume["e"]["bind"]] = {"kind": "payment", "ok": chosen == ["exile"]}
    plan.note(f"{plan.name(d.player)} {'exiles' if chosen == ['exile'] else 'does not exile'} the spell", actor=d.player)
    if chosen == ["exile"] and plan.state.cards.get(d.resume["spell"]) is not None and plan.state.cards[d.resume["spell"]].zone == "stack":
        exile(plan, ctx, {"do": "exile", "who": "target"})
    continue_effects(plan, ctx)


PRIMITIVES = {"return_or_else111f": return_or_else, "bluff_offer111f": bluff_offer}
RESUME: dict[str, Any] = {"bluff_offer111f": resume_bluff}
