"""-- wave 110J -- exact Oracle wordings of single cards, built from parts of wordings the grammar already reads.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]

_FORESTS = "half the number of Forests you control"


def _aspect(d: Def) -> Def:
    """Aspect of Wolf: X (rounded down) is the power bonus, Y (rounded up) the toughness bonus; two sentences of one static (613.4c, 107.1a)."""
    from app.rules import statics

    toughness = statics.parse(f"Enchanted creature gets +0/+X, where X is {_FORESTS}, rounded up.")
    return {**d, "p": 0, "t": 0, "also": [toughness]} if toughness and "each" in d else d


# whole ability text -> (the wording the grammar reads, what to change in its definition)
_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    "Enchanted creature gets +X/+Y, where X is half the number of Forests you control, rounded down, and Y is half the number of Forests you control, rounded up.":
        (f"Enchanted creature gets +X/+0, where X is {_FORESTS}, rounded down.", _aspect),
}


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def _farmer(d: Def) -> Def:
    """Orcish Farmer: the land stays a Swamp until its own controller's next untap step (611.2a, 502.3) — the controller of the land, not of the Farmer."""
    until = [e for e in d["effects"] if e.get("do") == "until" and e.get("duration") == "next_turn"]
    return {**d, "effects": [{**e, "controller110j": True} if e in until else e for e in d["effects"]]} if len(until) == 1 else d


_BUILD["{T}: Target land becomes a Swamp until its controller's next untap step."] = (
    "{T}: Target land becomes a Swamp until your next turn.", _farmer)


def _cudgels(d: Def) -> Def:
    """Bronze Cudgels: X is the number of times the ability has resolved this turn, this resolution included (history.counting_resolutions)."""
    pumps = [e for e in d["effects"] if e.get("do") == "pump"]
    return {**d, "effects": [{**e, "p": {"ref_amount": "resolution"}} if e in pumps else e for e in d["effects"]]} if len(pumps) == 1 else d


_BUILD["{2}: Until end of turn, equipped creature gets +X/+0, where X is the number of times this ability has resolved this turn."] = (
    "{2}: Until end of turn, equipped creature gets +1/+0.", _cudgels)


def _all_attack(d: Def) -> Def:
    """Mob Mentality: the trigger waits for every non-Wall creature its controller has to be attacking (triggers.py all110j)."""
    return {**d, "cond": {**d["cond"], "all110j": True}} if d.get("cond", {}).get("event") == "you_attack" else d


_BUILD["Whenever all non-Wall creatures you control attack, enchanted creature gets +X/+0 until end of turn, where X is the number of attacking creatures."] = (
    "Whenever you attack with one or more non-Wall creatures, enchanted creature gets +X/+0 until end of turn, where X is the number of attacking creatures.",
    _all_attack)


_SPORES = ('Whenever this creature blocks a creature, put four fungus counters on that creature. The creature gains "This creature doesn\'t untap during your '
           'untap step if it has a fungus counter on it" and "At the beginning of your upkeep, remove a fungus counter from this creature."')
# two grants of one clause, read as two sentences (both last for good, 611.2a)
_BUILD[_SPORES] = (
    'Whenever this creature blocks a creature, put four fungus counters on that creature. That creature gains "This creature doesn\'t untap during your '
    'untap step if it has a fungus counter on it." That creature gains "At the beginning of your upkeep, remove a fungus counter from this creature."',
    lambda d: d)


def _loki(d: Def) -> Def:
    """Loki, God of Lies: "that creature" is the spell's single target (115.9c), not a target of the trigger; its control, untap and haste follow (611.2b)."""
    from app.rules import token_copy_sources

    sel = d.get("target", {}).get("what")
    if not (sel and d.get("cond", {}).get("targets") == f"only_one:{sel}"):
        return d
    ref = f"ref:{token_copy_sources.CHOSEN}"
    effects = [{**e, "who": ref} if e.get("who") == "target" else e for e in d["effects"]]
    return {**{k: v for k, v in d.items() if k != "target"}, "effects": [{"do": "select_copy_spell_target", "selector": sel}, *effects]}


_BUILD["Whenever you cast a spell that targets only a single creature, gain control of that creature until end of turn. If it's your turn, untap that creature and it gains haste until end of turn."] = (
    "Whenever you cast a spell that targets only a single creature, gain control of target creature until end of turn. If it's your turn, untap that creature and it gains haste until end of turn.",
    _loki)


def _love(d: Def) -> Def:
    """Love on the Battlefield: exactly two attackers (508.1, 603.2); the damage watch is for the two declared attackers (a creature put onto the battlefield attacking was not declared, 508.4)."""
    from app.rules import selectors

    base = selectors.parse("attacking creature")
    declared = None if base is None else replace(base, extras=(*base.extras, "attacked_this_turn"))
    watches = [e for e in d["effects"] if e.get("do") == "delayed" and e["when"]["cond"].get("sel")]
    if declared is None or d["cond"].get("min_attackers") != 2 or len(watches) != 1:
        raise ValueError("Love on the Battlefield: unexpected native shape")
    watch = watches[0]
    cond = {**watch["when"]["cond"], "sel": declared.key()}
    return {**d, "cond": {**d["cond"], "max_attackers110j": 2},
            "effects": [{**e, "when": {**e["when"], "cond": cond}} if e is watch else e for e in d["effects"]]}


_BUILD["Whenever you attack with exactly two creatures, those creatures gain first strike until end of turn, then draw a card. Whenever either of those creatures deals combat damage to a player this combat, put a +1/+1 counter on it."] = (
    "Whenever you attack with two or more creatures, attacking creatures gain first strike until end of turn, then draw a card. Whenever an attacking creature deals combat damage to a player this combat, put a +1/+1 counter on it.",
    _love)


def _scavenger(d: Def) -> Def:
    """Silumgar Scavenger: the haste goes to the Scavenger only if it exploited the creature that died (702.110b; conditions.py exploited110j)."""
    return {**d, "effects": [*d["effects"], {"do": "only_if", "cond": {"exploited110j": True}, "skip": 1}, {"do": "grant", "who": "self", "keywords": ["haste"]}]}


_BUILD["Whenever another creature you control dies, put a +1/+1 counter on this creature. It gains haste until end of turn if it exploited that creature."] = (
    "Whenever another creature you control dies, put a +1/+1 counter on this creature.", _scavenger)


def _reattach(d: Def) -> Def:
    """Kudzu, Steam Vines: after the land is destroyed, its controller may choose any land; the Aura (still on the battlefield until state-based actions, 704.3) attaches to it (303.4f)."""
    from app.rules.nontarget_creature_choices import key

    if [e.get("do") for e in d["effects"]][:1] != ["destroy"]:
        raise ValueError("Kudzu/Steam Vines: unexpected native shape")
    d = {**d, "effects": [{**d["effects"][0], "as": "e0"}, *d["effects"][1:]]}
    pick = {"do": "player_chooses", "who": "ref:e0.controller", "sel": key("land"), "n": 1, "label": "land", "any": True, "upto": True, "optional": True, "as": "kz110j"}
    return {**d, "effects": [*d["effects"], pick, {"do": "attach_to", "src": "self", "who": "ref:kz110j"}]}


_BUILD["When enchanted land becomes tapped, destroy it. That land's controller may attach this Aura to a land of their choice."] = (
    "When enchanted land becomes tapped, destroy it.", _reattach)
_BUILD["When enchanted land becomes tapped, destroy it and this Aura deals 1 damage to that land's controller. That player attaches this Aura to a land of their choice."] = (
    "When enchanted land becomes tapped, destroy it and this Aura deals 1 damage to that land's controller.", _reattach)


def _paid_cu(d: Def) -> Def:
    """Hibernation's End: not an upkeep trigger; the paid_cumulative110j step starts it once the cumulative upkeep was paid (702.24a)."""
    return {**d, "trigger": PAID_CU} if d.get("trigger") == "upkeep_you" else d


PAID_CU = "paid_cu110j"
_BUILD["Whenever you pay this enchantment's cumulative upkeep, you may search your library for a creature card with mana value equal to the number of age counters on this enchantment, put it onto the battlefield, then shuffle."] = (
    "At the beginning of your upkeep, you may search your library for a creature card with mana value equal to the number of age counters on this enchantment, put it onto the battlefield, then shuffle.",
    _paid_cu)


def paid_cumulative(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Last step of a cumulative upkeep trigger: the permanent is still here only if it was paid (otherwise it was sacrificed, 702.24a), so its
    "Whenever you pay this permanent's cumulative upkeep" abilities trigger now (603.2)."""
    from app.rules import triggers

    src = plan.state.cards.get(ctx.get("source_card", ""))
    if src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
        for card, ch, i, d in triggers._watchers(plan, PAID_CU):
            if card.id == src.id:
                triggers._add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=i, definition=d)
    return True


def _ruin(d: Def) -> Def:
    """Rumbling Ruin: the "can't block" group is read with a power bound counted as the trigger resolves (611.2c: rule effect, group not locked)."""
    return {**d, "effects": [{**e, "do": "ruin110j"} if e.get("do") == "restrict" else e for e in d["effects"]]}


_BUILD["When this creature enters, count the number of +1/+1 counters on creatures you control. Creatures your opponents control with power less than or equal to that number can't block this turn."] = (
    "When this creature enters, creatures your opponents control with power 0 or less can't block this turn.", _ruin)


def ruin(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.rules import effects, selectors, values

    n = values.evaluate(plan, ctx, {"counters_among": "+1/+1", "of": selectors.Selector(types=("Creature",), controller="you").key()})
    who = e["who"].replace('["power","<=",0]', f'["power","<=",{n}]')
    return bool(effects.restrict(plan, ctx, {**e, "do": "restrict", "who": who}))


def _dragon(d: Def) -> Def:
    """Quicksilver Dragon: any spell may be targeted; only as the ability resolves is it checked that the spell's only target is this creature."""
    return {**d, "target": {**d["target"], "what": d["target"]["what"].replace('"extras":["single_target"],', "")},
            "effects": [{**e, "do": "dragon110j"} for e in d["effects"]]}


_BUILD["{U}: If target spell has only one target and that target is this creature, change that spell's target to another creature."] = (
    "{U}: Change the target of target spell with a single target. The new target must be a creature.", _dragon)


def dragon(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """115.9c, 115.7a: with one different target that is this creature, it becomes another legal creature (the new target differs from the old one)."""
    from app.rules import selectors, stack_interaction

    for sid in effects_stack_targets(plan, ctx, e):
        card = plan.state.cards.get(sid)
        if card is not None and selectors.targets_only(plan, card, "self", ctx["controller"], ctx.get("source_card")):
            return bool(stack_interaction.change_target(plan, ctx, {**e, "do": "change_target"}))
    return True


def effects_stack_targets(plan: Any, ctx: Any, e: dict[str, Any]) -> list[str]:
    from app.rules.effects import _stack_targets

    return list(_stack_targets(plan, ctx, e))


PRIMITIVES = {"paid_cumulative110j": paid_cumulative, "ruin110j": ruin, "dragon110j": dragon}
