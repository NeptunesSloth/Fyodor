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
    if cond.get("w110j") == "shares_event_type":  # Swindler's Scheme: 205.2, the revealed card and the spell that triggered it
        from app.rules import values

        card, spell = values._object(plan, ctx, cond["object"]), values._object(plan, ctx, "event")
        return card is not None and spell is not None and bool(set(card[1].types) & set(spell[1].types))
    return ctx.get("source_object") in plan.rules.began_untapped110j


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts

    if (cap := _CAP.fullmatch(ability.text.strip())) is not None and ch.name.startswith(cap["name"]):  # (the short name)
        return {"kind": "static", "static": "counter_cap110j", "counter": cap["kind"], "n": _NUMS[cap["n"]], "effects": []}
    if ability.text.strip() == _ES:
        return _shapeshifter()
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


def parse(body: str) -> Any:
    from app.rules import scripts

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
    if not lands:
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
