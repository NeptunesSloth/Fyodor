"""-- wave 110I -- exact Oracle wordings of single cards, read as a wording the grammar already reads (``_AS``) or built from parts of it.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
Researched against the Comprehensive Rules of 2026-09-25.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
Def = dict[str, Any]


def _won_last(d: Def) -> Def:
    """701.30d: the last instruction (the token's haste) happens only if you won the clash the trigger is about."""
    *head, last = d["effects"]
    return {**d, "effects": [*head, {"do": "only_if", "cond": {"clash_won100a": True}, "skip": 1}, last]}


# whole ability text -> the wording the grammar reads for it
_AS: dict[str, str] = {
    # Corrosion: "Artifacts destroyed this way" are the ones the destroy-each instruction destroyed ("They", 701.8c: can't be regenerated)
    "At the beginning of your upkeep, put a rust counter on each artifact target opponent controls. Then destroy each artifact with mana value less than "
    "or equal to the number of rust counters on it. Artifacts destroyed this way can't be regenerated.":
        "At the beginning of your upkeep, put a rust counter on each artifact target opponent controls. Then destroy each artifact with mana value less "
    "than or equal to the number of rust counters on it. They can't be regenerated.",
}


def _until_leaves(d: Def) -> Def:
    """The Moment: "It phases out until ~ leaves the battlefield" (610.3, 702.26a): the Oubliette lifetime packet, without its tap."""
    return {**d, "effects": [{"do": "phase_until_target110c", "untapped110i": True} if x.get("do") == "phase_out" else x for x in d["effects"]]}


def _lose_types(d: Def) -> Def:
    """Curse of Conformity: "lose all creature types" sets the creature types to none (205.1a, 613.1d layer 4), beside the layer 7b base P/T."""
    return {**d, "layered": True, "layer4": {"set_creature_types": []}}


def _bounce_gate(d: Def) -> Def:
    """Puppet Master: the payment is offered only if that card was returned to its owner's hand this way (a token or a card exiled instead isn't)."""
    first, *rest = d["effects"]
    return {**d, "effects": [{**first, "do": "bounce_gate110i", "skip": len(rest)}, *rest]}


def _attach_all(d: Def) -> Def:
    return {**d, "effects": [{"do": "attach_all110i"}]}


def _prevent_paid(d: Def) -> Def:
    """Errant Minion / Power Leak: the host's controller pays any amount of mana (118.3), then a prevention shield for that much (615.7) is made on
    them just before the Aura deals its 2, so damage-changing replacements (616.1) and the shield combine as the rules say."""
    (hit,) = d["effects"]
    pay = {"do": "optional_payment", "who": "event_player", "cost": "", "bind": "leak110i", "choose_x": {"max": None}}
    return {**d, "effects": [pay, {"do": "prevent", "who": "event_player", "n": {"paid_x": "leak110i"}}, hit]}


def _batch(d: Def) -> Def:
    """Bioessence Hydra: "one or more ... planeswalkers" is one trigger per batch of counter placements (603.2c) with their summed amount, not one per
    planeswalker (a replacement like Hardened Scales would add to each separate trigger's counters)."""
    return {**d, "cond": {**d["cond"], "aggregate": True}}


def _mirror(d: Def) -> Def:
    """Mirror of Fate: the up to seven face-up exiled cards are chosen as it resolves, not targeted (608.2d, 115.1), then the library is exiled
    (face up, 406.3) and the chosen cards go on top (401.4: their owner orders them)."""
    from app.rules import selectors

    key = selectors.parse("face-up card you own in exile").key()  # type: ignore[union-attr]
    pick = {"do": "player_chooses", "who": "you", "sel": key, "n": 7, "label": "exiled card", "zone": "exile", "upto": True, "optional": True, "as": "mof"}
    return {**d, "targets": [], "effects": [pick, {"do": "exile_library110i"}, {"do": "to_library", "who": "ref:mof", "place": "top"}]}


_POWER_LEAK = "At the beginning of the upkeep of enchanted {0}'s controller, that player may pay any amount of mana. This Aura deals 2 damage to that player. Prevent X of that damage, where X is the amount of mana that player paid this way."

# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    "{T}, Sacrifice this artifact: Choose up to seven face-up exiled cards you own. Exile all the cards from your library, then put the chosen cards on top of your library.":
        ("{T}, Sacrifice this artifact: Put up to seven target cards you own from exile on top of your library.", _mirror),
    "Whenever one or more loyalty counters are put on planeswalkers you control, put that many +1/+1 counters on this creature.":
        ("Whenever one or more loyalty counters are put on a planeswalker you control, put that many +1/+1 counters on this creature.", _batch),
    **{_POWER_LEAK.format(k): (f"At the beginning of the upkeep of enchanted {k}'s controller, this Aura deals 2 damage to that player.", _prevent_paid)
       for k in ("creature", "enchantment")},
    "Whenever an equipped creature you control other than Rhuk attacks or dies, you may attach all Equipment attached to that creature to Rhuk.":
        ("Whenever an equipped creature you control other than ~ attacks or dies, you may draw a card.", _attach_all),
    "When enchanted creature dies, return that card to its owner's hand. If that card is returned to its owner's hand this way, you may pay {U}{U}{U}. If you do, return this card to its owner's hand.":
        ("When enchanted creature dies, return that card to its owner's hand. You may pay {U}{U}{U}. If you do, return this card to its owner's hand.", _bounce_gate),
    "Nonlegendary creatures enchanted player controls have base power and toughness 3/3 and lose all creature types.":
        ("Nonlegendary creatures enchanted player controls have base power and toughness 3/3.", _lose_types),
    "{2}, {T}: Untap target creature you control. It phases out until The Moment leaves the battlefield.":
        ("{2}, {T}: Untap target creature you control. It phases out.", _until_leaves),
    "Whenever you clash, you may pay {1}. If you do, create a 3/1 red Elemental Shaman creature token. If you won, that token gains haste until end of turn.":
        ("Whenever you clash, you may pay {1}. If you do, create a 3/1 red Elemental Shaman creature token. That token gains haste until end of turn.", _won_last),
}


# a spell / mode body -> the wording the grammar reads for it
REWRITES: dict[str, str] = {}

# Survivor's Med Kit (RadAway): "loses all rad counters" is removing every rad counter the player has (122.1i, 728). The grammar's
# "Remove all rad counters from target player" only reads permanents' counters, so its first instruction is swapped for ``lose_rad110i``.
_RADAWAY = "Target player loses all rad counters. Sacrifice ~."


def parse(body: str) -> Any:
    from app.rules import scripts

    if body.strip() == _RADAWAY:
        parsed = scripts.parse_effects("Target player gets 1 rad counters. Sacrifice ~.")
        assert parsed is not None
        effects, target, optional = parsed
        return [{"do": "lose_rad110i", "who": "target"}, *effects[1:]], target, optional
    return scripts.parse_effects(same) if (same := REWRITES.get(body.strip())) is not None else None


def lose_rad(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    for pid in effects._players(plan, ctx, e["who"]):
        if (have := plan.state.players[pid].resources.get("rad", 0)) > 0:
            plan.do({"type": "resource", "player": pid, "key": "rad", "delta": -have}, actor=ctx["controller"])
    return True


def bounce_gate(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import effects

    cards = effects._cards(plan, ctx, e["who"])
    effects.bounce(plan, ctx, e)
    if not any(plan.state.cards[c].zone.endswith(":hand") for c in cards):
        del ctx["effects"][ctx["next"]:ctx["next"] + e["skip"]]  # the later instructions don't happen
    return True


def attach_all(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Rhuk: every Equipment attached to the event creature (603.10a: as it was just before it died) moves to the source (701.3a)."""
    from app.rules import attachments, context

    me = plan.state.cards.get(ctx.get("source_card") or "")
    if me is None or not me.zone.endswith(":battlefield") or plan.oid(me) != ctx.get("source_object"):
        return True
    for ref in context._object_refs(ctx, context.EVENT, was=True):
        here = context._same(plan, ref)
        snap = context.snapshot(plan, ref)
        ids = [c.id for c in plan.state.cards.values() if c.attached_to == here.id] if here is not None else list(snap.attached) if snap else []
        for cid in ids:
            gear = plan.state.cards.get(cid)
            if gear is not None and gear.zone.endswith(":battlefield") and "Equipment" in plan.ch(gear).subtypes:
                attachments.attach(plan, cid, me.id, ctx["controller"])
    return True


# friend or foe sides (app/rules/friend_foe.py): the acting player is "you" while the block runs (tempting.as_player)
SIDES: dict[str, list[Def]] = {
    # Regna's Sanction: a choice of their own (608.2d), then every other creature they control becomes tapped
    "chooses one untapped creature they control, then taps the rest": [
        {"do": "player_chooses", "who": "you", "sel": 'sel:{"tapped":false,"types":["Creature"]}', "n": 1, "label": "untapped creature", "as": "keep110i"},
        {"do": "bind_rest110i", "as": "rest110i"}, {"do": "tap", "who": "ref:rest110i"}],
    # Zndrsplt's Judgment: the friend chooses which creature they control to copy; the token is created under their control (111.2)
    "creates a token that's a copy of a creature they control": [
        {"do": "player_chooses", "who": "you", "sel": 'sel:{"types":["Creature"]}', "n": 1, "label": "creature", "as": "copy110i"},
        {"do": "token_copy", "n": 1, "who": "ref:copy110i"}],
}


def bind_rest(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Taps the rest": the creatures the acting player controls other than the one they chose."""
    from app.rules import context

    chosen = next((n for n in context.refs(ctx) if n.endswith("keep110i")), None)  # (spell lines rename their bindings: scripts.rename_bindings)
    keep = set(context.objects(plan, ctx, chosen)) if chosen else set()
    mine = [c.id for c in plan.state.cards.values() if c.zone == f"{ctx['controller']}:battlefield" and "Creature" in plan.ch(c).types and c.id not in keep]
    context.bind_objects(plan, ctx, e["as"], mine)
    return True


def exile_library(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.13 exile: every card of the controller's library moves to exile, face up."""
    pid = ctx["controller"]
    if cards := list(plan.state.zones.get(f"{pid}:library", [])):
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"}}, actor=pid)
    return True


PRIMITIVES = {"bind_rest110i": bind_rest, "exile_library110i": exile_library, "attach_all110i": attach_all, "lose_rad110i": lose_rad, "bounce_gate110i": bounce_gate}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    text = ability.text.strip()
    if (same := _AS.get(text)) is not None:
        return scripts.define(replace(ability, text=same), ch)
    built = _BUILD.get(text)
    if built is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)
