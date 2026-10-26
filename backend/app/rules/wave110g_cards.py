"""-- wave 110G -- exact Oracle wordings of single cards, read as a wording the grammar reads or built from parts of it (as wave110b_cards)."""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import replace
from typing import Any

Def = dict[str, Any]


def _keep_revealed(d: Def) -> Def:
    """The first choice leaves the rest of the revealed hand revealed for the second (701.20a)."""
    first = next(e for e in d["effects"] if e["do"] == "choose_from_hand")
    first["keep110g"] = True
    return d


def _controlled_since_turn_start(d: Def) -> Def:
    """"Except for creatures the player hasn't controlled continuously since the beginning of the turn": only those controlled since then are destroyed."""
    from app.rules import controller_turn_history69, selectors

    eff = d["effects"][0]
    head, _, key = eff["who"].partition("|sel:")
    sel = selectors.from_key("sel:" + key)
    return {**d, "effects": [{**eff, "who": f"{head}|" + replace(sel, extras=(*(("didnt_attack_combat110g" if x == "didnt_attack_this_turn" else x) for x in sel.extras), controller_turn_history69.EXTRA)).key()}]}


def _battles(d: Def) -> Def:
    """"...and each battle they protect": a second damage effect to the battles an opponent protects (310.8)."""
    from app.rules import selectors

    sel = replace(selectors.from_key('sel:{"types":["Battle"]}'), extras=("protected_by_opp110g",))
    return {**d, "effects": [*d["effects"], {**d["effects"][0], "who": sel.key()}]}


def _any_shuffle(d: Def) -> Def:
    """Psychogenic Probe: any player's shuffle (701.24), not just an opponent's."""
    return {**d, "cond": {**d["cond"], "player": "any"}}


def _shuffler_puts_back(d: Def) -> Def:
    """Widespread Panic: the shuffling player (the trigger's event player) puts the card back, not each opponent."""
    return {**_any_shuffle(d), "effects": [{**d["effects"][0], "who": "event_player"}]}


def _twin(d: Def) -> Def:
    """The token is named Twin and copies the attacker's power and toughness once, as it is created (111.1)."""
    token = d["effects"][0]["token"]
    token.update(name="Twin", toughness={"toughness": "self"})
    return d


def _pay_life_reveal(d: Def) -> Def:
    """Pay any amount of life (119.4, 0 up to the life total), then reveal that many cards (701.20a): the payment's amount sizes the reveal."""
    pay = {"do": "optional_payment", "who": "you", "cost": "", "bind": "viz110g", "choose_x": {"max": {"life": "you"}, "life": True}}
    reveal, *rest = d["effects"]
    return {**d, "effects": [pay, {**reveal, "n": {"paid_x": "viz110g"}}, *rest]}


def _walls_only(d: Def) -> Def:
    return {**d, "if": {"w110g": "walls_block"}}


def walls_block(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    """509.1g / 509.3b: another Wall blocks the attacker this creature blocks, and every creature blocking it is a Wall."""
    attacker = ((ctx.get("event") or {}).get("other") or {}).get("card")
    blockers = [c for c in plan.state.cards.values() if attacker and c.blocks(attacker)]
    return any(c.id != ctx.get("source_card") for c in blockers) and all("Wall" in plan.ch(c).subtypes for c in blockers)


def opponent_protects(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    """310.8: the targeted battle's protector is an opponent of the ability's controller."""
    from app.rules import battles

    return any((p := battles.protector(plan.state, c)) is not None and p != ctx["controller"]
               for t in ctx.get("targets") or [] if t and (c := plan.state.cards.get(t["id"])) is not None)


def exploited_big(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    """702.110b / 608.2h: the exploited creature, as it last existed, had power 3 or greater."""
    from app.rules import context

    got = context.info(plan, ctx, context.EVENT_OTHER)
    return bool(got and got[1].pt and got[1].pt[0] >= 3)


def other_targetable(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    """Beamsplitter Mage, 603.4: you control another creature the cast spell could target (as it triggers; again as it resolves, the spell still on the stack)."""
    from app.rules import copying

    spell = next(iter(copying._stack_objects(plan, ctx, "event_spell")), None)
    entry = plan.rules.stack.get(spell) if spell else None
    return entry is not None and bool(copying._each_victims(plan, ctx, ctx["controller"], entry))


def emerge_sacrifice(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    """Foul Emissary: the sacrificed creature was the cost of casting a spell with emerge (702.119a, 701.21a)."""
    oid = next((o["object_id"] for o in (ctx.get("event") or {}).get("objects") or []), None)
    return any(r.alternative == "emerge" and oid in r.sacrificed_objects for r in plan.rules.payments.values())


def shares_with_exiled(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    """Thought Prison: the spell cast has a color or a mana value in common with the card this artifact exiled (105.2, 202.3)."""
    from app.rules import context, exiled_with

    exiled = exiled_with.cards(plan, ctx)
    if not exiled:
        return False
    other = plan.ch(plan.state.cards[exiled[0]])
    return any((mine := plan.ch(plan.state.cards[c])) and (set(mine.colors) & set(other.colors) or mine.mana_value == other.mana_value)
               for c in context.objects(plan, ctx, context.EVENT))


def hand_began_empty(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    """The controller had no cards in hand as this turn began (an unknown receipt, turn one or an old save, reads the hand now)."""
    began = plan.state.turn.starting_hand
    you = ctx["controller"]
    return (began[you] if began is not None and you in began else len(plan.state.zones.get(f"{you}:hand", []))) == 0


def combat_alone(plan: Any, e: Any, snap: Any) -> str | None:
    """506.5: a creature that left was attacking (blocking) alone when no other creature, on the battlefield or leaving with it, was attacking (blocking)."""
    for attr in ("attacking", "blocking"):
        if getattr(snap, attr, False) and not any(
                c.id != snap.card and c.zone.endswith(":battlefield") and (c.is_attacking if attr == "attacking" else c.is_blocking) for c in plan.state.cards.values()) \
                and not any(x.kind == "zone_change" and x.batch == e.batch and x.object_id and x.object_id != e.object_id
                            and getattr(plan.rules.lki.get(x.object_id), attr, False) for x in plan.rules.events):
            return attr
    return None


def alone_in_combat(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    ev = ctx.get("event")
    return (ev.get("combat_alone110g") if isinstance(ev, dict) else getattr(ev, "combat_alone110g", None)) is not None


def holds(plan: Any, ctx: dict[str, Any], cond: Def) -> bool:
    return bool({"walls_block": walls_block, "opp_protects": opponent_protects, "exploited_big": exploited_big,
                   "hand_began_empty": hand_began_empty, "other_targetable": other_targetable, "emerge_sacrifice": emerge_sacrifice, "shares_with_exiled": shares_with_exiled, "alone_in_combat": alone_in_combat}[cond["w110g"]](plan, ctx, cond))


def _crown(d: Def) -> Def:
    empty = {"w110g": "hand_began_empty"}
    draw, hurt = d["effects"]
    return {**d, "effects": [{"do": "only_if", "cond": empty, "skip": 1}, draw, {"do": "only_if", "cond": {"not": empty}, "skip": 1}, hurt]}


def _treasure_if_big(d: Def) -> Def:
    """Henry Wu: the Treasure sentence is gated on the exploited creature's power."""
    fx = d["effects"]
    return {**d, "effects": [*fx[:-1], {"do": "only_if", "cond": {"w110g": "exploited_big"}, "skip": 1}, fx[-1]]}


_WARP_BOTTOM = "Put target exiled card with warp on the bottom of its owner's library."
_JUDOON = ("You may exile a Human you control and an artifact you control. If you do, search your library for a Doctor card, put it onto the battlefield, "
           "then shuffle.")
_INFERNAL = ("Choose an opponent. You and that player each sacrifice a creature. Each player who sacrificed a creature this way draws two cards.")
_REANIMATE = ("Choose an opponent. Return a creature card from your graveyard to the battlefield, then that player returns a creature card from their graveyard "
              "to the battlefield.")
_BARGE = ("Target creature gains islandwalk until end of turn. When ~ leaves the battlefield this turn, destroy that creature. "
          "A creature destroyed this way can't be regenerated.")
_MOONGLOVE = ("Target creature you control gets +1/+0 and gains deathtouch until end of turn. "
              "Whenever a creature dealt damage by that creature dies this turn, its controller loses 2 life.")
_EYE = ("The next time a source of your choice would deal damage to you this turn, instead that source deals that much damage to you and "
        "~ deals that much damage to that source's controller.")
_SUN1 = ("Remove all counters from target creature. It can't have counters put on it for as long as this creature remains on the battlefield.")
_SUN2 = ("Target opponent loses all counters. That player can't get counters for as long as this creature remains on the battlefield.")
SUN_KEY = "Suncleanser110g"
_SWING = ("Choose target battle. If an opponent protects it, remove three defense counters from it. Otherwise, put three defense counters on it.")


_CULTIST = "The next time damage would be dealt to target creature this turn, destroy that creature instead."
_FREE_PLAY = ("Target player exiles the top card of their library. Until that player's next end step, they may play that card without paying its mana cost.")
_PREPARE = {"Target creature becomes prepared.": "prepare", "Target creature becomes unprepared.": "unprepare100f"}
_AGONY = re.compile(r"(~ deals X damage to target creature, where X is the number of colors of mana spent to cast this spell\.) Exile cards from the top "
                    r"of your library equal to the excess damage dealt to that creature this way\. You may play those cards until the end of your next turn\.")


def parse(body: str) -> Any:
    """Etched Host Doombringer's mode: one target battle; the protector decides between removing and adding (310.4, 310.8)."""
    from app.rules import scripts

    if body.strip() == _WARP_BOTTOM:  # Blade of the Swarm: an exiled card that has warp (702.185a), any exile
        return scripts.parse_effects(_WARP_BOTTOM.replace("exiled card with warp", "card with warp in exile"))
    if body.strip() == _JUDOON:  # Fugitive of the Judoon III: both exiled together or nothing (paid as one cost, 118.3)
        return scripts.parse_effects(_JUDOON.replace("a Human you control and an artifact", "a Human you control and exile an artifact"))
    if body.strip() == _INFERNAL:  # Infernal Offering mode 1: the controller and the chosen opponent sacrifice together (101.4, 701.21a)
        got = scripts.parse_effects("Choose an opponent. Each player sacrifices a creature. "
                                    "Each player who sacrificed a creature this way draws two cards.")
        if got is None:
            return None
        (pick, sac, *rest), target, optional = got
        return [{**pick, "as": "e0"}, {**sac, "do": "sacrifice_pair110g", "who": "ref:e0"}, *rest], target, optional
    if body.strip() == _REANIMATE:  # Infernal Offering mode 2: "then" is a sequence, as the grammar reads two sentences
        return scripts.parse_effects("Choose an opponent. Return a creature card from your graveyard to the battlefield. "
                                     "That player returns a creature card from their graveyard to the battlefield.")
    if body.strip() == _BARGE:  # War Barge: the 'leaves' trigger belongs to the artifact (self), its effect to the ability's target (603.7c)
        from app.rules import bound_delayed_effects as bound
        from app.rules import language

        group = language.target_group("target creature")
        if group is None:
            return None
        return [{"do": "grant", "who": "target", "keywords": ["islandwalk"]},
                *bound._event("leave", "self", [{"do": "destroy", "who": "target"}, {"do": "no_regen"}])], [group], False
    if body.strip() == _MOONGLOVE:  # Touch of Moonglove: a turn-long watch on every death; delayed.on_events keeps those the target damaged (120.3, 603.7c)
        got = scripts.parse_effects("Target creature you control gets +1/+0 and gains deathtouch until end of turn.")
        if got is None:
            return None
        effects, target, optional = got
        return [*effects, {"do": "delayed", "when": {"kind": "event", "event": "die", "damager110g": True}, "n": 1, "who": "target", "this_turn": True,
                           "once": False}, {"do": "deferred:lose_life", "who": "ref:event.controller", "n": 2}], target, optional
    if (flat := body.strip().replace("~", "this creature")) in (_SUN1, _SUN2):  # Suncleanser: 122.1, 614.17; the mark lives on the source until it leaves (400.7)
        from app.rules import language

        group = language.target_group("target creature" if flat == _SUN1 else "target opponent")
        if group is None:
            return None
        if flat == _SUN2:
            return [{"do": "suncleanser110g", "who": "target", "player": True}], [group], False
        (remove,), _, _ = scripts.parse_effects("Remove all counters from target creature.")  # type: ignore[misc]
        return [remove, {"do": "suncleanser110g", "who": "target"}], [group], False
    if body.strip() == _EYE:  # Eye for an Eye: a chosen source (609.7a); its damage to you is still dealt, then ~ deals that much to its controller (615.5-like rider)
        return [{"do": "source_shield", "props": {}, "once": True, "to": "you", "observe110g": True,
                 "rider": {"if": False, "aggregation": "batch", "effects": [{"do": "damage", "who": "ref:from_ctrl", "src": "self",
                                                                             "n": {"ref_amount": "that_damage"}}]}}], None, False
    if body.strip() == _CULTIST:  # Kill-Suit Cultist: the target creature, chosen now
        from app.rules import language

        group = language.target_group("target creature")
        return None if group is None else ([{"do": "destroy_instead110g", "who": "target"}], [group], False)
    if body.strip() == _FREE_PLAY:  # Casey & Raph: the targeted player (the cards' owner) plays the exiled card free until their own next end step (611.2a)
        got = scripts.parse_effects("Target player exiles the top card of their library. Until your next end step, you may play that card without paying its mana cost.")
        if got is None:
            return None
        (top, play), target, optional = got
        return [top, {**play, "owner": True}], target, optional
    if (prep := _PREPARE.get(body.strip())) is not None:  # Biblioplex Tomekeeper: 722.3a / 722.3b on the target creature
        from app.rules import language

        group = language.target_group("target creature")
        return None if group is None else ([{"do": prep, "who": "target"}], [group], False)
    if (agony := _AGONY.fullmatch(body.strip())) is not None:  # Archaic's Agony: excess damage (120.10) sizes the exile
        got = scripts.parse_effects(f"{agony[1]} You gain life equal to the excess damage dealt to that creature this way.")
        if got is None:
            return None
        (hit, _life), target, optional = got
        (top, play), _, _ = scripts.parse_effects("Exile the top 3 cards of your library. You may play those cards until the end of your next turn.")  # type: ignore[misc]
        return [hit, {**top, "n": {"ref_amount": "excess_dealt"}}, play], target, optional
    if body != _SWING:
        return None
    (remove,), target, optional = scripts.parse_effects("Remove three defense counters from target battle.")  # type: ignore[misc]
    (add,), _, _ = scripts.parse_effects("Put three defense counters on target battle.")  # type: ignore[misc]
    opp = {"w110g": "opp_protects"}
    gate = lambda cond: {"do": "only_if", "cond": cond, "skip": 1}  # noqa: E731 - a failed condition skips the next effect
    return [gate(opp), remove, gate({"not": opp}), add], target, optional


def _exchange_power(d: Def) -> Def:
    """701.12g: exchanging two powers makes a continuous effect setting each (613.4b) to the other's previous value."""
    return {**d, "effects": [{"do": "exchange_power110g", "duration": "end_of_combat"}]}


def _lowest_life_control(d: Def) -> Def:
    """Loxodon Peacekeeper: the player with the lowest life total gains control; the controller picks among ties."""
    return {**d, "effects": [{"do": "lowest_life_control110g"}]}


# whole ability text -> the wording the grammar reads for it
_AS: dict[str, str] = {
    # Elemental Expressionist: one clause granting two quoted abilities is two grants of the same target; "is put into exile" of a granted ability is
    # exile from the battlefield (the grant ends when the creature leaves, 400.7; the replacement exiles it from there)
    "Magecraft \u2014 Whenever you cast or copy an instant or sorcery spell, choose target creature you control. Until end of turn, it gains \"If this creature would leave the battlefield, exile it instead of putting it anywhere else\" and \"When this creature is put into exile, create a 4/4 blue and red Elemental creature token.\"":
        "Magecraft \u2014 Whenever you cast or copy an instant or sorcery spell, choose target creature you control. Until end of turn, it gains \"If this creature would leave the battlefield, exile it instead of putting it anywhere else.\" Until end of turn, it gains \"When this creature is put into exile from the battlefield, create a 4/4 blue and red Elemental creature token.\"",
    # Savior of Ollenbock: a creature on the battlefield or a creature card in a graveyard is "creature or creature card in a graveyard";
    # "the exiled cards" return to the battlefield (607.2a link, 610.3)
    "When this creature leaves the battlefield, put the exiled cards onto the battlefield under their owners' control.":
        "When this creature leaves the battlefield, return the exiled cards to the battlefield under their owners' control.",
    # Carry Away: the Aura only enchants Equipment, so "enchanted permanent" is the enchanted Equipment
    "You control enchanted Equipment.": "You control enchanted permanent.",
    # Wormfang Drake: "a creature you control other than this creature" is "another creature you control"
    "When this creature enters, sacrifice it unless you exile a creature you control other than this creature.":
        "When this creature enters, sacrifice it unless you exile another creature you control.",
    # Portcullis: "two or more other creatures" is three or more with the entering one; the card returns when the artifact leaves (610.3)
    "Whenever a creature enters, if there are two or more other creatures on the battlefield, exile that creature. Return that card to the battlefield "
    "under its owner's control when this artifact leaves the battlefield.":
        "Whenever a creature enters, if there are three or more creatures on the battlefield, exile it until this artifact leaves the battlefield.",
    # Acquisitions Expert: the opponent reveals that many cards of their choice (701.20a); "those cards" read as "them"
    "When this creature enters, target opponent reveals a number of cards from their hand equal to the number of creatures in your party. "
    "You choose one of those cards. That player discards that card.":
        "When this creature enters, target opponent reveals a number of cards from their hand equal to the number of creatures in your party. "
        "You choose one of them. That player discards that card.",
}

def _transformed(d: Def) -> Def:
    """Invasion of Pyrulea (back face): the group is transformed permanents (701.27g), not creatures."""
    from app.rules import selectors, zones100g

    return {**d, "who": replace(selectors.from_key(d["who"]), types=(), extras=(zones100g.TRANSFORMED,)).key()}


def _land_or_dfc(d: Def) -> Def:
    """Invasion of Pyrulea: the revealed card is a land card or a double-faced card (711.1)."""
    from app.rules import selectors

    dfc = selectors.Selector(zones=(), card=True, extras=("double_faced_card",)).key()
    fx = [{**e, "cond": {"any": [e["cond"], {**e["cond"], "is": dfc}]}} if e.get("do") == "only_if" else e for e in d["effects"]]
    return {**d, "effects": fx}


def _swap_tapped(d: Def) -> Def:
    """Sands of Time: one simultaneous swap of the tapped and untapped artifacts, creatures and lands of the upkeep's player."""
    return {**d, "effects": [{"do": "swap_tapped110g", "who": "event_player"}]}


def _one_copy(d: Def) -> Def:
    """Beamsplitter Mage: one copy, for the one creature its controller chooses (707.10d, 115.9c); no creature to choose: no copy."""
    gate = {"w110g": "other_targetable"}  # 603.4: an intervening "if": no trigger without such a creature, checked again on resolution
    fx = [{**e, "one": True} if e.get("do") == "copy_each" else e for e in d["effects"]]
    return {**d, "if": gate, "effects": [{"do": "only_if", "cond": gate, "skip": len(fx)}, *fx]}


def _emerge_sacrifice(d: Def) -> Def:
    return {**d, "if": {"w110g": "emerge_sacrifice"}}  # 603.4: an intervening condition, it is a fact of the past when the trigger resolves


def _may(d: Def) -> Def:
    return {**d, "optional": True}  # "you may have …. If you do, …": the whole body hinges on the one choice


def _shares(d: Def) -> Def:
    return {**d, "if": {"w110g": "shares_with_exiled"}}


def _firm(d: Def) -> Def:
    return {**d, "effects": [d["effects"][0], {"do": "firm_creature110g", "who": "target"}, *d["effects"][1:]]}  # Whippoorwill: after the regeneration clause


def _tatsumasa(d: Def) -> Def:
    es = d["effects"]  # token, "when it dies", return: the exiled Equipment (bound as it is in exile) comes back, not the token
    return {**d, "effects": [{"do": "bind_exiled110g", "as": "tatsumasa"}, es[0], es[1], {**es[2], "who": "ref:tatsumasa", "under": "owner"}]}


def _could_attack(d: Def) -> Def:  # Season of the Witch: "except for creatures that couldn't attack" keeps only those that could have been declared
    return {**d, "effects": [{**x, "who": x["who"].replace('"didnt_attack_this_turn"', '"could_attack110g","didnt_attack_this_turn"')} for x in d["effects"]]}


def _alone(d: Def) -> Def:  # Thijarian Witness: the plain "if it was attacking" test, swapped for the 506.5 fact kept with the event
    test = {"w110g": "alone_in_combat"}
    return {**d, "if": test, "effects": [{**x, "cond": test} if x.get("do") == "only_if" else x for x in d["effects"]]}


def _halfdane(d: Def) -> Def:
    return {**d, "effects": [{"do": "halfdane110g"}]}


def _idol_enter(d: Def) -> Def:
    return {**d, "effects": [{"do": "exile_gy_until110g"}]}


def _idol_cast(d: Def) -> Def:
    return {**d, "effects": [{"do": "idol_cast110g"}]}


def _opponent_cause(d: Def) -> Def:
    return {**d, "cond": {**d["cond"], "cause_opp110g": True}}  # Sacred Ground: the move came out of an opponent's resolving spell or ability


# whole ability text -> (the wording the grammar reads, what to change in its definition)
def _imprint_pt(d: Def) -> Def:
    """Phyrexian Ingester: +X/+Y from the imprinted creature card, two statics of one line (613.4c; 607.2a link); no card exiled adds 0."""
    import copy

    def part(proj: str, p: int, t: int) -> Def:
        e = copy.deepcopy(d)
        e["each"] = {"p": p, "t": t, "value": {"linked_pool": {"projection": proj}}}
        return e

    return {**part("power", 1, 0), "also": [part("toughness", 0, 1)]}


def _fallen(d: Def) -> Def:
    """The Fallen: 1 damage at once to the opponents and planeswalkers recorded in RulesState.dealt_to110g for this object (120.3, 400.7)."""
    return {**d, "effects": [{"do": "fallen110g"}, {"do": "damage", "who": "ref:fallen_p", "n": 1, "with_next": True},
                             {"do": "damage", "who": "ref:fallen_c", "n": 1}]}


def _elkin(d: Def) -> Def:
    """Elkin Lair: the exile and the permission are the active player's own (400.3, 601.2a); the graveyard step at the next end step moves what is still that exiled object (400.7)."""
    return {**d, "effects": [{"do": "elkin110g"}, {"do": "delayed", "when": {"kind": "step", "step": "end", "whose": "next"}, "n": 1},
                             {"do": "deferred:return_card", "who": "ref:e0", "to": "graveyard", "under": "owner"}]}


def _no_phase_out(d: Def) -> Def:
    """Ertai's Familiar: the grammar's restriction on itself, with the phase-out prohibition phasing._held reads (702.26)."""
    return {**d, "effects": [{**x, "rules": ["cant_phase_out"]} if x.get("do") == "restrict" else x for x in d["effects"]]}


def _battlefield_or_graveyard(d: Def) -> Def:
    """Savior of Ollenbock: the one target is another creature on the battlefield or a creature card in a graveyard (115.1)."""
    from app.rules import selectors
    from app.rules.conditional_copy_sources import key

    sel = selectors.Selector(zones=("battlefield", "graveyard"), either=(key("another creature"), key("creature card in a graveyard"))).key()
    return {**d, "targets": [{**d["targets"][0], "what": sel}]}


def _hand_or_creature(d: Def) -> Def:
    """Cloak and Dagger, Entwined: reveal the hand, then you may exile a nonland card from it OR the chosen creature until it leaves (610.3)."""
    from app.rules import selectors

    sel = selectors.Selector(card=True, not_types=("Land",), zones=()).key()
    return {**d, "effects": [d["effects"][0], {"do": "choose_from_hand", "who": "you", "sel": sel, "n": 1, "label": "nonland card or creature", "optional": True,
                                               "extra110g": "target:1", "as": "e1"}, {"do": "exile_split110g", "who": "ref:e1"}]}


def exile_split(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """610.3c: exile until the source leaves; a card from a hand goes back to the hand, a permanent back to the battlefield."""
    from app.rules import effects

    if not effects._cards(plan, ctx, "self"):
        return True
    cards = effects._cards(plan, ctx, e["who"])
    for origin in (":hand", ":battlefield"):
        found = [c for c in cards if plan.state.cards[c].zone.endswith(origin)]
        if found:
            effects._exile_until_cards(plan, ctx, {"hand_origin": origin == ":hand"}, found)
    return True


def _land_or_color(land: str, color: str) -> Callable[[Def], Def]:
    """Nature's Wrath: "<Land> or <color> permanent" is a union selector, both for what enters and for what the controller sacrifices."""
    def build(d: Def) -> Def:
        from app.rules import selectors
        from app.rules.conditional_copy_sources import key

        sel = selectors.Selector(either=(key(land), key(f"{color} permanent"))).key()
        return {**d, "cond": {**d["cond"], "sel": sel}, "effects": [{**x, "sel": sel} for x in d["effects"]]}
    return build


def speed_cut(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Spikeshell Harrier: if that opponent's speed is greater than each other player's speed, it drops by 1, never below 1 (702.179f: no speed reads as 0)."""
    from app.rules import effects, speed

    for pid in effects._players(plan, ctx, e["who"]):
        if all(speed.of(plan, pid) > speed.of(plan, o) for o in plan.live() if o != pid) and speed.of(plan, pid) > 1:
            plan.do({"type": "set_resource", "player": pid, "key": speed.KEY, "value": speed.of(plan, pid) - 1}, actor=ctx["controller"])
    return True


_STICKER_KICKER = "Creature spells you cast have sticker kicker {1}."
_KICKERS = {"kicker", "multikicker", "squad", "replicate", "offspring", "entwine"}


def sticker_kicker(state: Any, player: str, card: Any, ch: Any, info: Any) -> Any:
    """702.33h: a creature spell its caster casts has "Kicker {1}" (Wicker Picker); casting.py then gives the ticket and sticker.
    ponytail: a spell with a kicker of its own is not given a second one (two kickers stay unsupported, 702.33b)."""
    if not ch.is_creature or any(_KICKERS & set(a.keywords) for a in ch.abilities):
        return ch
    from app.rules import cast_limits
    from app.rules.characteristics import AbilityText
    from app.rules.permissions import spell_matches

    if not any(src.controller == player and d["keyword"] == "sticker_kicker110g" and spell_matches(state, player, card, ch, d["filter"], info, src.id)
               for src, d in cast_limits._statics(state, info, "spell_helper")):
        return ch
    extra = AbilityText(index=1 + max((a.index for a in ch.abilities), default=99), text="Kicker {1}", kind="keywords", keywords=("kicker",), special="sticker_kicker110g")
    return replace(ch, abilities=(*ch.abilities, extra))


def sticker_kicker_effects() -> list[dict[str, Any]]:
    """702.33h: "you get a ticket counter and you may put a sticker on this spell" (the spell is the source)."""
    return [{"do": "player_counter", "who": "you", "counter": "ticket", "n": 1}, {"do": "put_sticker101", "kind": None, "n": 1, "as": "placed101", "who": "ref:spell110g"}]


def _sticker_pt(d: Def) -> Def:
    """Ambassador Blorpityblorpboop: base P/T become the stickers' totals; no duration, so it lasts (611.2a); a sticker's P/T is its own number (123.?)."""
    e = {**d["effects"][0], "p": {"sticker_pt110g": "power"}, "t": {"sticker_pt110g": "toughness"}, "duration": "permanent"}
    return {**d, "effects": [e], "optional": True}


def _subtype_count(name: str) -> Def:
    return {"value": {"count": f'sel:{{"controller":"you","subtypes":["{name}"]}}'}, "op": ">=", "n": 1}


def _done_for_the_day(d: Def) -> Def:
    """Done for the Day: intervening if (603.4) any of three types; "you may" get {TK} or Treasure = choose up to one mode (700.2); the sticker clause
    checks "all three" on resolution (608.2c)."""
    kinds = ("Employee", "Performer", "Robot")
    get = next(e for e in d["effects"] if e["do"] == "player_counter")
    treasure = {"do": "create_token", "who": "you", "n": 1, "token": {"name": "Treasure", "power": None, "toughness": None, "colors": [],
                "type_line": "Token Artifact \u2014 Treasure", "text": "{T}, Sacrifice this token: Add one mana of any color."}}
    put = {"do": "put_sticker101", "kind": None, "n": 1, "as": "placed101", "sel": 'sel:{"not_types":["Land"],"owner":"you"}'}
    return {**d, "optional": False, "if": {"any": [_subtype_count(k) for k in kinds]}, "effects": [], "target": None,
            "modes": [{"text": "You get {TK}.", "effects": [get], "target": None}, {"text": "Create a Treasure token.", "effects": [treasure], "target": None},
                      {"text": "Do neither.", "effects": [], "target": None}],  # "you may": declining still lets the next sentence happen
            "modal": {"min": 1, "max": 1, "repeat": False, "condition": None, "memory": None, "index": 0, "form": "triggered"},
            "after": [{"do": "only_if", "cond": {"all": [_subtype_count(k) for k in kinds]}, "skip": 1}, put]}


_BUILD: dict[str, tuple[str, Callable[[Def], Def]]] = {
    "At the beginning of your end step, if you control an Employee, a Performer, or a Robot, you may get {TK} or create a Treasure token. If you control all three, you may put a sticker on a nonland permanent you own.":
        ("At the beginning of your end step, if you control a Robot, you may get {TK}.", _done_for_the_day),
    "At the beginning of each combat, you may have Ambassador Blorpityblorpboop's base power become equal to the total power of all stickers on permanents you control and its base toughness become equal to those stickers' total toughness.":
        ("At the beginning of each combat, this creature has base power and toughness 3/3 until end of turn.", _sticker_pt),
    "When this creature enters, return target creature or Vehicle an opponent controls to its owner's hand. If that opponent's speed is greater than each other player's speed, reduce that opponent's speed by 1. This effect can't reduce their speed below 1.":
        ("When this creature enters, return target creature or Vehicle an opponent controls to its owner's hand. Its controller loses 1 life.",
         lambda d: {**d, "effects": [d["effects"][0], {"do": "speed_cut110g", "who": "ref:e0.controller"}]}),
    "Whenever a player puts an Island or blue permanent onto the battlefield, that player sacrifices an Island or blue permanent of their choice.":
        ("Whenever a blue permanent enters, its controller sacrifices a blue permanent of their choice.", _land_or_color("Island", "blue")),
    "Whenever a player puts a Swamp or black permanent onto the battlefield, that player sacrifices a Swamp or black permanent of their choice.":
        ("Whenever a black permanent enters, its controller sacrifices a black permanent of their choice.", _land_or_color("Swamp", "black")),
    "When Cloak and Dagger enter, choose target opponent and up to one target creature they control. They reveal their hand. You may exile a nonland card from their hand or the chosen creature until Cloak and Dagger leave the battlefield.":
        ("When this creature enters, target opponent reveals their hand. You may exile up to one target creature that player controls until this creature leaves the battlefield.", _hand_or_creature),
    "Whenever this creature trains, exile up to one other target creature from the battlefield or creature card from a graveyard.":
        ("Whenever this creature trains, exile up to one other target creature.", _battlefield_or_graveyard),
    # Thijarian Witness
    "Bear Witness \u2014 Whenever another creature dies, if it was attacking or blocking alone, exile it and investigate.":
        ("Whenever another creature dies, if it was attacking, exile it and investigate.", _alone),
    # Halfdane
    "At the beginning of your upkeep, Halfdane's base power and toughness become equal to the power and toughness of target creature other than Halfdane until the end of your next upkeep.":
        ("At the beginning of your upkeep, tap target creature other than this creature.", _halfdane),
    # Season of the Witch
    "At the beginning of the end step, destroy all untapped creatures that didn't attack this turn, except for creatures that couldn't attack.":
        ("At the beginning of the end step, destroy all untapped creatures that didn't attack this turn.", _could_attack),
    # Idol of Endurance
    "When this artifact enters, exile all creature cards with mana value 3 or less from your graveyard until this artifact leaves the battlefield.":
        ("When this artifact enters, draw a card.", _idol_enter),
    "{1}{W}, {T}: Until end of turn, you may cast a creature spell from among cards exiled with this artifact without paying its mana cost.":
        ("{1}{W}, {T}: Draw a card.", _idol_cast),
    # Tatsumasa, the Dragon's Fang
    "{6}, Exile Tatsumasa: Create a 5/5 blue Dragon Spirit creature token with flying. Return Tatsumasa to the battlefield under its owner's control when that token dies.":
        ("{6}, Exile this artifact: Create a 5/5 blue Dragon Spirit creature token with flying. When that token dies, return it to the battlefield.", _tatsumasa),
    # Whippoorwill
    "{G}{G}, {T}: Target creature can't be regenerated this turn. Damage that would be dealt to that creature this turn can't be prevented or dealt instead to "
    "another permanent or player. When the creature dies this turn, exile the creature.":
        ("{G}{G}, {T}: Target creature can't be regenerated this turn. When that creature dies this turn, exile it.", _firm),
    # Sacred Ground
    "Whenever a spell or ability an opponent controls causes a land to be put into your graveyard from the battlefield, return that card to the battlefield.":
        ("Whenever a land is put into your graveyard from the battlefield, return that card to the battlefield.", _opponent_cause),
    # Ertai's Familiar
    "{U}: Until your next upkeep, this creature can't phase out.": ("{U}: Until your next upkeep, this creature can't attack.", _no_phase_out),
    # Elkin Lair
    "At the beginning of each player's upkeep, that player exiles a card at random from their hand. The player may play that card this turn. "
    "At the beginning of the next end step, if the player hasn't played the card, they put it into their graveyard.":
        ("At the beginning of each player's upkeep, that player draws a card.", _elkin),
    # The Fallen
    "At the beginning of your upkeep, this creature deals 1 damage to each opponent and planeswalker it has dealt damage to this game.":
        ("At the beginning of your upkeep, this creature deals 1 damage to each opponent.", _fallen),
    # Phyrexian Ingester
    "This creature gets +X/+Y, where X is the exiled creature card's power and Y is its toughness.":
        ("This creature gets +X/+X, where X is the number of creatures you control.", _imprint_pt),
    # Thought Prison
    "Imprint \u2014 When this artifact enters, you may have target player reveal their hand. If you do, choose a nonland card from it and exile that card.":
        ("When this artifact enters, target player reveals their hand. You choose a nonland card from it. Exile that card.", _may),
    "Whenever a player casts a spell that shares a color or mana value with the exiled card, this artifact deals 2 damage to that player.":
        ("Whenever a player casts a spell, this artifact deals 2 damage to that player.", _shares),
    # Foul Emissary
    "When you sacrifice this creature while casting a spell with emerge, create a 3/2 colorless Eldrazi Horror creature token.":
        ("When you sacrifice this creature, create a 3/2 colorless Eldrazi Horror creature token.", _emerge_sacrifice),
    # Beamsplitter Mage
    "Whenever you cast an instant or sorcery spell that targets only this creature, if you control one or more other creatures that spell could target, choose one of "
    "those creatures. Copy that spell. The copy targets the chosen creature.":
        ("Whenever you cast an instant or sorcery spell that targets only this creature, copy that spell for each other creature you control that the spell could "
         "target. Each copy targets a different one of those creatures.", _one_copy),
    # Serene Master
    "Whenever this creature blocks, exchange its power and the power of target creature it's blocking until end of combat.":
        ("Whenever this creature blocks, target creature it's blocking has base power 3 until end of combat.", _exchange_power),
    # Total War: attack declaration (508.1); "didn't attack" = not among this combat's attackers
    "Whenever a player attacks with one or more creatures, destroy all untapped non-Wall creatures that player controls that didn't attack, except for creatures "
    "the player hasn't controlled continuously since the beginning of the turn.":
        ("Whenever a player attacks with one or more creatures, destroy all untapped non-Wall creatures that player controls that didn't attack this turn.",
         _controlled_since_turn_start),
    # Gemini Engine: "X/X where X is its power", toughness patched
    "Whenever this creature attacks, create a colorless Construct artifact creature token named Twin that's attacking. Its power is equal to this creature's power "
    "and its toughness is equal to this creature's toughness. Sacrifice the token at end of combat.":
        ("Whenever this creature attacks, create an X/X colorless Construct artifact creature token that's attacking, where X is this creature's power. "
         "Sacrifice it at end of combat.", _twin),
    # Psychogenic Probe: every library shuffle in the engine is made by a spell or ability (701.24)
    "Whenever a spell or ability causes a player to shuffle their library, this artifact deals 2 damage to that player.":
        ("Whenever an opponent shuffles their library, this artifact deals 2 damage to that player.", _any_shuffle),
    # Widespread Panic
    "Whenever a spell or ability causes its controller to shuffle their library, that player puts a card from their hand on top of their library.":
        ("Whenever an opponent shuffles their library, each opponent puts a card from their hand on top of their library.", _shuffler_puts_back),
    # Joyful Stormsculptor
    "Whenever you cast a spell that has convoke, this creature deals 1 damage to each opponent and each battle they protect.":
        ("Whenever you cast a spell that has convoke, this creature deals 1 damage to each opponent.", _battles),
    # Vizkopa Confessor
    "When this creature enters, pay any amount of life. Target opponent reveals that many cards from their hand. You choose one of them and exile it.":
        ("When this creature enters, target opponent reveals a number of cards from their hand equal to the number of creatures you control. "
         "You choose one of them. Exile that card.", _pay_life_reveal),
    "Other transformed permanents you control have trample and ward {2}.":
        ("Other creatures you control have trample and ward {2}.", _transformed),
    "When this Siege enters, scry 3, then reveal the top card of your library. If it's a land or double-faced card, draw a card.":
        ("When this Siege enters, scry 3, then reveal the top card of your library. If it's a land card, draw a card.", _land_or_dfc),
    # Sands of Time
    "At the beginning of each player's upkeep, that player simultaneously untaps each tapped artifact, creature, and land they control and taps each untapped "
    "artifact, creature, and land they control.":
        ("At the beginning of each player's upkeep, that player draws a card.", _swap_tapped),
    # Loxodon Peacekeeper
    "At the beginning of your upkeep, the player with the lowest life total gains control of this creature. If two or more players are tied for lowest life total, "
    "you choose one of them, and that player gains control of this creature.":
        ("At the beginning of your upkeep, you gain control of this creature.", _lowest_life_control),
    # Henry Wu
    "Whenever a creature you control exploits a non-Human creature, draw a card. If the exploited creature had power 3 or greater, create a Treasure token.":
        ("Whenever a creature you control exploits a non-Human creature, draw a card. Create a Treasure token.", _treasure_if_big),
    # Carry Away (701.3d): the Equipment the Aura enchants stops equipping its creature
    "When this Aura enters, unattach enchanted Equipment.":
        ("When this Aura enters, you gain 1 life.", lambda d: {**d, "effects": [{"do": "unattach_enchanted110g"}]}),
    # Mindstorm Crown: "If you had a card in hand" is the other branch of the same snapshot
    "At the beginning of your upkeep, draw a card if you had no cards in hand at the beginning of this turn. If you had a card in hand, this artifact deals 1 damage to you.":
        ("At the beginning of your upkeep, draw a card. This artifact deals 1 damage to you.", _crown),
    # Wormfang Crab
    "When this creature enters, an opponent chooses a permanent you control other than this creature and exiles it.":
        ("When this creature enters, exile another permanent you control.", lambda d: _opponent_exiles(d)),
    # Wall of Caltrops
    "Whenever this creature blocks a creature, if at least one other Wall creature is blocking that creature and no non-Wall creatures are blocking that creature, "
    "this creature gains banding until end of turn.":
        ("Whenever this creature blocks a creature, this creature gains banding until end of turn.", _walls_only),
    # Distended Mindbender: two sequential choices from the revealed hand (701.9)
    "When you cast this spell, target opponent reveals their hand. You choose from it a nonland card with mana value 3 or less and a card with mana value 4 or greater. "
    "That player discards those cards.":
        ("When you cast this spell, target opponent reveals their hand. You choose a nonland card with mana value 3 or less from it. That player discards that card. "
         "You choose a card with mana value 4 or greater from it. That player discards that card.", _keep_revealed),
}


_ENGULF = "When this creature enters, exile target non-Ooze creature an opponent controls until this creature leaves the battlefield."
_DISSOLVE = "{X}{B}: Put target creature card with mana value X exiled with this creature into its owner's graveyard."


def definition(ability: Any, ch: Any) -> Def | None:
    from app.rules import scripts, selectors

    if ability.text.strip() == _STICKER_KICKER:  # Wicker Picker: the grant itself is read by sticker_kicker via cast_limits' spell_helper table
        from app.rules import cast_limits

        return {"kind": "static", "static": "spell_helper", "keyword": "sticker_kicker110g", "filter": cast_limits._filter("Creature")[1], "effects": []}

    if ability.text.strip() == "Engulf \u2014 " + _ENGULF:  # Gelatinous Cube: the exile is the linked half Dissolve refers to (607.2a)
        native = scripts.define(replace(ability, text=_ENGULF), ch)
        return None if native is None else {**native, "effects": [{**x, "link": True} for x in native["effects"]]}
    if ability.text.strip().split("\u2014 ", 1)[-1] == _DISSOLVE:  # Gelatinous Cube: the linked-exile target of Hearse-style "{X}{W}: put target card with mana value X exiled with ~ ..." (607.2a)
        sel = selectors.Selector(card=True, zones=("exile",), types=("Creature",), compare=(("mv", "==", selectors.X_VALUE),)).key()
        return {"kind": "activated", "cost": ability.cost, "effects": [{"do": "return_card", "who": "target", "to": "graveyard", "under": "owner"}],
                "target": {"what": "exiled_with:" + sel}}
    if (same := _AS.get(ability.text.strip())) is not None:
        return scripts.define(replace(ability, text=same), ch)
    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def _opponent_exiles(d: Def) -> Def:
    """Wormfang Crab: an opponent picks which of the controller's other permanents is exiled (607.2a link for "the exiled card")."""
    # "exile" marks the exiling half for exiled_with._exiles
    return {**d, "effects": [{"do": "opponent_exiles110g", "exile": True, "link": True}]}


def _exile_chosen(plan: Any, ctx: dict[str, Any], chooser: str) -> bool:
    from app.rules import effects, selectors

    mine = [c for c in selectors.candidates(plan, selectors.from_key('sel:{"controller":"you","other":true}'), ctx["controller"], ctx.get("source_card"))
            if plan.state.cards[c].controller == ctx["controller"] and plan.state.cards[c].zone.endswith(":battlefield")]
    if len(mine) <= 1:
        return effects.exile_cards(plan, ctx, {"link": True}, mine)
    effects.decide(plan, player=chooser, kind="choose_cards", prompt="Choose a permanent to exile", min_choices=1, max_choices=1,
                   options=[effects.DecisionOption(id=c, label=plan.state.cards[c].name or "Permanent", card_id=c) for c in mine],
                   resume={"step": "opponent_exiles110g", "ctx": ctx, "mine": mine})
    return False


def opponent_exiles(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """An opponent chooses (101.4 / ruling: with several opponents the controller picks which one) a permanent the controller has besides the source."""
    from app.rules import effects

    opponents = [p for p in plan.apnap() if p != ctx["controller"] and p in plan.live()]
    if len(opponents) > 1:
        effects.decide(plan, player=ctx["controller"], kind="choose_one", prompt="Choose an opponent to pick the permanent",
                       options=[effects.DecisionOption(id=p, label=plan.name(p)) for p in opponents], resume={"step": "opponent_exiles110g", "ctx": ctx, "opponents": opponents})
        return False
    return _exile_chosen(plan, ctx, opponents[0]) if opponents else True


def resume_opponent_exiles(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if "opponents" in d.resume:
        if chosen[0] not in d.resume["opponents"]:
            raise ValueError("not an opponent")
        done = _exile_chosen(plan, ctx, chosen[0])
    else:
        if chosen[0] not in d.resume["mine"]:
            raise ValueError("not a candidate")
        done = effects.exile_cards(plan, ctx, {"link": True}, [chosen[0]])
    if done:
        effects.continue_effects(plan, ctx)


def unattach_enchanted(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """701.3d: the permanent this Aura is attached to becomes unattached (it stays on the battlefield)."""
    src = plan.state.cards.get(ctx.get("source_card") or "")
    host = plan.state.cards.get(src.attached_to) if src is not None and src.attached_to else None
    if host is not None and host.attached_to:
        plan.do({"type": "detach", "card_ids": [host.id]}, actor=ctx["controller"])
    return True


def fallen(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Bind the opponents (still in the game) and the planeswalkers (still those objects) this object has dealt damage to this game."""
    from app.rules import context

    dealt = plan.rules.dealt_to110g.get(ctx.get("source_object") or "", [])
    context.bind_players(ctx, "fallen_p", [p for p in plan.live() if p in dealt and p != ctx["controller"]])
    context.bind_objects(plan, ctx, "fallen_c", [c.id for c in plan.state.cards.values()
                                                 if plan.oid(c) in dealt and c.zone.endswith(":battlefield") and "Planeswalker" in plan.ch(c).types])
    return True


def suncleanser(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Mode 2 first loses the player's counters (every resource but speed); both modes then remember the target on the source, if it is still there."""
    from app.rules import effects

    src = plan.state.cards.get(ctx.get("source_card") or "")
    if e.get("player"):
        for pid in effects._players(plan, ctx, e["who"]):
            for kind, n in list(plan.state.players[pid].resources.items()):
                if n and kind != "speed":
                    plan.do({"type": "set_resource", "player": pid, "key": kind, "value": 0}, actor=ctx["controller"])
            mark = f"player:{pid}"
    else:
        cards = effects._cards(plan, ctx, e["who"])
        mark = f"object:{plan.oid(cards[0])}" if cards else ""
    if mark and src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == ctx.get("source_object"):
        plan.do({"type": "set_choice", "card_id": src.id, "key": SUN_KEY, "value": mark}, actor=ctx["controller"])
    return True


def sun_marked(plan: Any, mark: str) -> str | None:
    """The name of a battlefield permanent that has marked this object ("object:<oid>") or player ("player:<id>") under Suncleanser's duration."""
    return next((c.name or "a permanent" for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.choices.get(SUN_KEY) == mark), None)


def elkin(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Exile a random card from the active player's hand (public, 406.3) and let that player play it this turn; bound as e0."""
    import secrets

    from app.rules import context, permissions

    pid = plan.state.turn.active_player
    hand = sorted(plan.state.zones.get(f"{pid}:hand", []))
    if not hand:
        context.bind_objects(plan, ctx, "e0", [])
        return True
    cid = (plan.rng or secrets.SystemRandom()).choice(hand)
    before = [r for r in [context.ref_of(plan, cid)] if r is not None]
    plan.do({"type": "move", "card_ids": [cid], "to": {"zone": "exile"}}, actor=pid)
    context.bind_moved(plan, ctx, "e0", before)
    return permissions.grant_play(plan, {**ctx, "controller": pid}, {"do": "grant_play", "who": "ref:e0", "play": True, "cast": True, "until": "end_of_turn"})


def lowest_life_control(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Control goes to the lowest life total (119.1); on a tie the controller chooses one of the tied players (this card's text)."""
    from app.rules import effects

    live = list(plan.live())
    low = min(plan.state.players[p].life for p in live)
    tied = [p for p in live if plan.state.players[p].life == low]
    if len(tied) > 1:
        effects.decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a tied player to gain control",
                       options=[effects.DecisionOption(id=p, label=plan.name(p)) for p in tied], resume={"step": "lowest_control110g", "ctx": ctx, "tied": tied})
        return False
    return effects.gain_control(plan, ctx, {"do": "gain_control", "who": "self", "to": f"player:{tied[0]}"})


def resume_lowest_control(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if chosen[0] not in d.resume["tied"]:
        raise ValueError("not a tied player")
    plan.note(f"{plan.name(d.player)} chooses {plan.name(chosen[0])}")
    if effects.gain_control(plan, ctx, {"do": "gain_control", "who": "self", "to": f"player:{chosen[0]}"}):
        effects.continue_effects(plan, ctx)


def sacrifice_pair(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """701.21a, 101.4: the controller and the player ``who`` names choose in APNAP order, then both sacrifice at once."""
    from app.rules import effects

    pair = {ctx["controller"], *effects._players(plan, ctx, e["who"])}
    return effects._sacrifice_next(plan, ctx, e["sel"], 1, [p for p in plan.apnap() if p in pair], [], e.get("as"))


def swap_tapped(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Sands of Time: both groups are fixed first (the swap is simultaneous), then untapped (stun counters replace it, 122.1d) and tapped."""
    from app.rules import effects, keyword_actions

    for pid in effects._players(plan, ctx, e["who"]):
        mine = [c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == pid and plan.in_game(c)
                and plan.ch(c).types & {"Artifact", "Creature", "Land"}]
        up = keyword_actions.untap_stunned(plan, [c.id for c in mine if c.tapped], pid)
        down = [c.id for c in mine if not c.tapped]
        if up:
            plan.do({"type": "tap", "card_ids": up, "tapped": False}, actor=pid)
        if down:
            plan.do({"type": "tap", "card_ids": down, "tapped": True}, actor=pid)
    return True


def exchange_power(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Both powers are read before either is set (701.12g)."""
    from app.rules import effects, values

    mine, theirs = (values.evaluate(plan, ctx, {"power": who}) for who in ("self", "target"))
    base = {"do": "become", "types": [], "duration": e["duration"]}
    effects.become(plan, ctx, {**base, "who": "self", "p": theirs})
    return effects.become(plan, ctx, {**base, "who": "target", "p": mine})


def bind_exiled(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The source, exiled as a cost, as that new object in exile (400.7): a later 'return it' only finds it while it is still there (610.3-style)."""
    from app.rules import context

    src = plan.state.cards.get(ctx.get("source_card") or "")
    context.bind_objects(plan, ctx, e["as"], [src.id] if src is not None and src.zone.endswith(":exile") else [])
    return True


def exile_gy_until(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """610.3 / 607.2a: your creature cards with mana value 3 or less leave the graveyard together, linked to this source; they go back there when it leaves."""
    from app.rules import effects, exiled_with, selectors

    src = effects._cards(plan, ctx, "self")
    if not src:  # 610.3b: the artifact is already gone
        return True
    sel = selectors.Selector(card=True, zones=("graveyard",), types=("Creature",), compare=(("mv", "<=", 3),))
    you = ctx["controller"]
    cards = [c for c in plan.state.zones.get(f"{you}:graveyard", []) if selectors.matches(plan, sel, plan.state.cards[c], plan.ch(plan.state.cards[c]), you, ctx.get("source_card"))]
    if cards:
        plan.do({"type": "move", "card_ids": cards, "to": {"zone": "exile"}}, actor=you)
        exiled = [c for c in cards if plan.state.cards[c].zone.endswith(":exile")]
        oids = [plan.oid(c) for c in exiled]
        plan.rules.linked_exile[ctx["source_object"]] = [*plan.rules.linked_exile.get(ctx["source_object"], []), *oids]
        plan.rules.linked_exile_from.update({oid: "graveyard" for oid in oids})
        exiled_with.record(plan, ctx, exiled)
    return True


def idol_cast(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Until end of turn the controller may cast any creature card exiled with this artifact for free (normal timing, 118.9)."""
    from app.rules import context, exiled_with
    from app.rules.exile_packet_continuations import insert

    context.bind_objects(plan, ctx, "idol110g", exiled_with.cards(plan, ctx))
    return insert(ctx, [{"do": "grant_play", "who": "ref:idol110g", "from_exile": True, "play": False, "cast": True, "until": "end_of_turn", "free": True}])


def halfdane(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """608.2h: the target's power and toughness are read once, as this resolves; they become Halfdane's base power and toughness (613.4b)
    until the end of its controller's next upkeep."""
    from app.rules import effects, values

    p, t = (values.evaluate(plan, ctx, {stat: "target"}) for stat in ("power", "toughness"))
    return effects.become(plan, ctx, {"do": "become", "who": "self", "types": [], "p": p, "t": t, "duration": "end_of_next_upkeep110g"})


def firm_creature(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """615.12 / 614.9: damage that would be dealt to the creature this turn can be neither prevented nor dealt instead to another permanent or player."""
    import secrets

    from app.rules.effects import _cards

    for cid in _cards(plan, ctx, e["who"]):
        plan.rules.replacements.append({"id": secrets.token_hex(4), "kind": "unpreventable", "turn": plan.state.turn.number, "controller": ctx["controller"],
                                        "source": ctx.get("source_object"), "scope": {}, "to110g": plan.oid(cid), "noredirect110g": True})
    return True


def destroy_instead(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """614.1a / 615.8: the next damage to the target this turn is replaced (never dealt, 614.6) by destroying it; used up by that one time (a body, as Phytohydra's)."""
    from app.rules import replace as rep
    from app.rules import source_shields

    to = source_shields._recipient(plan, ctx, {"to": "target"})
    if to is not None:
        rep.add_record(plan, event="damage", match={"source": {}, "to": to}, op={"do": "body", "once": True, "batch": True,
                           "rider": {"effects": [{"do": "destroy", "who": "ref:to"}], "if": False}}, controller=ctx["controller"],
                           source=ctx.get("source_object"), source_card=ctx.get("source_card"), label=ctx.get("name") or "a replacement effect")
    return True


PRIMITIVES: dict[str, Any] = {"speed_cut110g": speed_cut, "exile_split110g": exile_split, "halfdane110g": halfdane, "exile_gy_until110g": exile_gy_until, "idol_cast110g": idol_cast, "bind_exiled110g": bind_exiled, "firm_creature110g": firm_creature, "elkin110g": elkin, "suncleanser110g": suncleanser, "fallen110g": fallen, "destroy_instead110g": destroy_instead, "exchange_power110g": exchange_power, "lowest_life_control110g": lowest_life_control,
                           "sacrifice_pair110g": sacrifice_pair, "swap_tapped110g": swap_tapped, "opponent_exiles110g": opponent_exiles,
                              "unattach_enchanted110g": unattach_enchanted}
RESUME: dict[str, Any] = {"lowest_control110g": resume_lowest_control, "opponent_exiles110g": resume_opponent_exiles}
