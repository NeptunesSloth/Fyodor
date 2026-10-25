"""-- spells (wave 110A) -- instant and sorcery wordings read onto the existing primitives."""
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

Parsed = tuple[list[dict[str, Any]], Any, bool]


def _p(text: str) -> Parsed:
    from app.rules import scripts

    got = scripts.parse_effects(text)
    if got is None:
        raise AssertionError(f"wave110a: the grammar no longer reads {text!r}")
    return copy.deepcopy(got)


def _berserk() -> Parsed:
    """Berserk: "that creature attacked this turn" is read as the end step begins (508.1; the attack record of that object, 400.7)."""
    effects, target, optional = _p("Target creature gains trample and gets +X/+0 until end of turn, where X is its power. "
                                   "At the beginning of the next end step, destroy that creature.")
    destroy, delayed = effects.pop(), effects[-1]
    cond = {"history": "object", "object": "ref:berserk110a", "what": "attacked"}
    return [*effects[:-1], {"do": "bind110a", "who": "target", "as": "berserk110a"}, {**delayed, "n": 2},
            {"do": "deferred:only_if", "cond": cond, "skip": 1}, destroy], target, optional


def _take_the_bait() -> Parsed:
    """Take the Bait: the prevention covers you and the planeswalkers you control (615.1; damage to a planeswalker, 120.3c), then the attackers untap and
    are goaded (701.15), then the added combat phase (500.8)."""
    from app.rules import selectors

    prevent = _p("Prevent all combat damage that would be dealt to you and creatures you control this turn.")[0][0]
    walkers = selectors.Selector(controller="you", types=("Planeswalker",)).key()
    rest = _p("Untap all attacking creatures and goad them. After this phase, there is an additional combat phase.")[0]
    return [{**prevent, "scope": {**prevent["scope"], "to_objects": walkers}}, *rest], None, False


def _snow(add: bool) -> Callable[[], Parsed]:
    from app.rules import selectors

    def build() -> Parsed:
        return ([{"do": "snow110a", "who": "target", "add": add}],
                (selectors.Selector(not_supertypes=("Snow",)) if add else selectors.Selector(supertypes=("Snow",))).key(), False)
    return build


def controller_of(plan: Any, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    """"its controller has …": the condition judged for the controller the object has, or had as it last existed (608.2h); gone: false (608.2b)."""
    from app.rules import conditions, values

    found = values._object(plan, ctx, cond["object"])
    return found is not None and conditions.holds(plan, {**ctx, "controller": found[0].controller}, cond["cond"])


CONDITIONS = {"controller_of": controller_of}


def _anoint() -> Parsed:
    """Anoint with Affliction: judged once as it resolves (608.2c): corrupted (its controller has three or more poison counters) exiles it
    whatever its mana value, else only with mana value 3 or less."""
    from app.rules import multi100n

    base, target, optional = _p("Exile target creature if it has mana value 3 or less.")
    alt = _p("Exile target creature.")[0]
    corrupted = {"w110a": "controller_of", "object": "target", "cond": {"value": {"player_counters": "poison"}, "op": ">=", "n": 3}}
    return multi100n._instead(corrupted, base, alt), target, optional


def _slime() -> Parsed:
    """Convert to Slime: delirium counts the graveyard after the destruction ("Then", 608.2c); X is the total mana value of the permanents that were
    destroyed this way, each as it last existed (608.2h) — one that wasn't destroyed (indestructible, regenerated) counts for nothing."""
    effects, groups, optional = _p("Destroy up to one target artifact, up to one target creature, and up to one target enchantment. Then if there are four "
                                   "or more card types among cards in your graveyard, create a 1/1 green Ooze creature token.")
    total = {"plus": [{"sum": "mana_value", "of": f"ref:slime{i}"} for i in range(3)]}
    out = []
    for e in effects:
        if e["do"] == "destroy":
            e = {**e, "as": f"slime{e['who'].rpartition(':')[2]}"}
        elif e["do"] == "create_token":
            e = {**e, "token": {**e["token"], "power": total, "toughness": total}}
        out.append(e)
    return out, groups, optional


# Sentences the grammar reads in other words with the same meaning (the rewrite must mean the same: 608.2c).
REWRITES = {
    # (122.6: "enters with … additional counters" is the grammar's "if a creature enters this way, it enters with …" for the returned permanent card)
    "Return target historic permanent card from your graveyard to the battlefield. It enters with two additional +1/+1 counters on it if it's a "
    "creature.": "Return target historic permanent card from your graveyard to the battlefield. If a creature enters this way, it enters with two "
                 "additional +1/+1 counters on it.",
}


def _choose_transform(kind: str) -> Parsed:
    from app.rules import nontarget_creature_choices as pick

    return [pick.choose(kind, **{"as": "choice_group"}), {"do": "transform", "who": "ref:choice_group"}], None, False


BUILDERS: dict[str, Callable[[], Parsed]] = {
    "Destroy up to one target artifact, up to one target creature, and up to one target enchantment. Then if there are four or more card types among "
    "cards in your graveyard, create an X/X green Ooze creature token, where X is the total mana value of permanents destroyed this way.": _slime,
    "Exile target creature if it has mana value 3 or less. Exile that creature instead if its controller has three or more poison counters.": _anoint,
    "Tap up to three target creatures. Put a stun counter on one of them.": lambda: (  # Aerith Rescue Mission: 122.1g, one of the targets (608.2d)
        [*(tap := _p("Tap up to three target creatures."))[0], {"do": "bind110a", "who": "target:0", "as": "targets110a"},
         {"do": "choose_one_of", "who": "ref:targets110a", "n": 1, "as": "one110a"},
         {"do": "add_counters", "who": "ref:one110a", "kind": "stun", "n": 1}], tap[1], False),
    "Incubate 2, then transform an Incubator token you control.": lambda: (  # Sunder the Gateway: 701.53a, then 701.28 the Incubator you choose
        [*_p("Incubate 2.")[0], *_choose_transform("Incubator token you control")[0]], None, False),
    # Thermal Flux: 205.4 snow is a supertype, so layer 4 (613.1d), until end of turn (the duration of supertype100i is the effect's default)
    "Target nonsnow permanent becomes snow until end of turn.": _snow(True),
    "Target snow permanent isn't snow until end of turn.": _snow(False),
    "Prevent all combat damage that would be dealt to you and planeswalkers you control this turn. Untap all attacking creatures and goad them. "
    "After this phase, there is an additional combat phase.": _take_the_bait,
    "End the combat phase.": lambda: ([{"do": "end_combat_phase110a"}], None, False),  # (Mandate of Peace: 724.2)
    "Target creature gains trample and gets +X/+0 until end of turn, where X is its power. At the beginning of the next end step, destroy that "
    "creature if it attacked this turn.": _berserk,
}


def bind(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Name the objects ``who`` is now (400.7), so a condition of a delayed trigger can ask about them."""
    from app.rules import context, effects

    context.bind_objects(plan, ctx, e["as"], effects._cards(plan, ctx, e["who"]))
    return True


def end_combat_phase(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """724.2: the expedited process, as end_turn.end_turn (724.1) but to the next phase (the postcombat main, or an added phase): earlier triggers
    that weren't on the stack cease to exist (724.2a), the stack is exiled with the resolving spell (724.2b), state-based actions (724.2c), combat is
    left and "until end of combat" effects expire (724.2d), no end of combat step so its abilities don't trigger (724.2e); outside a combat phase
    nothing happens (724.2g)."""
    from app.game.state import COMBAT_PHASES, STACK
    from app.rules import combat, combat_rules, engine, sba, triggers

    if plan.state.turn.phase not in COMBAT_PHASES:
        return True
    r = plan.rules
    triggers.collect(plan)
    r.pending_triggers = []
    for sid in list(plan.state.zones.get(STACK, [])):
        oid = plan.oid(sid)
        r.stack.pop(sid, None)
        r.buyback = [o for o in r.buyback if o != oid]
        r.flashback = [o for o in r.flashback if o != oid]
        r.exile_resolves.pop(oid, None)
        plan.do({"type": "move", "card_ids": [sid], "to": {"player": plan.state.cards[sid].owner, "zone": "exile"}}, actor=ctx["controller"])
    plan.note(f"{ctx.get('name') or 'An effect'} ends the combat phase (724.2)", actor=ctx["controller"])
    sba.check(plan)
    combat.end_combat(plan)
    engine.empty_pools(plan)
    plan.do({"type": "phase", "to": combat_rules.next_phase(plan) or "main2", "force": True}, actor=plan.active)
    engine._mark_step(plan)
    engine.on_step_start(plan)
    return r.decision is None


def snow(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Layer 4 (613.1d), until end of turn: the target permanent becomes snow or isn't snow (205.4, 611.2c: locked to the objects it began on)."""
    from app.rules import effects, layers

    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    if cards:
        change: dict[str, Any] = {"add_supertypes": ["Snow"]} if e["add"] else {"remove_supertypes": ["Snow"]}
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="4", source=ctx.get("source_object"), controller=ctx["controller"],
                          label=f"{'snow' if e['add'] else 'not snow'} ({ctx.get('name', '')})", **change)
    return True


PRIMITIVES = {"bind110a": bind, "end_combat_phase110a": end_combat_phase, "snow110a": snow}
