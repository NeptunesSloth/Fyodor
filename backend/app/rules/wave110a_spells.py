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


def _repeat_put(what: str) -> Callable[[], Parsed]:
    """Eureka, Hypergenesis: each player in turn, starting with you, may put one such card from their hand onto the battlefield (101.4: in turn order,
    each choice after the cards before it entered); the round is repeated while someone put a card onto the battlefield."""
    def build() -> Parsed:
        put = _p(f"Each player may put {what} card from their hand onto the battlefield.")[0][0]
        return [{"do": "repeat_put110a", "put": put, "first": True}], None, False
    return build


def repeat_put(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    if not e["first"] and not ctx.get("_any_put110a"):
        return True
    ctx["_any_put110a"] = False
    seats = plan.apnap()
    order = [p for p in seats[seats.index(ctx["controller"]):] + seats[:seats.index(ctx["controller"])] if p in plan.live()]
    steps: list[dict[str, Any]] = []
    for p in order:
        steps += [{**e["put"], "who": f"player:{p}"}, {"do": "note_put110a", "p": p}]
    ctx["effects"][ctx["next"]:ctx["next"]] = [*steps, {**e, "first": False}]
    return True


def note_put(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """each_put left the players who put nothing in ``_put_none``: this round goes on if one put a card."""
    if e["p"] not in ctx.get("_put_none", ()):
        ctx["_any_put110a"] = True
    return True


def _meditation() -> Parsed:
    """Cleansing Meditation: threshold judged as it resolves (608.2c); instead the enchantment cards in your graveyard that were destroyed this way
    (so yours: they go to their owner's graveyard, 400.3) return to the battlefield under your control."""
    from app.rules import multi100n

    base, target, optional = _p("Destroy all enchantments.")
    alt = _p("Destroy all enchantments, then return all enchantment cards put into your graveyard this way to the battlefield.")[0]
    return multi100n._instead(multi100n._cond("there are seven or more cards in your graveyard"), base, alt), target, optional

def _searing_light_exile() -> Parsed:
    """Olórin's Searing Light: each opponent exiles a creature with the greatest power among creatures they control (101.4: simultaneous choices,
    the edict's group exile)."""
    exile = copy.deepcopy(_p("Each opponent exiles a creature they control with the greatest power among creatures they control.")[0][0])
    return [{**exile, "as": "exiled110a"}], None, False


def _searing_light_mastery() -> Parsed:
    """Spell mastery (an ability word, no rule meaning, 207.2c): each opponent is dealt damage equal to the power of the creature that player exiled,
    as it last existed (608.2h)."""
    cond = _cond("there are two or more instant and/or sorcery cards in your graveyard")
    return [{"do": "only_if", "cond": cond, "skip": 1}, {"do": "exiled_power_damage110a", "ref": "exiled110a"}], None, False


def _cond(text: str) -> dict[str, Any]:
    from app.rules import multi100n

    return multi100n._cond(text)


def exiled_power_damage(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Damage from the source to each player who exiled a creature this way, equal to that creature's power as it last existed (120.3, 608.2h)."""
    from app.rules import context, effects, sba

    hits = []
    # (a spell's lines keep their own binding names, scripts.rename_bindings: the first line's "l0_exiled110a" is found by its suffix)
    name = next((k for k in context.refs(ctx) if k.endswith(e["ref"])), e["ref"])
    for card, ch in context.infos(plan, ctx, name):
        n = sba.power(card, ch)
        if n and n > 0:
            hits.append((effects._ability_source(plan, ctx), card.controller, n))
    return effects._deal(plan, ctx, hits) if hits else True


def exile_hands(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Every card in every hand, at once (a selector never reads hidden zones of other players; the move is public, 400.1)."""
    from app.game.state import zone_key
    from app.rules import effects

    return effects.exile_cards(plan, ctx, e, [c for p in plan.live() for c in plan.state.zones.get(zone_key(p, "hand"), [])])


def _decree() -> Parsed:
    """Decree of Annihilation: the three exiles in order (608.2c); "all cards from all hands" is every card in every hand (the hand zones, 400.1)."""
    first = _p("Exile all artifacts, creatures, and lands. Exile all cards from all graveyards.")[0]
    return [*first, {"do": "exile_hands110a"}], None, False


# Sentences the grammar reads in other words with the same meaning (the rewrite must mean the same: 608.2c).
REWRITES = {
    # (Threaten: control and haste both last until end of turn, 611.2a)
    "Until end of turn, you gain control of target creature and it gains haste.":
        "Gain control of target creature until end of turn. It gains haste until end of turn.",
    # (122.6: "enters with … additional counters" is the grammar's "if a creature enters this way, it enters with …" for the returned permanent card)
    "Return target historic permanent card from your graveyard to the battlefield. It enters with two additional +1/+1 counters on it if it's a "
    "creature.": "Return target historic permanent card from your graveyard to the battlefield. If a creature enters this way, it enters with two "
                 "additional +1/+1 counters on it.",
    # (Bioshift: "with the same controller" = the controller of the first target, the "that player" of Mutiny's wording; player_relative._names_player)
    "Move any number of +1/+1 counters from target creature onto another target creature with the same controller.":
        "Move any number of +1/+1 counters from target creature onto another target creature that player controls.",
    # (Dispersal: lands have mana value 0, so a nonland permanent has the greatest mana value among all permanents its controller controls exactly
    # when it has it among their nonland ones; each opponent chooses, 701.21a-style, one after the other, then the discards)
    "Each opponent returns a nonland permanent they control with the greatest mana value among permanents they control to its owner's hand, then "
    "discards a card.":
        "Each opponent chooses a nonland permanent with the greatest mana value among nonland permanents they control. Return it to its owner's hand. "
        "Each opponent discards a card.",
}


def _choose_transform(kind: str) -> Parsed:
    from app.rules import nontarget_creature_choices as pick

    return [pick.choose(kind, **{"as": "choice_group"}), {"do": "transform", "who": "ref:choice_group"}], None, False


def _owner_too() -> Parsed:
    """Pendant of Prosperity: the artifact's owner (108.3, wherever it is now) does the same as you (608.2c: each player's own hand)."""
    mine = _p("Draw a card, then you may put a land card from your hand onto the battlefield.")[0]
    draw, put = _p("Target player draws a card, then that player may put a land card from their hand onto the battlefield.")[0]
    return [*mine, {**draw, "who": "source_owner"}, {**put, "who": "source_owner"}], None, False


_ROUND = " Repeat this process until no one puts a card onto the battlefield."
def _melee() -> Parsed:
    """Melee: 509.3g, 506.4 — the watch is the grammar's "untap it and tap it" with the second step read as "remove it from combat"."""
    effects, target, optional = _p("Whenever a creature attacks and isn't blocked this combat, untap it and tap it.")
    assert effects[-1]["do"] == "deferred:tap"
    return [*effects[:-1], {**effects[-1], "do": "deferred:remove_from_combat"}], target, optional


def _chooser(kind: str, combat: bool = False) -> Callable[[], Parsed]:
    return lambda: ([{"do": "declare_chooser110a", "kind": kind, "combat": combat}], None, False)


BUILDERS: dict[str, Callable[[], Parsed]] = {
    # Gideon of the Trials +1: 615.1 a prevention shield that lasts until the controller's next turn (the shield record's own duration)
    "Until your next turn, prevent all damage target permanent would deal.": lambda: (
        [{**(got := _p("Prevent all damage target permanent would deal this turn."))[0][0], "duration": "next_turn"}], got[1], got[2]),
    "Target player draws 2ˣ cards.": lambda: ([{"do": "draw", "who": "target", "n": {"two_pow": {"x": 1}}}], "player", False),  # Mathemagics: 107.3 X
    "Each opponent exiles a creature with the greatest power among creatures that player controls.": _searing_light_exile,
    "If there are two or more instant and/or sorcery cards in your graveyard, ~ deals damage to each opponent equal to the power of the "
    "creature they exiled.": _searing_light_mastery,
    "Exile all artifacts, creatures, and lands from the battlefield, all cards from all graveyards, and all cards from all hands.": _decree,
    "Whenever a creature attacks and isn't blocked this combat, untap it and remove it from combat.": _melee,
    # Predatory Focus: 510.1c, each blocked creature of the controller asks its own "as though it weren't blocked" (group_unblocked.allows)
    "You may have creatures you control assign their combat damage this turn as though they weren't blocked.":
        lambda: ([{"do": "unblocked_turn110a"}], None, False),
    # Full Bore: 702.185a, the creature's spell was cast for its warp cost (the record stays with the permanent)
    "Target creature you control gets +3/+2 until end of turn. If that creature was cast for its warp cost, it also gains trample and haste until "
    "end of turn.": lambda: (lambda got: ([got[0][0], {"do": "only_if", "cond": {"object": "target", "cast_alt110a": "warp"}, "skip": 1}, got[0][2]],
                                          got[1], got[2]))(_p("Target creature you control gets +3/+2 until end of turn. If that creature is tapped, it also "
                                                                "gains trample and haste until end of turn.")),
    "You choose which creatures attack this turn.": _chooser("attack"),  # Master Warcraft: 508.1a
    "You choose which creatures block this turn and how those creatures block.": _chooser("block"),  # 509.1a
    "You choose which creatures block this combat and how those creatures block.": _chooser("block", True),
    "you choose which creatures block this combat and how those creatures block.": _chooser("block", True),  # Odric's trigger body (509.1a)
    "Draw a card, then you may put a land card from your hand onto the battlefield. ~'s owner draws a card, then that player may put a land "
    "card from their hand onto the battlefield.": _owner_too,
    "Destroy all enchantments. If there are seven or more cards in your graveyard, instead destroy all enchantments, then return all cards in your "
    "graveyard destroyed this way to the battlefield.": _meditation,
    "Starting with you, each player may put a permanent card from their hand onto the battlefield." + _ROUND: _repeat_put("a permanent"),
    "Starting with you, each player may put an artifact, creature, enchantment, or land card from their hand onto the battlefield." + _ROUND:
        _repeat_put("an artifact, creature, enchantment, or land"),
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


# Whole abilities the grammar reads in other words (same meaning).
ABILITY_REWRITES = {
    # Storm Cauldron: a land tapped for mana is tapped by a player (106.12a); a stack trigger, it adds no mana (so not a mana ability, 605.1b)
    "Whenever a land is tapped for mana, return it to its owner's hand.":
        "Whenever a player taps a land for mana, return that land to its owner's hand.",
    # Xenagos, the Reveler: the same choice, "any number" (the exiled cards are public; 608.2d the controller chooses on resolution)
    "\u22126: Exile the top seven cards of your library. You may put any number of creature and/or land cards from among them onto the battlefield.":
        "\u22126: Exile the top seven cards of your library. Put a creature or land card exiled this way onto the battlefield.",
}
_ANY_NUMBER = {"\u22126: Exile the top seven cards of your library. You may put any number of creature and/or land cards from among them onto the battlefield."}


BOUNCE_CHAMBER = ("Whenever you roll to visit your Attractions, return a creature you don't control with the lowest toughness among creatures you don't control to its owner's hand.")


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from dataclasses import replace

    from app.rules import scripts

    old = scripts.self_text(ability.text, ch.name)
    if old == "The attacking player chooses how each creature blocks each combat.":  # Invasion Plans: 509.1a, read by wave110a_choosers.chooser
        return {"kind": "static", "static": "block_chooser110a", "effects": []}
    if old == BOUNCE_CHAMBER:  # Bounce Chamber: the visitor (not each opponent) chooses among the tied lowest-toughness creatures it doesn't control
        from app.rules import selectors

        d = scripts.define(replace(ability, text="Whenever you roll to visit your Attractions, each opponent chooses a creature with the least toughness "
                                                 "among creatures they control. Return it to its owner's hand."), ch)
        sel = selectors.parse("creature you don't control with the lowest toughness among creatures you don't control")
        if d is None or sel is None or d["effects"][0]["do"] != "player_chooses":
            return None
        d["effects"][0].update(who="you", any=True, sel=sel.key(), label="creature with the lowest toughness among creatures you don't control")
        return d
    new = ABILITY_REWRITES.get(old)
    d = None if new is None else scripts.define(replace(ability, text=new), ch)
    if d is not None and old in _ANY_NUMBER:
        for e in d["effects"]:
            if e["do"] == "return_choice":
                e.update(n=99, upto=True)
    return d


def unblocked_turn(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    plan.rules.assign_unblocked_turn[ctx["controller"]] = plan.state.turn.number
    return True


PRIMITIVES = {"unblocked_turn110a": unblocked_turn, "repeat_put110a": repeat_put, "note_put110a": note_put, "bind110a": bind, "end_combat_phase110a": end_combat_phase, "snow110a": snow,
              "exiled_power_damage110a": exiled_power_damage, "exile_hands110a": exile_hands}
