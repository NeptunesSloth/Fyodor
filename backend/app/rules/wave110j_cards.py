"""-- wave 110J -- exact Oracle wordings of single cards, built from parts of wordings the grammar already reads.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from app.rules import oracle

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


def _earthbind_trigger(d: Def) -> Def:
    return {**d, "effects": [*d["effects"], {"do": "mark110j"}]}


def _earthbind_static(d: Def) -> Def:
    return {**d, "conditions": [*d.get("conditions", []), {"static": "marked110j"}]}


# Earthbind (oracle.EARTHBIND splits the line in two): the trigger marks the Aura, the static applies only to a marked one (611.3a)
_BUILD[oracle.EARTHBIND] = (
    "When this Aura enters, if enchanted creature has flying, this Aura deals 2 damage to that creature.", _earthbind_trigger)
_BUILD["As long as this Aura gained that ability, enchanted creature loses flying."] = ("Enchanted creature loses flying.", _earthbind_static)


def _splinter(d: Def) -> Def:
    """Splintering Wind: the delayed trigger's damage comes from the token itself ("it deals", last known information, 608.2h), not from the enchantment."""
    return {**d, "effects": [{**e, "src": "ref:e1"} if str(e.get("do")) == "deferred:damage" else e for e in d["effects"]]}


_BUILD['{2}{G}: This enchantment deals 1 damage to target creature. Create a 1/1 green Splinter creature token. It has flying and "Cumulative upkeep {G}." When it leaves the battlefield, it deals 1 damage to you and each creature you control.'] = (
    '{2}{G}: This enchantment deals 1 damage to target creature. Create a 1/1 green Splinter creature token with flying and "Cumulative upkeep {G}." '
    'When it leaves the battlefield, this enchantment deals 1 damage to you and each creature you control.', _splinter)

GAINED = "Gained ability"


def mark(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """"This Aura gains …": remember it for this object, if it is still on the battlefield (the static reads the mark)."""
    card = plan.state.cards.get(ctx.get("source_card", ""))
    if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == ctx.get("source_object"):
        plan.do({"type": "set_choice", "card_id": card.id, "key": GAINED, "value": "Yes"}, actor=ctx["controller"])  # (a zone change clears it: ops.py, 400.7)
    return True


PRIMITIVES = {"paid_cumulative110j": paid_cumulative, "ruin110j": ruin, "dragon110j": dragon, "mark110j": mark}


# Razor Boomerang: "It" is the Equipment (the ruling: the Equipment deals the damage, 120.3), so name it; the grant binds the name to its granter
_BOOMERANG = 'Equipped creature has "{T}, Unattach Razor Boomerang: %s Return Razor Boomerang to its owner\'s hand."'
_BUILD[_BOOMERANG % "It deals 1 damage to any target."] = (_BOOMERANG % "Razor Boomerang deals 1 damage to any target.", lambda d: d)


def note_battle_attacks(plan: Any, attackers: Any) -> None:
    """310.5, 508.1: remember the attackers declared against a battle (not a player, not a planeswalker) for "attacked a battle this turn"."""
    from app.game.rules_state import turn_log_now

    log = turn_log_now(plan.state)
    for x in attackers:
        t = plan.state.cards.get(x.target)
        if log is not None and t is not None and "Battle" in plan.ch(t).types and (o := plan.oid(plan.state.cards[x.card_id])) not in log.attacked_battle110j:
            log.attacked_battle110j.append(o)

ENGAGED = "Engaged110j"


def note_engaged(plan: Any, card_ids: Any) -> None:
    """508.1, 509.1g: remember (on the object, 400.7) the turn it attacked, blocked or was blocked in, for "since your last upkeep"."""
    for cid in dict.fromkeys(card_ids):
        plan.do({"type": "set_choice", "card_id": cid, "key": ENGAGED, "value": str(plan.state.turn.number)}, actor=plan.actor)


def engaged_since_upkeep(plan: Any, ctx: Any, ids: set[str]) -> bool:
    """Did one of these objects attack, block or become blocked since its controller's last upkeep? That upkeep began in that controller's previous
    own turn (events of that turn follow its upkeep step, 503.1); without a known previous turn, since the game began."""
    done = plan.rules.completed_own_turns.get(ctx["controller"])
    since = done.turn if done is not None else 0
    return any(int(c.choices.get(ENGAGED, "-1")) >= since for c in plan.state.cards.values() if plan.oid(c) in ids)


def _since_upkeep(d: Def) -> Def:
    """Wiitigo, Shape of the Wiitigo: the "this turn" history read in the native wording is swapped for the since-last-upkeep one."""
    gate = d["effects"][0]
    return {**d, "effects": [{**gate, "cond": {**gate["cond"], "what": "engaged110j"}}, *d["effects"][1:]]}


_UP = "At the beginning of your upkeep, put a +1/+1 counter on %s if it %s since your last upkeep. Otherwise, remove a +1/+1 counter from it."
_NATIVE = "At the beginning of your upkeep, put a +1/+1 counter on %s if %s attacked or blocked this turn. Otherwise, remove a +1/+1 counter from %s."
_BUILD[_UP % ("this creature", "has blocked or been blocked")] = (_NATIVE % ("~", "~", "~"), _since_upkeep)
_BUILD[_UP % ("enchanted creature", "attacked or blocked")] = (_NATIVE % ("enchanted creature", "it", "it"), _since_upkeep)


# -- spell/ability bodies (exact text -> a wording the grammar reads) --
REWRITES: dict[str, str] = {
    # Simic Guildmage: "with the same controller" = "that player" of the first target (player_relative._names_player; Bioshift)
    "Move a +1/+1 counter from target creature onto another target creature with the same controller.":
        "Move a +1/+1 counter from target creature onto another target creature that player controls.",
}


def parse(body: str) -> Any:
    from app.rules import scripts

    return scripts.parse_effects(same) if (same := REWRITES.get(body.strip())) is not None else None


def _guildmage(d: Def) -> Def:
    """Simic Guildmage: the new host is another permanent controlled by the controller of the Aura's current host (permanent_exchanges, 701.3)."""
    first, second = d["targets"]
    return {**d, "targets": [first, {**second, "of": 0, "relative_quality": {"kind": "hostctl110j"}}]}


_BUILD["{1}{U}: Attach target Aura attached to a permanent to another permanent with the same controller."] = (
    "{1}{U}: Attach target Aura attached to a permanent to target permanent.", _guildmage)
