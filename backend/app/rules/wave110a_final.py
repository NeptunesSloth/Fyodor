"""-- wave 110A final pass -- exact wordings of the last PARTIAL cards of the bucket, read onto existing machinery.

* Damping Engine (116.2d, 601.3, 305.1): the static is a cast_limit (who "each", mostperm110a) that engine.play_land_problem also reads; the sacrifice that ignores it
  is the special action ``end_effect`` (licids): any time its player has priority, no stack, once per turn per Engine (ruling 2008-08-01), only while it applies.
* Ice Cave (118.12 / 101.4 / 107.3h): each player but the caster is offered, in turn order, the mana cost of the spell on the stack (its X as chosen)."""
from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.plan import Plan

DAMPING = ("A player who controls more permanents than each other player can't play lands or cast artifact, creature, or enchantment spells. "
           "That player may sacrifice a permanent of their choice for that player to ignore this effect until end of turn.")
TYPES = frozenset({"Artifact", "Creature", "Enchantment"})
GORGER = ("Whenever ~ attacks, exile up to one card of each card type from defending player's graveyard. Put a +1/+1 counter on ~ for each card exiled this way.")
ULDAROS = ("When ~ enters, if you cast ~, exile up to one target nonland card of each card type from your graveyard. Copy those cards. "
           "You may cast any number of spells with total mana value 6 or less from among the copies without paying their mana costs.")
INTIMATIONS_SPELL = ("Each opponent sacrifices a creature or planeswalker of their choice, then discards a card. "
                     "You return a creature or planeswalker card from your graveyard to your hand, then draw a card.")
INTIMATIONS_CAST = ("When you cast a Bolas planeswalker spell, exile this card from your graveyard. That planeswalker enters with an additional loyalty counter on it.")
MAGMARCH = ("Whenever you cast an instant or sorcery spell that targets only a single nonland permanent an opponent controls, if another opponent controls one or more "
            "nonland permanents that spell could target, choose one of those permanents. Copy that spell. The copy targets the chosen permanent.")
THREEFOLD = "Each spell you cast that's exactly three colors has replicate {3}."
DEIF_CHOICE = "As ~ enters, choose a planeswalker type."
DEIF_HEXPROOF = "Planeswalkers you control of the chosen type have hexproof."
DEIF_LOYALTY = ("As long as you control a creature, if damage dealt to a planeswalker you control of the chosen type would result in all loyalty counters on it being removed, "
                "instead all but one of those counters are removed.")
PW_LABEL = "Chosen planeswalker type"
VISIONARY = "When you play a card exiled with ~, transform ~."
PROWL_ATTACK = "Whenever ~ attacks, exile up to one other target tapped creature or Vehicle. For as long as that card remains exiled, its owner may play it."
PROWL_PLAY = "Whenever a player plays a card exiled with ~, you draw a card and transform ~."  # (self_text reads "convert" as "transform", the same action: ruling 2022-10-14)
ICE_CAVE = "Whenever a player casts a spell, any other player may pay that spell's mana cost. If a player does, counter the spell."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if text == PROWL_ATTACK:  # 607.2a: the exile is Prowl's linked one; 305.1 / 601.3: the card's owner (not Prowl's controller) may play it while it stays exiled (grant_play "owner")
        d = scripts.define(replace(ability, text="Whenever ~ attacks, exile up to one other target tapped creature or Vehicle."), ch)
        if d is None or [e["do"] for e in d["effects"]] != ["exile"]:
            return None
        return {**d, "effects": [{**d["effects"][0], "as": "prowl_exiled110a"}, {"do": "grant_play", "who": "ref:prowl_exiled110a", "play": True, "cast": True, "until": "permanent", "owner": True}]}
    if text == PROWL_PLAY:
        d = scripts.define(replace(ability, text="Whenever a player plays a land or casts a spell, you draw a card and transform ~."), ch)
        if d is None or d["cond"].get("event") != "either" or len(d["cond"]["conds"]) != 2:
            return None
        return {**d, "cond": {**d["cond"], "conds": [{**c, "exiled_with110a": True} for c in d["cond"]["conds"]]}}
    if text == VISIONARY:  # a play is a land play or a cast (305.1, 601.1), of a card exiled with it: the played card's previous object is in its link record (triggers.py)
        d = scripts.define(replace(ability, text="Whenever you play a land or cast a spell, transform this creature."), ch)
        if d is None or d["cond"].get("event") != "either" or len(d["cond"]["conds"]) != 2:
            return None
        return {**d, "cond": {**d["cond"], "conds": [{**c, "exiled_with110a": True} for c in d["cond"]["conds"]]}}
    if text == DEIF_CHOICE:  # 614.12a: the choice is made before it enters, recorded on it like a chosen creature type
        return {"kind": "replacement", "replacement": "enters_choice", "effects": [{"do": "choose_value", "who": "you", "what": "planeswalker type", "remember": True}]}
    if text == DEIF_HEXPROOF:  # 205.3j: the chosen planeswalker type, read by selectors.matches ("chosen_pw110a")
        from app.rules import selectors

        d = scripts.define(replace(ability, text="Other creatures you control have hexproof."), ch)
        if d is None or d.get("static") != "grant":
            return None
        return {**d, "who": selectors.Selector(types=("Planeswalker",), controller="you", extras=("chosen_pw110a",)).key()}
    if text == DEIF_LOYALTY:  # read by replace.apply_damage (deification)
        return {"kind": "static", "static": "deification110a", "effects": []}
    if text == THREEFOLD:  # 702.56a, ruling 2022-04-29: the same grant as Hatchery Sliver's (wave110a_grants.with_replicate) for spells of exactly three colors (105.1)
        from app.rules import selectors

        sel = selectors.parse("spell")
        return None if sel is None else {"kind": "static", "static": "spell_replicate110a", "kw": "Replicate {3}", "effects": [],
                                         "filter": replace(sel, compare=(("color_count", "==", 3),)).key()}
    if text == MAGMARCH:  # the intervening "if" is read as it triggers (cond other_opp110a, triggers.py) and as it resolves (the primitive)
        d = scripts.define(replace(ability, text="Whenever you cast an instant or sorcery spell that targets only a single nonland permanent an opponent controls, "
                                                 "copy that spell. You may choose new targets for the copy."), ch)
        if d is None or [e["do"] for e in d["effects"]] != ["copy_spell", "copy_new_targets"] or d["cond"].get("event") != "cast":
            return None
        return {**d, "cond": {**d["cond"], "other_opp110a": True}, "effects": [{"do": "magmarch110a"}]}
    if text == INTIMATIONS_CAST:  # 113.6m: it works from the graveyard (the "self_gy" exile); 614.1c: the Bolas planeswalker spell gets one more loyalty counter as it enters
        d = scripts.define(replace(ability, text="When you cast a Bolas planeswalker spell, return this card from your graveyard to your hand."), ch)
        if d is None or [e["do"] for e in d["effects"]] != ["return_card"]:
            return None
        return {**d, "effects": [{"do": "exile", "who": "self_gy"}, {"do": "loyalty_rider110a", "who": "event_spell"}]}
    if text == GORGER:  # one card of each card type: a single choice, checked as one card per type (the primitive below)
        d = scripts.define(replace(ability, text="Whenever this creature attacks, exile all cards from defending player's graveyard. "
                                                 "Put a +1/+1 counter on this creature for each card exiled this way."), ch)
        if d is None or [e["do"] for e in d["effects"]] != ["exile", "add_counters"]:
            return None
        return {**d, "effects": [{**d["effects"][0], "do": "exile_one_per_type110a"}, *d["effects"][1:]]}
    if text == ULDAROS:  # 115.3: one "target" word, so no card twice; one group per card type (Land excluded by "nonland")
        d = scripts.define(replace(ability, text="When ~ enters, if you cast him, exile up to one target nonland card from your graveyard. Copy that card. "
                                                 "You may cast the copy without paying its mana cost."), ch)
        if d is None or [e["do"] for e in d["effects"]] != ["only_if", "exile", "copy_cards", "free_cast"] or len(d["targets"]) != 1:
            return None
        base = json.loads(d["targets"][0]["what"][4:])
        kinds = ("Artifact", "Battle", "Creature", "Enchantment", "Instant", "Kindred", "Planeswalker", "Sorcery")
        fx = [dict(e) for e in d["effects"]]
        fx[1]["who"] = "all_targets"
        fx[3] = {**fx[3], "mv_total": 6, "n": 99}
        return {**d, "effects": fx, "targets": [{"what": "sel:" + json.dumps({**base, "types": [t]}, separators=(",", ":"), sort_keys=True), "min": 0, "max": 1,
                                                  "distinct_from": list(range(i))} for i, t in enumerate(kinds)]}
    if text == DAMPING:
        return {"kind": "static", "static": "cast_limit", "who": "each", "when": None, "filter": None, "from": None, "act": None, "max": None, "mostperm110a": True, "effects": []}
    if text == ICE_CAVE:
        d = scripts.define(replace(ability, text="Whenever a player casts a spell, any opponent may pay {1}. If a player does, counter that spell."), ch)
        if d is None or [(e["do"], e.get("who"), e.get("cost")) for e in d["effects"]] != [("each_may", "each_opponent", "{1}")]:
            return None
        return {**d, "effects": [{**d["effects"][0], "who": "each_other_than_event", "cost": "{1}", "spell_cost110a": True}]}
    return None


def _count(state: GameState, player: str) -> int:
    return sum(1 for c in state.cards.values() if c.zone.endswith(":battlefield") and c.controller == player)


def ignoring(state: GameState, player: str, src: CardInstance) -> bool:
    r = state.rules
    return r is not None and any(x["what"] == "damping110a" and x["player"] == player and x["src"] == r.object_id(src.id) and x["turn"] == state.turn.number for x in r.results)


def applies(state: GameState, src: CardInstance, player: str) -> bool:
    """601.3 / 305.1: ``player`` controls strictly more permanents than each other player still in the game, and has not paid to ignore this Engine this turn."""
    from app.rules.plan import live_players

    others = [p for p in live_players(state) if p != player]
    mine = _count(state, player)
    return player in live_players(state) and bool(others) and all(mine > _count(state, p) for p in others) and not ignoring(state, player, src)


def cast_hit(state: GameState, src: CardInstance, player: str, types: Any) -> bool:
    return bool(TYPES & set(types)) and applies(state, src, player)


def land_barred(state: GameState, info: Any, player: str) -> CardInstance | None:
    from app.rules import cast_limits

    return next((src for src, d in cast_limits._statics(state, info, "cast_limit") if d.get("mostperm110a") and applies(state, src, player)), None)


def is_engine(plan: Plan, card: CardInstance) -> bool:
    from app.rules import scripts

    return card.zone.endswith(":battlefield") and any(d.get("mostperm110a") for d in scripts.definitions(plan.ch(card)).values())


def sacrifice_start(plan: Plan, card: CardInstance) -> None:
    """The special action's cost: choose a permanent (of the player's own) to sacrifice, then it is sacrificed and the Engine is ignored until end of turn."""
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    me = plan.actor
    if not applies(plan.state, card, me):
        raise ActionError(f"{card.name} does not stop you now")
    options = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == me]
    decide(plan, player=me, kind="choose_cards", prompt=f"{card.name}: sacrifice a permanent to ignore it until end of turn",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Permanent", card_id=c) for c in options], min_choices=1, max_choices=1,
           resume={"step": "damping110a", "engine": card.id})


def resume_sacrifice(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    src = plan.state.cards[d.resume["engine"]]
    me = d.player
    effects._sacrifice_cards(plan, chosen, me)
    turn = plan.state.turn.number
    plan.rules.results = [x for x in plan.rules.results if x["turn"] == turn]
    plan.rules.results.append({"player": me, "what": "damping110a", "src": plan.oid(src), "turn": turn})
    plan.note(f"{plan.name(me)} sacrifices a permanent to ignore {src.name} until end of turn", [src.id], actor=me)
    plan.rules.passed = []


def _copyable(plan: Plan, spell: str, oid: str) -> tuple[Any, list[Any], Any] | None:
    from app.rules import copying, targets

    card = plan.state.cards.get(spell)
    entry = copying.source_entry102(plan, card, oid) if card is not None else None
    if card is None or entry is None or not copying.positions(entry) or copying.uncopyable(plan, card, object_id=oid) is not None:
        return None
    return entry, copying.positions(entry), targets.source_of(plan, spell, True, object_id=oid)


def other_opponents_permanents(plan: Plan, spell: str, oid: str, caster: str) -> list[str]:
    """Magmarch: the nonland permanents of the opponents other than the one whose permanent the spell targets that the spell could target (115.1, 707.10c)."""
    from app.rules import copying, targets

    found = _copyable(plan, spell, oid)
    if found is None or not found[0].targets:
        return []
    entry, positions, source_ch = found
    first = plan.state.cards.get(entry.targets[0].id)
    if first is None:
        return []
    return [c.id for c in plan.state.cards.values()
            if c.zone.endswith(":battlefield") and c.controller not in (caster, first.controller) and "Land" not in plan.ch(c).types and plan.in_game(c)
            and all(c.id in targets.legal_targets(plan, copying._spec(entry, p).get("what", "any"), caster, source_ch, spell, source_object=entry.source_object)
                    for p in positions)]


def other_opponent_could(plan: Plan, watcher: CardInstance, spell: CardInstance) -> bool:
    return bool(other_opponents_permanents(plan, spell.id, str(plan.oid(spell)), watcher.controller))


def magmarch(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Exterminator Magmarch (ruling 2024-06-07): the copy is created on the stack (not cast), even if the original was countered; modes and X are copied; nothing is
    done when no other opponent has a permanent the spell could target as this resolves. 707.10: the caster chooses the one permanent the copy targets."""
    from app.game.rules_state import DecisionOption
    from app.rules import copying, targets
    from app.rules.plan import decide

    found = next(iter(copying._copy_sources(plan, ctx, "event_spell")), None)
    if found is None:
        return True
    legal = other_opponents_permanents(plan, found[0], found[1], ctx["controller"])
    if not legal:
        return True
    if len(legal) > 1:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt="Exterminator Magmarch: choose the permanent the copy targets",
               options=[DecisionOption(id=t, label=targets.label(plan, t), card_id=t) for t in legal], resume={"step": "magmarch110a", "ctx": ctx, "spell": found})
        return False
    return _copy_for(plan, ctx, found, legal[0])


def _copy_for(plan: Plan, ctx: dict[str, Any], found: Any, target: str) -> bool:
    from app.rules import copying, spell_copy_replacements

    return copying._each_run(plan, {"ctx": ctx, "spell": found[0], "oid": found[1], "controller": ctx["controller"], "victims": [target],
                                    "additional": spell_copy_replacements.additional(plan, ctx["controller"])})


def resume_magmarch(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    if _copy_for(plan, d.resume["ctx"], d.resume["spell"], chosen[0]):
        effects.continue_effects(plan, d.resume["ctx"])


def loyalty_rider(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The planeswalker spell the cast trigger is about gets one more loyalty counter as it enters (the creature riders' record, cast_riders.spell_rider)."""
    from app.rules import cast_riders

    return cast_riders.spell_rider(plan, ctx, {"do": "spell_rider", "who": "event_spell", "riders": [{"kind": "loyalty110a"}]})


def entering_loyalty(plan: Plan, card: CardInstance) -> int:
    """Additional loyalty counters a planeswalker spell was given as it was cast (Dark Intimations, 614.1c): one per rider on its payment record."""
    from app.rules import mana_units

    rec = mana_units.record_of(plan, card)
    return 0 if rec is None else sum(1 for r in rec.mana_riders if r["kind"] == "loyalty110a")


def pw_options(plan: Plan) -> list[str]:
    """205.3j: every planeswalker type (the known ones and any a planeswalker in this game has)."""
    from app.rules import selectors

    found = set(selectors.PLANESWALKER_TYPES)
    for c in plan.state.cards.values():
        if "Planeswalker" in plan.ch(c).types:
            found |= plan.ch(c).subtypes
    return sorted(found)


def chosen_pw(plan: Plan, card: CardInstance, ch: Any, source: str | None) -> bool:
    src = plan.state.cards.get(source or "")
    kind = src.choices.get(PW_LABEL) if src is not None else None
    return bool(kind) and kind in ch.subtypes


def deification(plan: Plan, walkers: dict[str, int]) -> None:
    """Deification (rulings 2023-05-12): damage is still dealt (lifelink and the like happen); only the loyalty removal changes, from all counters to all but one, for a
    planeswalker its controller has of the chosen type while they control a creature."""
    from app.rules import scripts

    for key, n in walkers.items():
        card = plan.state.cards.get(key)
        have = card.counters.get("loyalty", 0) if card is not None else 0
        if card is None or not have or n < have:
            continue
        ch = plan.ch(card)
        if any(src.controller == card.controller and src.zone.endswith(":battlefield") and chosen_pw(plan, card, ch, src.id)
               and any(d.get("static") == "deification110a" for d in scripts.definitions(plan.ch(src)).values())
               and any(c.controller == card.controller and c.zone.endswith(":battlefield") and plan.ch(c).is_creature for c in plan.state.cards.values())
               for src in plan.state.cards.values()):
            walkers[key] = have - 1


def _assignable(plan: Plan, cards: list[str]) -> bool:
    """One card of each card type: every card is given a card type it has, no type twice (a card with two types serves for one of them)."""
    from app.rules.characteristics import CARD_TYPES

    owner: dict[str, str] = {}

    def place(c: str, seen: set[str]) -> bool:
        for t in plan.ch(plan.state.cards[c]).types & CARD_TYPES:
            if t not in seen:
                seen.add(t)
                if t not in owner or place(owner[t], seen):
                    owner[t] = c
                    return True
        return False

    return all(place(c, set()) for c in cards)


def one_per_type(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Grime Gorger: its controller chooses up to one card of each card type among the graveyard cards (608.2d); a card with two types takes up one of them."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    pool = effects._cards(plan, ctx, e["who"])
    if not pool:
        return effects.exile_cards(plan, ctx, {k: v for k, v in e.items() if k != "who"}, [])
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt="Exile up to one card of each card type from the graveyard", min_choices=0, max_choices=len(pool),
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in pool],
           resume={"step": "exile_one_per_type110a", "ctx": ctx, "e": e})
    return False


def resume_one_per_type(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    if not _assignable(plan, chosen):
        raise ActionError("Choose at most one card of each card type")
    ctx = d.resume["ctx"]
    effects.exile_cards(plan, ctx, {k: v for k, v in d.resume["e"].items() if k != "who"}, chosen)
    effects.continue_effects(plan, ctx)


def choose_order(plan: Plan, ctx: dict[str, Any], frame: dict[str, Any]) -> bool:
    """Chaotic Transformation (ruling 2022-09-09): when its controller has several of the exiled permanents left to consider, they choose which one is next (a decision, True)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    rest = frame["rows"][frame["next"]:]
    same = [r for r in rest if r["controller"] == rest[0]["controller"]]
    if len(same) < 2 or frame.get("asked") == frame["next"]:
        return False
    decide(plan, player=rest[0]["controller"], kind="choose_cards", prompt="Chaotic Transformation: choose which exiled permanent to consider next",
           options=[DecisionOption(id=r["object"], label=r["name"] or "Permanent") for r in same], min_choices=1, max_choices=1,
           resume={"step": "chaotic_order110a", "ctx": ctx})
    return True


def resume_order(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    ctx = d.resume["ctx"]
    frame = ctx["polymorph102"]
    i = frame["next"]
    pick = next(j for j in range(i, len(frame["rows"])) if frame["rows"][j]["object"] == chosen[0])
    frame["rows"].insert(i, frame["rows"].pop(pick))
    frame["asked"] = i
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "polymorph_walk102"}]
    continue_effects(plan, ctx)


REWRITES = {INTIMATIONS_SPELL: INTIMATIONS_SPELL.replace("You return", "Return")}  # (the grammar has no "you return"; 101.4 / the 2017-02-09 ruling: opponents choose in turn order, all at once)
PRIMITIVES: dict[str, Any] = {"magmarch110a": magmarch, "loyalty_rider110a": loyalty_rider, "exile_one_per_type110a": one_per_type}
RESUME: dict[str, Any] = {"damping110a": resume_sacrifice, "chaotic_order110a": resume_order, "exile_one_per_type110a": resume_one_per_type, "magmarch110a": resume_magmarch}
