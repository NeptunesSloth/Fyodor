"""-- wave 110J -- exact Oracle wordings of single cards, built from parts of wordings the grammar already reads.

Each entry matches one whole ability's Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

import re
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


_CAP = re.compile(r"(?P<name>\w+) can't have more than (?P<n>one|two|three|four|five|six|seven|eight|nine|ten) (?P<kind>[a-z]+) counters on it\.?")
_NUMS = {w: i for i, w in enumerate(["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"])}


def excess(plan: Any) -> list[tuple[Any, str, int]]:
    """704.5r: "~ can't have more than N X counters on it" (Rasputin Dreamweaver) is a state-based action, so every way
    counters arrive (proliferate, enters with, moved, put) is trimmed to N the same way."""
    from app.rules import cast_limits

    return [(src, d["counter"], over) for src, d in cast_limits._statics(plan.state, plan.info, "counter_cap110j")
            if src.zone.endswith(":battlefield") and (over := src.counters.get(d["counter"], 0) - d["n"]) > 0]


def counter_key(c: Any, ev: dict[str, Any]) -> str:
    return f"counters110j:{c.id}:{ev['target']}"


def counters_left(plan: Any, sim: dict[str, Any], c: Any, ev: dict[str, Any]) -> int:
    """Rock Hydra: the counters still on the recipient that this damage batch hasn't used to prevent damage yet (the table changes after the batch, 615.5)."""
    card = plan.state.cards.get(ev["target"])
    return int(sim.get("shields", {}).get(counter_key(c, ev), card.counters.get(c.op["counter"], 0) if card is not None else 0))


def caster(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> str:
    """Swindler's Scheme: "that opponent may cast the revealed card" — whoever cast the spell that triggered it (permissions.free_cast)."""
    if e.get("caster") == "event":
        found = values_object(plan, ctx)
        if found is not None:
            return str(found[0].controller)
    return str(ctx["controller"])


def values_object(plan: Any, ctx: dict[str, Any]) -> tuple[Any, Any] | None:
    from app.rules import values

    return values._object(plan, ctx, "event")


def holds(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    """Rasputin Dreamweaver: the source was untapped on the battlefield as this turn began (500.1, before the untap step). Swindler's Scheme: see below."""
    if cond.get("w110j") == "unattached_ninja":  # Shuriken: the cost unattached the Equipment from a Ninja (701.3d, 205.3)
        sid = ctx.get("stack_id") or ctx.get("source_card")
        record = plan.rules.payments.get(plan.rules.object_id(sid)) if sid else None
        return record is not None and record.unattached_ninja110j
    if cond.get("w110j") == "shares_event_type":  # Swindler's Scheme: 205.2, the revealed card and the spell that triggered it
        from app.rules import values

        card, spell = values._object(plan, ctx, cond["object"]), values._object(plan, ctx, "event")
        return card is not None and spell is not None and bool(set(card[1].types) & set(spell[1].types))
    return ctx.get("source_object") in plan.rules.began_untapped110j


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts


    if (cap := _CAP.fullmatch(ability.text.strip())) is not None and ch.name.startswith(cap["name"]):  # (the short name)
        return {"kind": "static", "static": "counter_cap110j", "counter": cap["kind"], "n": _NUMS[cap["n"]], "effects": []}
    if ability.text.strip() == _WEB1:  # Magnetic Web: a source-less conditional attack requirement (508.1d), score in combat_conditional_requirements67
        from app.rules import combat_conditional_requirements67, selectors, statics

        return statics._definition(selectors.Selector(types=("Creature",), extras=("counter:magnet",)).key(), None, [],
                                   rules=[combat_conditional_requirements67.PREFIX + "@src:magnet110j"])
    if ability.text.strip() == _TAKKLE_GAIN:  # Takklemaggot's granted ability: the chosen player is the one recorded as it returned (read by triggers._whose_step)
        return {"kind": "triggered", "trigger": "step:upkeep:chosen_player", "effects": [{"do": "damage", "who": "event_player", "n": 1}], "optional": False, "target": None}
    if ability.text.strip() == _EQUINOX:
        return {"kind": "activated", "cost": "{T}", "effects": [{"do": "equinox110j"}], "target": {"what": "spell"}}
    if ability.text.strip() == _CURSE_IGNORE:
        native = scripts.define(replace(ability, text="Sacrifice a permanent: Draw a card."), ch)
        return None if native is None else {**native, "effects": [{"do": "ignore110j"}]}
    if ability.text.strip() == _SPLICER:
        return _splicer(ability, ch)
    if ability.text.strip() == _ES:
        return _shapeshifter()
    if (shuriken := _SHURIKEN.fullmatch(ability.text.strip())) is not None:
        return _shuriken(shuriken["oid"], ability, ch)
    if (blight := _BLIGHT.fullmatch(ability.text.strip())) is not None:
        return _nettlevine(blight["oid"], ability, ch)
    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def _farmer(d: Def) -> Def:
    """Orcish Farmer: the land stays a Swamp until its own controller's next untap step (611.2a, 502.3) — the controller of the land, not of the Farmer."""
    until = [e for e in d["effects"] if e.get("do") == "until" and e.get("duration") == "next_turn"]
    return {**d, "effects": [{**e, "controller110j": True} if e in until else e for e in d["effects"]]} if len(until) == 1 else d


def _hydra(d: Def) -> Def:
    """Rock Hydra: for each 1 damage, a counter is removed and that 1 damage prevented — only as much is prevented as there are counters (op prevent_counters110j)."""
    op = d.get("op") or {}
    if d.get("event") != "damage" or op.get("do") != "prevent_all" or not op.get("rider"):
        raise ValueError("Rock Hydra: unexpected native shape")
    return {**d, "op": {**op, "do": "prevent_counters110j", "counter": "+1/+1"}}


_BUILD["For each 1 damage that would be dealt to this creature, if it has a +1/+1 counter on it, remove a +1/+1 counter from it and prevent that 1 damage."] = (
    "If this creature would be dealt damage while it has a +1/+1 counter on it, prevent that damage and remove that many +1/+1 counters from it.", _hydra)
_BUILD["{4}, {T}: An opponent chooses target creature they control. Create a token that's a copy of that creature. That token gains haste until end of turn. Exile the token at the beginning of the next end step. Activate only as a sorcery."] = (
    "{4}, {T}: Create a token that's a copy of target creature. That token gains haste until end of turn. Exile the token at the beginning of the next end step. Activate only as a sorcery.",
    lambda d: {**d, "delegated_target": "opponent", "delegated_controls110d": True})  # Echo Chamber: the opponent announces the target among their own creatures (wave 110D, Preacher)
def _keeper(d: Def) -> Def:
    """Keeper of the Dead: the opponent is chosen as the ability is activated (601.2c) among those with at least two fewer creature cards in their graveyard."""
    groups = d.get("targets") or []
    if not groups or groups[0].get("what") != "opponent":
        raise ValueError("Keeper of the Dead: unexpected native shape")
    return {**d, "targets": [{**groups[0], "what": "opponent_as:gy2_110j"}, *groups[1:]]}


_BUILD["{B}, {T}: Choose target opponent who has at least two fewer creature cards in their graveyard than you do as you activate this ability. Destroy target nonblack creature that player controls."] = (
    "{B}, {T}: Choose target opponent. Destroy target nonblack creature that player controls.", _keeper)
def _cycle(d: Def) -> Def:
    """Cycle of Life: the target is a creature the controller cast this turn (targets.legal_targets cast_creature110j)."""
    if not str((d.get("target") or {}).get("what")).startswith("sel:") or d.get("targets"):
        raise ValueError("Cycle of Life: unexpected native shape")
    return {**d, "target": {**d["target"], "what": "cast_creature110j"}}


_BUILD["Return this enchantment to its owner's hand: Target creature you cast this turn has base power and toughness 0/1 until your next upkeep. At the beginning of your next upkeep, put a +1/+1 counter on that creature."] = (
    "Return this enchantment to its owner's hand: Target creature you control has base power and toughness 0/1 until your next upkeep. At the beginning of your next upkeep, put a +1/+1 counter on that creature.", _cycle)
_BUILD["Whenever Agent Maria Hill becomes tapped to pay a teamwork cost, put a +1/+1 counter on her and draw a card."] = (
    "Whenever this creature becomes tapped, put a +1/+1 counter on this creature and draw a card.",
    lambda d: {**d, "cond": {"event": "teamwork_tapped110j", "subject": "self"}})
_BUILD["At the beginning of your upkeep, if Rasputin started the turn untapped, put a dream counter on it."] = (
    "At the beginning of your upkeep, put a dream counter on this creature.", lambda d: {**d, "if": {"w110j": "began_untapped"}})
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
    from app.rules import triggers, wave110i_cards

    src = plan.state.cards.get(ctx.get("source_card", ""))
    if src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
        for card, ch, i, d in triggers._watchers(plan, PAID_CU):
            if card.id == src.id:
                triggers._add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=i, definition=wave110i_cards.cu_fill(plan, ctx, d))  # (wave 110I: the mana spent)
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


def mask(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Jester's Mask: the target player puts their hand on top of their library (their order: the library is shuffled at the end, so it can't matter),
    then the activator searches that library for that many cards (701.23a) and the player puts them into their hand, then shuffles (701.24)."""
    from app.game.state import zone_key
    from app.rules import effects, selectors

    for pid in effects._players(plan, ctx, e["who"]):
        hand = list(plan.state.zones.get(zone_key(pid, "hand"), []))
        for cid in hand:
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": pid, "zone": "library"}, "position": "top"}, actor=pid)
        sel = selectors.parse("card in your library")
        assert sel is not None
        search = {"do": "search", "who": "you", "library": "target", "sel": sel.key(), "label": "cards", "max": len(hand), "to": "hand"}
        at = ctx["next"]
        ctx["effects"] = [*ctx["effects"][:at], search, *ctx["effects"][at:]]
    return True


PRIMITIVES = {"mask110j": mask, "paid_cumulative110j": paid_cumulative, "ruin110j": ruin, "dragon110j": dragon, "mark110j": mark}


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


_BOUND = ("Sacrifice a creature. Return up to X cards from your graveyard to your hand, where X is the number of colors that creature was. "
          "Exile this card.")


_PRANCE = ("Target creature you don't control blocks target creature you control with a power and toughness sticker on it other than ~ "
           "this turn if able.")


def parse(body: str) -> Any:
    from app.rules import scripts

    if body.strip() == _BOUND:  # Bound: X = colors of the sacrificed creature as it last existed (608.2h)
        got = scripts.parse_effects("Sacrifice a creature. Return up to two cards from your graveyard to your hand. Exile ~.")
        if got is not None:
            got[0][0]["as"] = "e0"
            got[0][1]["n"] = {"colors": "ref:e0"}
        return got
    if body.strip() == _PRANCE:  # Lineprancers: the second target is "other than ~" (the stickered creature must not be the source)
        got = scripts.parse_effects(_PRANCE.replace(" other than ~", ""))
        if got is not None:
            from dataclasses import replace

            from app.rules import selectors

            t = got[1][1]
            t["what"] = replace(selectors.from_key(t["what"]), other=True).key()
        return got
    return scripts.parse_effects(same) if (same := REWRITES.get(body.strip())) is not None else None


def _guildmage(d: Def) -> Def:
    """Simic Guildmage: the new host is another permanent controlled by the controller of the Aura's current host (permanent_exchanges, 701.3)."""
    first, second = d["targets"]
    return {**d, "targets": [first, {**second, "of": 0, "relative_quality": {"kind": "hostctl110j"}}]}


_BUILD["{1}{U}: Attach target Aura attached to a permanent to another permanent with the same controller."] = (
    "{1}{U}: Attach target Aura attached to a permanent to target permanent.", _guildmage)


def _mask(d: Def) -> Def:
    return {**d, "effects": [{"do": "mask110j", "who": "target"}]}


_BUILD["{1}, {T}, Sacrifice this artifact: Target opponent puts the cards from their hand on top of their library. Search that player's library for that many cards. That player puts those cards into their hand, then shuffles."] = (
    "{1}, {T}, Sacrifice this artifact: Target opponent discards a card.", _mask)


def entered_transformed(plan: Any, info: dict[str, Any]) -> bool:
    """712.14a, 702.145b: the permanent of an "enter" fact came onto the battlefield back face up. A transformation (701.28) leaves a "transformed" event
    on its object; a daybound permanent that was flipped as it entered (702.145b) leaves none, so it counts as entering transformed."""
    oid, log = info.get("oid"), plan.rules.turn_log
    entry = next((x for x in reversed(log.entered) if x.object_id == oid), None) if oid and log is not None else None
    card = plan.state.cards.get(entry.card) if entry is not None else None
    return (card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == oid and card.face == 1
            and (plan.info.get(card.card_id) or {}).get("layout") == "transform"  # 712.14a: a modal DFC's back face (712.4) never "transforms"
            and not any(e.kind == "designation" and e.counter == "transformed" and e.object_id == oid for e in plan.rules.events))


def _towashi(d: Def) -> Def:
    from app.rules import events

    entered = events._parse("a permanent you control enters transformed")
    assert entered is not None
    return {**d, "cond": {"event": "either", "conds": [d["cond"], entered]}}


_BUILD["Whenever a permanent you control transforms or a permanent you control enters transformed, you may draw a card. Do this only once each turn."] = (
    "Whenever a permanent you control transforms, you may draw a card. Do this only once each turn.", _towashi)


# All Hallow's Eve: the spell exiles itself with two scream counters (the instruction moves the resolving spell, so it isn't put into a graveyard, 608.2n);
# each of its owner's upkeeps, while it is exiled with a scream counter (an ability of the exiled card, as for suspend), it loses one, and with none left
# it goes to the graveyard and every graveyard's creatures return (the step trigger of an exiled card: triggers.at_step_generic, exiled_step)
SCREAM = "scream"


def scream_exile(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    card = plan.state.cards.get(ctx.get("source_card", ""))
    if card is None or card.zone != "stack":
        return True
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "exile"}}, actor=ctx["controller"])
    plan.do({"type": "counter", "card_ids": [card.id], "kind": SCREAM, "delta": 2}, actor=ctx["controller"])
    return True


def scream_tick(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    """Intervening "if" (603.4): checked again as it resolves; no counter, or no longer exiled: nothing happens."""
    card = plan.state.cards.get(ctx.get("source_card", ""))
    if card is None or not card.zone.endswith(":exile") or plan.oid(card) != ctx.get("source_object") or card.counters.get(SCREAM, 0) < 1:
        ctx["next"] = len(ctx["effects"])
        return True
    plan.do({"type": "counter", "card_ids": [card.id], "kind": SCREAM, "delta": -1}, actor=ctx["controller"])
    if plan.state.cards[card.id].counters.get(SCREAM, 0) > 0:
        ctx["next"] = len(ctx["effects"])
        return True
    plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "graveyard"}}, actor=ctx["controller"])
    return True


PRIMITIVES.update({"scream_exile110j": scream_exile, "scream_tick110j": scream_tick})

_BUILD["Exile All Hallow's Eve with two scream counters on it."] = ("Draw a card.", lambda d: {**d, "effects": [{"do": "scream_exile110j"}]})
_BUILD["At the beginning of your upkeep, if this card is exiled with a scream counter on it, remove a scream counter from it. If there are no more scream counters on it, put it into your graveyard and each player returns all creature cards from their graveyard to the battlefield."] = (
    "At the beginning of your upkeep, return all creature cards from all graveyards to the battlefield under their owners' control.",
    lambda d: {**d, "trigger": "step:upkeep:you", "exiled_step": True, "if": {"value": {"counters": SCREAM, "on": "self"}, "op": ">=", "n": 1},
               "effects": [{"do": "scream_tick110j"}, *d["effects"]]})


def _livio_exile(d: Def) -> Def:
    """The target creature's controller decides (608.2d): a yes/no question to them, then the exile with the counter."""
    return {**d, "effects": [{"do": "optional_payment", "who": "tp:0", "ask": "Exile it with an aegis counter on it?", "cost": "", "bind": "aegis110j"},
                             {"do": "only_if", "cond": {"succeeded": "aegis110j"}, "skip": 2}, *d["effects"]]}


_BUILD["{1}{W}: Choose another target creature. Its controller may exile it with an aegis counter on it."] = (
    "{1}{W}: Exile another target creature. Put an aegis counter on it.", _livio_exile)


def _livio_return(d: Def) -> Def:
    from app.rules import selectors

    sel = selectors.parse("card in exile with an aegis counter on it")
    assert sel is not None
    return {**d, "effects": [{**e, "who": sel.key()} if e.get("do") == "return_card" else e for e in d["effects"]]}


_BUILD["{2}{W}, {T}: Return all exiled cards with aegis counters on them to the battlefield under their owners' control."] = (
    "{2}{W}, {T}: Return all cards from exile to the battlefield under their owners' control.", _livio_return)


_READING: set[str] = set()


def has_keyword(plan: Any, source: Any, keyword: str) -> bool:
    """Manor Gargoyle: "as long as it has defender" reads the permanent's own abilities while the static is being applied. Read them as if
    that static were off (613.8: it adds indestructible, which cannot change whether it has defender); the guard stops the loop."""
    if source.id in _READING:
        return False
    _READING.add(source.id)
    try:
        return keyword in plan.ch(source).keywords
    finally:
        _READING.discard(source.id)


_ES = "As long as an opponent controls a creature with flying not named Escaped Shapeshifter, this creature has flying. The same is true for first strike, trample, and protection from any color."


def opponent_has(plan: Any, source: Any, controller: str, keyword: str) -> bool:
    """Escaped Shapeshifter: an opponent controls a creature not named Escaped Shapeshifter with the keyword; "protection:R" is protection from that color
    (702.16: read by testing the creature's protection qualities against a bare object of that color)."""
    from app.rules import protection

    if source.id in _READING:  # (two of them: each reads the other, which is named like it and so does not count — stop the loop)
        return False
    _READING.add(source.id)
    try:
        for c in plan.state.cards.values():
            if c.zone.endswith(":battlefield") and c.controller != controller and c.controller in plan.live() and c.name != source.name:
                have = plan.ch(c)
                if not have.is_creature or have.name == source.name:
                    continue
                if keyword.startswith("protection:"):
                    bare = replace(have, colors=frozenset({keyword[-1]}), types=frozenset(), subtypes=frozenset(), supertypes=frozenset(), name="")
                    if protection.protected_from(have, bare):
                        return True
                elif keyword in have.keywords:
                    return True
        return False
    finally:
        _READING.discard(source.id)


def _shapeshifter() -> Def:
    from app.rules import statics

    def part(**kw: Any) -> Def:
        return statics._definition("self", None, [{"static": "opp_keyword110j", "keyword": kw.pop("when")}], **kw)

    first = part(when="flying", keywords=["flying"])
    colors = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}
    return {**first, "also": [part(when="first strike", keywords=["first strike"]), part(when="trample", keywords=["trample"]),
                              *(part(when=f"protection:{c}", grants=[f"Protection from {n}"]) for c, n in colors.items())]}


_BUILD["Whenever an opponent casts a spell from their hand, you may reveal the top card of your library. If it shares a card type with that spell, counter that spell and that opponent may cast the revealed card without paying its mana cost."] = (
    "Whenever an opponent casts a spell from their hand, you may reveal the top card of your library. If it's a creature card, counter that spell.", lambda d: _scheme(d))


def _scheme(d: Def) -> Def:
    """Swindler's Scheme: the revealed card shares a card type with the spell (205.2, conditions "w110j": shares_event_type); the opponent who cast it may then
    cast the revealed card for free (permissions.free_cast caster "event")."""
    fx = d["effects"]
    gate = next((i for i, e in enumerate(fx) if e.get("do") == "only_if"), None)
    if gate is None or fx[gate]["cond"].get("object") != "ref:e0" or fx[gate]["skip"] != 1 or gate + 2 != len(fx):
        raise ValueError("Swindler's Scheme: unexpected native shape")
    cond = {"w110j": "shares_event_type", "object": "ref:e0"}
    fx[gate]["cond"] = cond
    fx += [{"do": "only_if", "cond": cond, "skip": 1},
           {"do": "free_cast", "zone": "looked", "filter": None, "mv": None, "optional": True, "caster": "event"}]
    return d


_BUILD["{U}, Sacrifice this creature: Turn all cards exiled with this creature face up. Counter all spells with those names."] = (
    "{U}, Sacrifice this creature: Draw a card.",
    lambda d: {**d, "effects": [{"do": "turn_up_linked100g", "who": "exiled_with", "as": "grimoire110j"}, {"do": "counter_names110j", "who": "exiled_with"}]})


def counter_names(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Grimoire Thief: 701.6 counter every spell (any controller) with the name of a card exiled with this creature (607.2a; the cards are face up now)."""
    from app.rules import effects

    names = {plan.state.cards[c].name for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":exile")}
    for sid in list(plan.state.zones.get("stack", ())):
        card = plan.state.cards.get(sid)
        if card is not None and card.ability is None and card.name in names:
            effects.counter_object(plan, sid, ctx["controller"], source=ctx.get("source_card"))
    return True


PRIMITIVES["counter_names110j"] = counter_names


# -- Turf War (wave 110J) -- 613.1b control change; the creature's controller (not Turf War's) chooses the land (608.2d, "of their choice"), 701.26 untap
_TURF = ("Whenever a creature deals combat damage to a player, if that player controls one or more lands with contested counters on them, "
         "that creature's controller gains control of one of those lands of their choice and untaps it.")
_BUILD[_TURF] = ("Whenever a creature deals combat damage to a player, if that player controls a land with a contested counter on it, you draw a card.",
                 lambda d: {**d, "effects": [{"do": "turf110j"}]})


def _turf_take(plan: Any, ctx: Any, land: str, who: str) -> None:
    from app.rules import effects

    effects.PRIMITIVES["gain_control"](plan, ctx, {"do": "gain_control", "who": f"object:{plan.oid(land)}", "to": f"player:{who}", "untap": True})


def turf(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    found, hit = context.info(plan, ctx, context.EVENT), next(iter((ctx.get("event") or {}).get("players") or []), None)
    lands = [c.id for c in plan.state.cards.values() if found and c.zone.endswith(":battlefield") and c.controller == hit
             and "Land" in plan.ch(c).types and c.counters.get("contested")]
    if not lands or found is None:
        return True
    who = found[0].controller
    if len(lands) > 1:
        decide(plan, player=who, kind="choose_cards", prompt="Gain control of one of the lands with contested counters", min_choices=1, max_choices=1,
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "a land", card_id=c) for c in lands], resume={"step": "turf110j", "ctx": ctx, "who": who})
        return False
    _turf_take(plan, ctx, lands[0], who)
    return True


def resume_turf(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    _turf_take(plan, d.resume["ctx"], chosen[0], d.resume["who"])
    continue_effects(plan, d.resume["ctx"])


PRIMITIVES["turf110j"] = turf
RESUME: dict[str, Any] = {"turf110j": resume_turf}


# -- Kianne, Dean of Substance // Imbraham, Dean of Theory (wave 110J) -- study counters on exiled cards (122.1: counters on a card in exile are legal)
def _kianne(d: Def) -> Def:
    land = d["effects"][1]["cond"]
    return {**d, "effects": [d["effects"][0], d["effects"][1], d["effects"][2], {"do": "only_if", "cond": {"not": land}, "skip": 1},
                             {"do": "add_counters", "who": "ref:e0", "kind": "study", "n": 1}]}


_BUILD["{T}: Exile the top card of your library. If it's a land card, put it into your hand. Otherwise, put a study counter on it."] = (
    "{T}: Exile the top card of your library. If it's a land card, return it to your hand.", _kianne)


def _imbraham(d: Def) -> Def:
    from app.rules import selectors

    sel = selectors.parse("card you own in exile with a study counter on it")
    assert sel is not None
    return {**d, "effects": [*d["effects"], {"do": "player_chooses", "who": "you", "sel": sel.key(), "n": 1, "label": "card with a study counter", "zone": "exile",
                                             "upto": True, "optional": True, "as": "stu"}, {"do": "bounce", "who": "ref:stu"}]}


_BUILD["{X}{U}{U}, {T}: Exile the top X cards of your library and put a study counter on each of them. Then you may put a card you own in exile with a study counter on it into your hand."] = (
    "{X}{U}{U}, {T}: Exile the top X cards of your library and put a study counter on each of them.", _imbraham)


# -- Memory Vampire (wave 110J) -- the mill clause (any number of target players, 115.1) then the collect-evidence reflexive trigger (701.59, 603.12) of the native wording
def _vampire(d: Def) -> Def:
    mill = {"do": "mill", "who": "target:0", "n": {"event_amount": 1}}
    return {**d, "targets": [{"what": 'sel:{"player":"any"}', "min": 0, "max": 250}], "effects": [mill, *d["effects"]]}


_BUILD["Whenever this creature deals combat damage to a player, any number of target players each mill that many cards. Then you may collect evidence 9. When you do, you may cast target nonland card from defending player's graveyard without paying its mana cost."] = (
    "Whenever this creature deals combat damage to a player, you may collect evidence 9. When you do, you may cast target nonland card from that player's graveyard without paying its mana cost.", _vampire)


# -- Nettlevine Blight (wave 110J) -- the granted trigger names its Aura (607.1a, layers bind ‹granter#oid›): its controller (the permanent's) sacrifices the permanent,
# then chooses (not a target, 608.2d) a creature or land they control; the Aura, still on the battlefield, is attached to it (701.3a, 303.4f)
_BLIGHT = re.compile(r"At the beginning of your end step, sacrifice (?:this permanent|~) and attach ‹granter(?:#(?P<oid>[^›]*))?› to a creature or land you control\.")


def _nettlevine(oid: str | None, ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts
    from app.rules.nontarget_creature_choices import key

    native = scripts.define(replace(ability, text="At the beginning of your end step, sacrifice this permanent."), ch)
    if native is None:
        return None
    pick = {"do": "player_chooses", "who": "you", "sel": key("creature or land you control"), "n": 1, "label": "creature or land", "as": "nv110j"}
    # (no object id yet while the grant is only being read: attaches nothing)
    return {**native, "effects": [*native["effects"], pick, {"do": "attach_to", "src": f"obj:{oid or ''}", "who": "ref:nv110j"}]}


# -- Shuriken (wave 110J) -- the granted activated ability names its Equipment: it deals the damage (120.3), the cost unattached it (701.3d) from the creature whose
# type counts (it was a Ninja or not), and the target's controller (as it last existed, 608.2h) gains control of the Equipment unless it was a Ninja
_SHURIKEN = re.compile(r"\{T\}, Unattach ‹granter(?:#(?P<oid>[^›]*))?›: ‹granter(?:#[^›]*)?› deals 2 damage to target creature\. "
                       r"That creature's controller gains control of ‹granter(?:#[^›]*)?› unless it was unattached from a Ninja\.")


def _shuriken(oid: str | None, ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    g = f"‹granter#{oid}›" if oid else "‹granter›"
    native = scripts.define(replace(ability, text=f"{{T}}, Unattach {g}: {g} deals 2 damage to target creature."), ch)
    if native is None:
        return None
    take = {"do": "gain_control", "who": f"obj:{oid or ''}", "to": "target_player_or_controller"}
    return {**native, "effects": [*native["effects"], {"do": "only_if", "cond": {"not": {"w110j": "unattached_ninja"}}, "skip": 1}, take]}


# Bomb Squad: 603.8 state trigger per creature (state_triggers._each); "that creature" is the event object
_BUILD["Whenever a creature has four or more fuse counters on it, remove all fuse counters from it and destroy it. That creature deals 4 damage to its controller."] = (
    "Whenever a creature attacks, remove all fuse counters from it and destroy it. That creature deals 4 damage to its controller.",
    lambda d: {**d, "trigger": "state", "cond": None, "state": {"each110j": ["fuse", 4]}})


# -- Temporal Aperture (wave 110J) -- after the shuffle and reveal: until end of turn, for as long as that card remains on top of the library (checked in
# permissions.expire_source and grants), it is revealed to everyone (401.5, visibility.top_revealed) and its owner may play it free (118.9, X is 0: 107.3b)
def aperture(plan: Any, ctx: Def, e: Def) -> bool:
    import secrets

    from app.game.rules_state import Permission
    from app.game.state import zone_key

    pid = ctx["controller"]
    library = plan.state.zones.get(zone_key(pid, "library"), [])
    if library:
        top = library[0]
        plan.rules.permissions.append(Permission(
            id=secrets.token_hex(4), player=pid, play=True, cast=True, zone="library_top", object_id=plan.oid(plan.state.cards[top]), card=top, free=True,
            top110j=True, turn=plan.state.turn.number, granted_step=plan.rules.step_serial, source=ctx.get("source_object"),
            label=f"{ctx.get('name') or 'An effect'}: play it from the top of your library without paying its mana cost"))
    return True


PRIMITIVES["aperture110j"] = aperture
_BUILD["{5}, {T}: Shuffle your library, then reveal the top card. Until end of turn, for as long as that card remains on top of your library, play with the top card of your library revealed and you may play that card without paying its mana cost."] = (
    "{5}, {T}: Shuffle your library, then reveal the top card of your library.", lambda d: {**d, "effects": [*d["effects"], {"do": "aperture110j"}]})


# -- Dimensional Breach (wave 110J) -- 603.7: the delayed ability at the beginning of each player's upkeep (it ends once none of the exiled cards remain exiled,
# 611.2b); that player (the active player, 503.1) returns one of the exiled cards they own to the battlefield (their choice, 608.2d)
_BREACH = ("Exile all permanents. For as long as any of those cards remain exiled, at the beginning of each player's upkeep, "
           "that player returns one of the exiled cards they own to the battlefield.")


def _breach_cards(plan: Any, cards: list[dict[str, str]]) -> list[str]:
    return [c["card"] for c in cards if (card := plan.state.cards.get(c["card"])) is not None and card.zone.endswith(":exile") and plan.oid(card) == c["object"]]


def breach_live(plan: Any, t: Any) -> bool:
    return any(_breach_cards(plan, e["cards"]) for e in t.effects if e.get("do") == "breach_return110j")


def breach_setup(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    import secrets

    from app.game.rules_state import DelayedTrigger
    from app.rules import context

    name = next((k for k in (ctx.get("refs") or {}) if k.endswith("bx110j")), "")  # (the grammar prefixes binding names with their level: l0_bx110j)
    cards = [{"card": c, "object": plan.oid(c)} for c in context.objects(plan, ctx, name) if plan.state.cards[c].zone.endswith(":exile")]
    if cards:
        plan.rules.delayed.append(DelayedTrigger(
            id=secrets.token_hex(4), controller=ctx["controller"], source_card=ctx.get("source_card"), source_object=ctx.get("source_object"),
            name=ctx.get("name") or "Dimensional Breach", when={"kind": "step", "step": "upkeep", "whose": "each110j"},
            effects=[{"do": "breach_return110j", "cards": cards}], turn=plan.state.turn.number, step=plan.state.turn.phase,
            created_step=plan.rules.step_serial, once=False))
    return True


def _breach_return(plan: Any, ctx: Any, card: str) -> None:
    from app.rules import context, effects

    context.bind_objects(plan, ctx, "pick110j", [card])
    effects.PRIMITIVES["return_card"](plan, ctx, {"do": "return_card", "who": "ref:pick110j", "to": "battlefield", "tapped": False, "under": "owner"})


def breach_return(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    who = plan.active
    mine = [c for c in _breach_cards(plan, e["cards"]) if plan.state.cards[c].owner == who]
    if len(mine) > 1:
        decide(plan, player=who, kind="choose_cards", prompt="Return one of the exiled cards you own to the battlefield", min_choices=1, max_choices=1,
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "a card", card_id=c) for c in mine],
               resume={"step": "breach110j", "ctx": ctx})
        return False
    if mine:
        _breach_return(plan, ctx, mine[0])
    return True


def resume_breach(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    _breach_return(plan, d.resume["ctx"], chosen[0])
    continue_effects(plan, d.resume["ctx"])


PRIMITIVES.update({"breach_setup110j": breach_setup, "breach_return110j": breach_return})
RESUME["breach110j"] = resume_breach
_BUILD[_BREACH] = ("Exile all permanents.", lambda d: {**d, "effects": [{**d["effects"][0], "as": "bx110j"}, {"do": "breach_setup110j"}]})


# -- Phyrexian Splicer (wave 110J) -- "Choose flying, first strike, trample, or shadow" is announced like the mode of a "choose one" ability (the choice comes before
# the targets, which name "the chosen ability"): four modes, each with its two target groups (601.2b-c, 700.2)
_SPLICER = ("{2}, {T}, Choose flying, first strike, trample, or shadow: Until end of turn, target creature with the chosen ability loses it and another "
            "target creature gains it.")


def _splicer(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    modes: list[Def] = []
    for k, kw in enumerate(("flying", "first strike", "trample", "shadow")):
        text = f"Target creature with {kw} loses {kw} until end of turn. Another target creature gains {kw} until end of turn."
        one = scripts.define(replace(ability, text="{2}, {T}: " + text, cost="{2}, {T}"), ch)
        if one is None or not one.get("targets"):
            return None
        modes.append({"text": text, "effects": scripts.rename_bindings(one["effects"], f"m{k}_"), "target": None, "groups": one["targets"]})
    return {"kind": "activated", "cost": "{2}, {T}", "effects": [], "target": None, "optional": False, "modes": modes,
            "modal": {"min": 1, "max": 1, "repeat": False, "condition": None, "memory": None, "index": ability.index, "form": "activated"}}


# -- Giant Oyster (wave 110J) -- the "doesn't untap" restriction is native ("for as long as this creature remains tapped", 611.2b); here: the -1/-1 counter at the
# beginning of each of its controller's draw steps while that holds (603.7), and the delayed "When this creature leaves the battlefield or becomes untapped,
# remove all -1/-1 counters from the creature" (603.7a), put on the stack by oyster_sweep as the table is next looked at (603.3)
_OYSTER = ("{T}: For as long as this creature remains tapped, target tapped creature doesn't untap during its controller's untap step, and at the beginning of each "
           "of your draw steps, put a -1/-1 counter on that creature. When this creature leaves the battlefield or becomes untapped, remove all -1/-1 counters "
           "from the creature.")
_BUILD[_OYSTER] = ("{T}: Target tapped creature doesn't untap during its controller's untap step for as long as this creature remains tapped.",
                   lambda d: {**d, "effects": [*d["effects"], {"do": "oyster110j"}]})


def oyster_live(plan: Any, ref: dict[str, str]) -> bool:
    card = plan.state.cards.get(ref["card"])
    return card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == ref["object"] and card.tapped


def oyster(plan: Any, ctx: Def, e: Def) -> bool:
    import secrets

    from app.game.rules_state import DelayedTrigger
    from app.rules import effects

    me = plan.state.cards.get(ctx.get("source_card") or "")
    if me is None or plan.oid(me) != ctx.get("source_object"):
        return True
    for target in effects._cards(plan, ctx, "target"):
        if plan.state.cards[target].zone.endswith(":battlefield"):
            plan.rules.delayed.append(DelayedTrigger(
                id=secrets.token_hex(4), controller=ctx["controller"], source_card=me.id, source_object=ctx.get("source_object"), name=ctx.get("name") or "Giant Oyster",
                when={"kind": "step", "step": "draw", "whose": "you"}, turn=plan.state.turn.number, step=plan.state.turn.phase, created_step=plan.rules.step_serial, once=False,
                effects=[{"do": "oyster_tick110j", "oyster": {"card": me.id, "object": ctx["source_object"]}, "target": {"card": target, "object": plan.oid(target)}}]))
    return True


def _oyster_target(plan: Any, e: Def) -> str | None:
    card = plan.state.cards.get(e["target"]["card"])
    return card.id if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == e["target"]["object"] else None


def oyster_tick(plan: Any, ctx: Def, e: Def) -> bool:
    from app.rules import context, effects

    if (target := _oyster_target(plan, e)) is not None:
        context.bind_objects(plan, ctx, "oy110j", [target])
        effects.PRIMITIVES["add_counters"](plan, ctx, {"do": "add_counters", "who": "ref:oy110j", "kind": "-1/-1", "n": 1})
    return True


def oyster_clear(plan: Any, ctx: Def, e: Def) -> bool:
    from app.rules import context, effects

    if (target := _oyster_target(plan, e)) is not None:
        context.bind_objects(plan, ctx, "oy110j", [target])
        effects.PRIMITIVES["remove_counters"](plan, ctx, {"do": "remove_counters", "who": "ref:oy110j", "kind": "-1/-1", "n": 1000000})
    return True


def oyster_sweep(plan: Any) -> None:
    from app.rules import delayed

    r = plan.rules
    ended = [t for t in r.delayed if t.effects and t.effects[0].get("do") == "oyster_tick110j" and not oyster_live(plan, t.effects[0]["oyster"])]
    if not ended:
        return
    r.delayed = [t for t in r.delayed if t not in ended]
    for t in ended:
        e = t.effects[0]
        delayed._fire(plan, t.model_copy(update={"effects": [{"do": "oyster_clear110j", "target": e["target"]}], "when": {"kind": "event"}}), None)


PRIMITIVES.update({"oyster110j": oyster, "oyster_tick110j": oyster_tick, "oyster_clear110j": oyster_clear})


# -- Balduvian Warlord, Sorrow's Path (wave 110J) -- blockers moved by an effect. 506.4 (removed from combat), 509.1h (a creature it blocked stays blocked), 509.3c/d via
# combat_rules.enter_blocking (an effect-made block does not check blocking restrictions: 509.1b is about the declaration; the attacker must attack the blocker's controller, 506.3e)
_WARLORD = ("{T}: Remove target blocking creature from combat. Creatures it was blocking that hadn't become blocked by another creature this combat become "
            "unblocked, then it blocks an attacking creature of your choice. Activate only during the declare blockers step.")
_PATH = ("{T}: Choose two target blocking creatures controlled by the same opponent. If each of those creatures could block all creatures that the other is "
         "blocking, remove both of them from combat. Each one then blocks all creatures the other was blocking.")


def _blocked_by(card: Any) -> list[str]:
    return [x for x in (card.blocking, *card.blocking_more) if x]


def _leave(plan: Any, ctx: Any, card: Any) -> None:
    from app.rules import combat_rules

    combat_rules.remove_from_combat(plan, ctx, {"who": f"object:{plan.oid(card)}"})


def _block(plan: Any, ctx: Any, blocker: Any, attacker_id: str) -> None:
    from app.rules import combat_rules

    combat_rules.enter_blocking(plan, ctx, {"who": f"object:{plan.oid(blocker)}", "blocked": f"object:{plan.oid(plan.state.cards[attacker_id])}", "effect": True})


# Rules check (wave 110 J): the brief said a creature made to block by an effect does not trigger "whenever ~ blocks". CR 509.3a/b say it DOES (once per combat if it
# was not already a blocking creature; per attacker for "blocks a creature"); only a creature put onto the battlefield blocking (509.4, Brimaz tokens) never triggers.
# So the effect-made blocks here pass "effect": True to combat_rules.enter_blocking, which fires the block triggers.
def warlord(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects, history
    from app.rules.plan import decide

    found = [plan.state.cards[c] for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].is_blocking and plan.state.cards[c].zone.endswith(":battlefield")]
    if not found:
        return True
    t, blocks = found[0], history.log_for(plan).blocks
    mine = plan.oid(t)
    atk = _blocked_by(t)
    _leave(plan, ctx, t)
    for a in atk:  # "hadn't become blocked by another creature this combat": nobody else was ever declared as its blocker
        if not any(plan.oid(plan.state.cards[a]) in objs for ob, objs in blocks.items() if ob != mine):
            plan.rules.blocked = [c for c in plan.rules.blocked if c != a]
    opts = [c.id for c in plan.state.cards.values() if c.is_attacking and c.zone.endswith(":battlefield") and c.attacking is not None
            and (c.attacking.id == t.controller or plan.state.cards.get(c.attacking.id) is not None and plan.state.cards[c.attacking.id].controller == t.controller)]
    if len(opts) > 1:
        decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{t.name} blocks which attacking creature?", min_choices=1, max_choices=1,
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "a creature", card_id=c) for c in opts], resume={"step": "warlord110j", "ctx": ctx, "who": t.id})
        return False
    if opts:
        _block(plan, ctx, t, opts[0])
    return True


def resume_warlord(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    _block(plan, d.resume["ctx"], plan.state.cards[d.resume["who"]], chosen[0])
    continue_effects(plan, d.resume["ctx"])


def path(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.rules import combat, effects

    got = [plan.state.cards[c] for k in ("who", "with") for c in effects._cards(plan, ctx, e[k])]
    if len(got) != 2 or got[0].id == got[1].id or got[0].controller != got[1].controller or not all(c.is_blocking and c.zone.endswith(":battlefield") for c in got):
        return True
    a, b = got
    # "could block all creatures that the other is blocking": every one of them blockable (509.1a-b restrictions) and within the blocker's block limit (509.1a)
    for x, y in ((a, b), (b, a)):
        if len(_blocked_by(y)) > combat.block_limit(plan, plan.ch(x)) or any(
                combat.block_problem(plan.state, x, plan.ch(x), plan.state.cards[i], plan.ch(plan.state.cards[i]), plan.info) for i in _blocked_by(y)):
            return True
    ma, mb = _blocked_by(a), _blocked_by(b)
    _leave(plan, ctx, a)
    _leave(plan, ctx, b)
    for x, ys in ((a, mb), (b, ma)):
        for i in ys:
            _block(plan, ctx, x, i)
    return True


PRIMITIVES.update({"warlord110j": warlord, "path110j": path})
RESUME["warlord110j"] = resume_warlord
_BUILD[_WARLORD] = ("{T}: Remove target blocking creature from combat. Activate only during the declare blockers step.",
                    lambda d: {**d, "effects": [{"do": "warlord110j", "who": d["effects"][0]["who"]}]})
_BUILD[_PATH] = ("{T}: Target blocking creature an opponent controls fights another target blocking creature that player controls.",
                 lambda d: {**d, "effects": [{**d["effects"][0], "do": "path110j"}]})


# -- Magnetic Web (wave 110J) -- 508.1d: while a creature with a magnet counter is declared as an attacker, every creature with one attacks if able (the condition is
# read from the proposed declaration: combat_conditional_requirements67.score, "magnet110j"); the trigger makes each of them block the attacker (509.1c, @it = the attacker)
_WEB1 = "If a creature with a magnet counter on it attacks, all creatures with magnet counters on them attack if able."
_WEB2 = "Whenever a creature with a magnet counter on it attacks, all creatures with magnet counters on them block that creature this turn if able."
_BUILD[_WEB2] = ("Whenever a creature with a magnet counter on it attacks, you gain 1 life.",
                 lambda d: {**d, "effects": [{"do": "restrict", "who": d["cond"]["sel"], "rules": ["must_block_obj:@it"]}]})


# -- Paliano, the High City (wave 110J) -- ruling 2014-05-29: without a draft nothing was chosen, so the mana ability adds no mana (not even colorless). It stays a
# mana ability (605.1a): {T} is paid, the one option adds nothing.
_PALIANO = "{T}: Add one mana of any color chosen as you drafted cards named Paliano, the High City."


def parse_mana(text: str) -> Any:
    from app.rules import mana as M

    return M.ManaAbility(tap=True, sacrifice_self=False, options=((),)) if text.strip() == _PALIANO else None


# -- Takklemaggot (wave 110J) -- "When enchanted creature dies, that creature's controller chooses a creature that this card could enchant. ..." Rulings 2009-10-01: the
# trigger resolves with the Aura in the graveyard (704.5m put it there); the creature is chosen on resolution (no target), only one this card could legally enchant, and
# the player must choose one if able; the controller of the returned card stays the Aura's controller. 303.4f: an Aura entering not being cast is attached to the chosen
# object. With none, it returns as an Enchantment that is no Aura (205.1a, entry form), loses "enchant creature" (613.1f) and gains the damage trigger, which names the
# player the dying creature's controller (chosen player, 614.12a style record).
_TAKKLE = ("When enchanted creature dies, that creature's controller chooses a creature that this card could enchant. If the player does, return this card to the battlefield "
           "under your control attached to that creature. If they don't, return this card to the battlefield under your control as a non-Aura enchantment. It loses \"enchant "
           "creature\" and gains \"At the beginning of that player's upkeep, this enchantment deals 1 damage to that player.\"")
_TAKKLE_GAIN = "At the beginning of the chosen player's upkeep, this enchantment deals 1 damage to that player."
_BUILD[_TAKKLE] = ("When enchanted creature dies, draw a card.", lambda d: {**d, "effects": [{"do": "takkle110j"}]})


def _takkle_hosts(plan: Any, card: Any, controller: str) -> list[str]:
    from app.rules import attachments

    return [h for h in attachments.legal_hosts(plan, card, controller)
            if h in plan.state.cards and plan.state.cards[h].zone.endswith(":battlefield") and "Creature" in plan.ch(plan.state.cards[h]).types]


def takkle(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide
    from app.rules.targets import label

    card = plan.state.cards.get(ctx.get("source_card") or "")
    who = context.players(plan, ctx, "event.controller")
    if card is None or not card.zone.endswith(":graveyard") or not who:  # (ruling: only if it is still in that graveyard)
        return True
    hosts = _takkle_hosts(plan, card, ctx["controller"])
    if hosts:
        decide(plan, player=who[0], kind="choose_one", prompt="Choose a creature for the Aura to enchant", options=[DecisionOption(id=h, label=label(plan, h), card_id=h) for h in hosts],
               resume={"step": "takkle110j", "ctx": ctx, "chooser": who[0]}, source=card)
        return False
    return _takkle_enter(plan, ctx, card, None, who[0])


def _takkle_enter(plan: Any, ctx: Any, card: Any, host: str | None, chooser: str) -> bool:
    from app.rules import attachments, chosen, effects

    entry: dict[str, Any] = {"card": card.id, "player": ctx["controller"], "actor": ctx["controller"]}
    if host is not None:
        entry["host"] = host
    if host is None:  # (attachments.enter judges the printed Aura: it would stay in the graveyard, 303.4g; it stops being an Aura at once below, 205.1a, before any state-based action, 704.5m)
        from app.rules import replacements

        replacements.move_together(plan, [entry])
    elif not attachments.enter(plan, [entry], ctx):
        return False
    now = plan.state.cards[card.id]
    if host is None and now.zone.endswith(":battlefield"):
        plan.do({"type": "set_choice", "card_id": card.id, "key": "Chosen player", "value": plan.state.players[chooser].name}, actor=ctx["controller"])
        chosen.record(plan, card.id, chooser)
        gone = [a.index for a in plan.ch(now).abilities if a.kind == "keywords" and a.text.startswith("Enchant")]
        effects.become(plan, {**ctx, "source_card": card.id, "source_object": plan.oid(now)},
                       {"who": "self", "types": [], "remove_subtypes": ["Aura"], "abilities": [_TAKKLE_GAIN], "lose_index": gone, "duration": "permanent", "marker": "loses enchant creature"})
    return True


def resume_takkle(plan: Any, d: Any, chosen_ids: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is None or not card.zone.endswith(":graveyard"):
        return continue_effects(plan, ctx)
    if chosen_ids[0] not in _takkle_hosts(plan, card, ctx["controller"]):
        raise ValueError("it can't enchant that")
    if _takkle_enter(plan, ctx, card, chosen_ids[0], d.resume["chooser"]):
        continue_effects(plan, ctx)


PRIMITIVES["takkle110j"] = takkle
RESUME["takkle110j"] = resume_takkle


# -- Volrath's Curse (wave 110J) -- "That creature's controller may sacrifice a permanent of their choice for that player to ignore this effect until end of turn."
# The creature gets "Sacrifice a permanent: ..." (its controller pays; ceilings: it uses the stack and needs priority, so it must be done before attackers/blockers are
# declared, and two Curses on one creature are ignored together) which is exempt from the Curse's own "activated abilities can't be activated" (casting.py); while it
# has been paid this turn (statics.holds "ignored110j") the whole static, "can't attack or block" included, does not apply (611.3a).
_CURSE = ("Enchanted creature can't attack or block, and its activated abilities can't be activated. That creature's controller may sacrifice a permanent of their choice "
          "for that player to ignore this effect until end of turn.")
_CURSE_IGNORE = "Sacrifice a permanent: Ignore Volrath's Curse until end of turn."
_BUILD[_CURSE] = ("Enchanted creature can't attack or block, and its activated abilities can't be activated.",
                  lambda d: {**d, "grants": [_CURSE_IGNORE], "conditions": [{"static": "not", "cond": {"static": "ignored110j"}}]})


def ignore(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    plan.rules.once_per_turn[f"ignore110j:{ctx['source_object']}"] = plan.state.turn.number
    plan.note("Volrath's Curse is ignored until end of turn", actor=ctx["controller"])
    return True


PRIMITIVES["ignore110j"] = ignore


# -- Last Voyage of the _____ (wave 110J) -- rulings 2022-10-07: it becomes an Aura whether or not a sticker was put on (205.1, permanent: 611.2a), enchant creature; if it can't
# be attached to the returned creature (protection) it goes to the graveyard as a state-based action (704.5m) and the creature stays. 303.4: attach_to is the engine's
# "attach this Aura to it". Its +2/+0 counts the name stickers on this Aura with seven or fewer letters (values.py "sticker_short110j").
_VOYAGE = ("When this enchantment enters, you may put a name sticker on it, then it becomes an Aura with enchant creature. Return a creature card from your graveyard to the "
           "battlefield and attach this Aura to it.")


def _voyage(d: Def) -> Def:
    fx = d["effects"]
    return {**d, "effects": [fx[0], {"do": "become", "who": "self", "types": [], "add_creature_types": ["Aura"], "abilities": ["Enchant creature"], "duration": "permanent"}, *fx[1:]]}


_BUILD[_VOYAGE] = ("When this enchantment enters, you may put a name sticker on it. Return a creature card from your graveyard to the battlefield and attach this Aura to it.", _voyage)
_BUILD["Enchanted creature gets +2/+0 for each name sticker on this Aura with seven or fewer letters."] = (
    "Enchanted creature gets +2/+0 for each counter on this Aura.", lambda d: {**d, "each": {**d["each"], "value": {"sticker_short110j": True}}})
_BUILD["When this Aura leaves the battlefield, sacrifice enchanted creature."] = (
    "When this Aura leaves the battlefield, enchanted creature's controller sacrifices it.", lambda d: d)


def short_stickers(plan: Any, ctx: Any) -> int:
    """Name stickers (kind "name") on the source whose text has seven or fewer letters (spaces and punctuation are not letters)."""
    card = plan.state.cards.get(ctx.get("source_card") or "")
    return 0 if card is None else sum(1 for p in card.stickers101 if p.sticker.kind == "name" and sum(ch.isalpha() for ch in p.sticker.text) <= 7)


# -- Equinox (wave 110J) -- "{T}: Counter target spell if it would destroy a land you control." Rulings: 2013-09-20 checked as the ability resolves, by what the spell would do
# right then; 2004-10-04 / 2008-10-01 only a spell that destroys the land directly (not damage, sacrifice, or a result of a choice or chance); any spell can be targeted.
# Read: the spell's own unconditional "destroy" instructions (a target, a selector) and "destroy all"; a spell with modes, or any other instruction that mentions destroying,
# is not guessed: the ability's controller says whether it would (the same call a player makes at the table).
_EQUINOX = "{T}: Counter target spell if it would destroy a land you control."


def _destroys_my_land(plan: Any, entry: Any, sid: str, ctx: Any) -> bool | None:
    from app.rules import effects

    if plan.state.cards[sid].ability is not None:
        return False
    if entry is None or entry.modes or entry.slots:
        return None
    sctx = {"controller": entry.controller, "source_card": entry.source_card, "source_object": entry.source_object, "name": entry.name,
            "targets": [t.model_dump() for t in entry.targets], "stack_id": sid, "kind": entry.kind, "effects": entry.effects, "next": 0, "x": entry.x, "event": None}
    hit = False
    for e in entry.effects:
        if e.get("do") == "destroy" and set(e) <= {"do", "who", "as"} and (e["who"] == "target" or str(e["who"]).startswith("sel:")):
            ids = effects._cards(plan, sctx, e["who"])
        elif e.get("do") == "destroy_all" and set(e) <= {"do", "who", "types"} and e.get("who") == "all":
            ids = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.ch(c).types & set(e.get("types") or ["Land"])] if "Land" in (e.get("types") or []) else []
        elif "destroy" in repr(e):
            return None
        else:
            continue
        hit = hit or any(plan.state.cards[c].zone.endswith(":battlefield") and plan.state.cards[c].controller == ctx["controller"] and "Land" in plan.ch(plan.state.cards[c]).types
                         for c in ids if c in plan.state.cards)
    return hit


def equinox(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    sids = effects._stack_targets(plan, ctx, {"who": "target"})
    if not sids:
        return True
    sid = sids[0]
    verdict = _destroys_my_land(plan, plan.rules.stack.get(sid), sid, ctx)
    if verdict is None:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"Would {plan.state.cards[sid].name} destroy a land you control if it resolved right now?",
               options=[DecisionOption(id="yes", label="Yes, counter it"), DecisionOption(id="no", label="No")], resume={"step": "equinox110j", "ctx": ctx, "sid": sid})
        return False
    return effects.counter(plan, ctx, {"do": "counter", "who": "target"}) if verdict else True


def resume_equinox(plan: Any, d: Any, chosen_ids: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if chosen_ids[0] == "yes" and d.resume["sid"] in plan.state.zones.get("stack", []):
        effects.counter(plan, ctx, {"do": "counter", "who": "target"})
    effects.continue_effects(plan, ctx)


PRIMITIVES["equinox110j"] = equinox
RESUME["equinox110j"] = resume_equinox
_BUILD["Enchanted land has \"" + _EQUINOX + "\""] = ("Enchanted land has \"{T}: Counter target spell.\"", lambda d: {**d, "grants": [_EQUINOX]})
