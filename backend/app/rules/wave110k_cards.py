"""-- wave 110K -- exact Oracle wordings of single cards, built from parts of wordings the grammar already reads.

Each entry matches one whole ability's (or spell's) Oracle text exactly and nothing else; any other wording stays unsupported.
"""
from __future__ import annotations

from typing import Any

Def = dict[str, Any]

# -- Library of Lat-Nam: "An opponent chooses one —" (608.2d: the mode is chosen on resolution by the player the text names) --
_LATNAM = ["An opponent chooses one —", "• You draw three cards at the beginning of the next turn's upkeep.",
           "• You search your library for a card, put that card into your hand, then shuffle."]
_LATNAM_MODES = ["Draw three cards at the beginning of the next turn's upkeep.", "Search your library for a card, put that card into your hand, then shuffle."]


def spell(ch: Any, lines: list[Any]) -> Def | None:
    """Spell definitions of whole-spell wordings: the chooser's modes are read as the native wording of each bullet."""
    from app.rules import scripts

    if [x.text for x in lines] != _LATNAM:
        return None
    modes = [scripts.parse_effects(m) for m in _LATNAM_MODES]
    if any(m is None or m[1] is not None for m in modes):
        return None
    return {"kind": "spell", "whole110k": True, "effects": [{"do": "opponent_mode110k", "modes": [m[0] for m in modes if m is not None],
                                          "labels": ["Its controller draws three cards at the beginning of the next turn's upkeep",
                                                     "Its controller searches their library for a card"]}]}


def opponent_mode(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """An opponent picks the mode; with several opponents the controller picks which one (800.4: only players still in the game)."""
    from app.rules import effects

    opponents = [p for p in plan.apnap() if p != ctx["controller"] and p in plan.live()]
    if not opponents:
        return True
    if len(opponents) > 1:
        effects.decide(plan, player=ctx["controller"], kind="choose_one", prompt="Choose an opponent to choose the mode",
                       options=[effects.DecisionOption(id=p, label=plan.name(p)) for p in opponents],
                       resume={"step": "opponent_mode110k", "ctx": ctx, "effect": e, "opponents": opponents})
        return False
    return _ask(plan, ctx, e, opponents[0])


def _ask(plan: Any, ctx: dict[str, Any], e: dict[str, Any], chooser: str) -> bool:
    from app.rules import effects

    effects.decide(plan, player=chooser, kind="choose_one", prompt=f"{ctx.get('name') or 'Choose one'}: choose one",
                   options=[effects.DecisionOption(id=str(i), label=label) for i, label in enumerate(e["labels"])],
                   resume={"step": "opponent_mode110k", "ctx": ctx, "effect": e})
    return False


def resume_opponent_mode(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, e = d.resume["ctx"], d.resume["effect"]
    if "opponents" in d.resume:
        if chosen[0] not in d.resume["opponents"]:
            raise ValueError("not an opponent")
        _ask(plan, ctx, e, chosen[0])
        return
    if chosen[0] not in {str(i) for i in range(len(e["modes"]))}:
        raise ValueError("not a mode")
    ctx["effects"][ctx["next"]:ctx["next"]] = e["modes"][int(chosen[0])]
    effects.continue_effects(plan, ctx)


def as_controller(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The next instructions are done by the controller the bound permanent last had (a player who left the game is gone: they are skipped, 800.4a)."""
    from app.rules import effects

    owners = effects._players(plan, ctx, e["who"])
    if not owners:
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
        return True
    ctx.setdefault("controllers", []).append(ctx["controller"])
    ctx["controller"] = owners[0]
    return True


def cant_phase_in(plan: Any, card_id: str) -> bool:
    """Held out of phasing in by a Teferi-style rule (phasing.untap_step)."""
    oid = plan.oid(card_id)
    return any(oid in h.objects for h in plan.rules.phase_holds110k)


def end_of_turn(plan: Any) -> None:
    """The cleanup step of the holder's next turn (a later turn than the one the hold began in) ends the holds (514.2, 611.2a)."""
    plan.rules.phase_holds110k = [h for h in plan.rules.phase_holds110k if h.player in plan.live() and not (h.player == plan.active and plan.state.turn.number > h.turn)]  # (800.4m: a departed player's duration ends with them)


def phase_out_hold(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """phasing.phase_out, then a rule on exactly the objects that phased out (702.26b: one that did not, e.g. "can't phase out", is not held) that they
    can't phase in until the cleanup step of the controller's next turn (611.2a, 514.2; phasing.untap_step reads the rule)."""
    from app.game.rules_state import PhaseHold110K
    from app.rules import effects, phasing

    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield") and not phasing._held(plan, c)]
    if cards:
        plan.do({"type": "phase_shift", "card_ids": cards, "out": True}, actor=ctx["controller"])
    out = [plan.oid(c) for c in cards if plan.state.cards[c].zone.endswith(":phased")]
    if out:
        plan.rules.phase_holds110k.append(PhaseHold110K(objects=out, player=ctx["controller"], turn=plan.state.turn.number))
    return True


def extra_combat_after_first(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """500.8: an additional combat phase after the first combat phase of this turn. Before it (the precombat main phase, nothing else queued) the natural
    combat stays first and the added one follows it; during it, the phase is added directly after it; once it is over there is no phase to add it
    after, so nothing happens."""
    from app.rules import combat_rules

    r, phase = plan.rules, plan.state.turn.phase
    added = {"do": "extra_phases", "after": "phase", "then": e["then"]}
    if phase == "main1" and r.combats == 0 and not r.extra_phases:
        combat_rules.extra_phases(plan, ctx, added)
        r.extra_phases = [r.extra_phases[1], r.extra_phases[0]]  # [the natural first combat, the added one]
    elif phase in combat_rules._COMBAT and r.combats == 1:
        combat_rules.extra_phases(plan, ctx, added)
    else:
        plan.note(f"{ctx.get('name') or 'It'}: there is no first combat phase to add an additional combat phase after (500.8)")
    return True


def villain110k(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """villainous.villain for a spell: the player who faces the choice is not an event's player (a spell has no event), so the options carry a marker that
    becomes "that player" as the choice begins."""
    import json

    from app.rules import villainous

    return villainous.villain(plan, ctx, {**json.loads(json.dumps(e).replace("THAT110K", "event_player")), "do": "villain"})


def shuffle_other(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"They shuffle another creature they own into their library": the player picks one of the creatures they own on the battlefield (other than the one
    just shuffled away: it isn't there any more), nothing if they own none (701.55b)."""
    from app.rules import effects

    pid = effects._players(plan, ctx, e["who"])
    if not pid:
        return True
    mine = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.owner == pid[0] and plan.in_game(c) and plan.ch(c).is_creature]
    if not mine:
        plan.note(f"{plan.name(pid[0])} owns no other creature to shuffle into their library")
        return True
    effects.decide(plan, player=pid[0], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: choose a creature you own to shuffle into your library",
                   min_choices=1, max_choices=1, options=[effects.DecisionOption(id=c, label=plan.state.cards[c].name or "Creature", card_id=c) for c in mine],
                   resume={"step": "shuffle_other110k", "ctx": ctx, "mine": mine})
    return False


def resume_shuffle_other(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in d.resume["mine"]:
        raise ValueError("not one of the creatures")
    if effects.PRIMITIVES["to_library"](plan, ctx, {"do": "to_library", "who": f"object:{plan.oid(chosen[0])}", "place": "shuffle"}):
        effects.continue_effects(plan, ctx)


def copies_of_revealed(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"If a creature card is revealed this way, you may have creatures you control other than this creature become copies of that card until end of
    turn": its controller decides; the copies take the card's copiable values as the effect begins (707.2, 707.9, 611.2c)."""
    from app.rules import effects, selectors

    _, looked = effects._looked(plan, ctx)
    if len(looked) != 1 or "Creature" not in plan.ch(plan.state.cards[looked[0]]).types:
        return True
    others = selectors.Selector(types=("Creature",), controller="you", other=True).key()
    if not effects._cards(plan, ctx, others):
        return True
    effects.decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{plan.state.cards[looked[0]].name}: have your other creatures become copies of it?",
                   options=[effects.DecisionOption(id="yes", label="Yes, they become copies of it until end of turn"), effects.DecisionOption(id="no", label="No")],
                   resume={"step": "copies_of_revealed110k", "ctx": ctx, "card": looked[0], "who": others})
    return False


def resume_copies_of_revealed(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import context, copying, effects

    ctx = d.resume["ctx"]
    card = plan.state.cards.get(d.resume["card"])
    if chosen == ["yes"] and card is not None and card.zone.endswith(":library"):
        context.bind_objects(plan, ctx, "revealed110k", [card.id])
        copying.become_copy(plan, ctx, {"do": "become_copy", "who": d.resume["who"], "with": "ref:revealed110k", "duration": "end_of_turn"})
    effects.continue_effects(plan, ctx)


def control_swap(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Cruel Entertainment (723.1, 723.1a): each of the two target players controls the other during that other player's next turn. A half whose players aren't
    both still in the game does nothing (800.4)."""
    from app.game.rules_state import PlayerControl
    from app.rules import effects

    first, second = (effects._players(plan, ctx, f"target:{i}") for i in (0, 1))
    if len(first) != 1 or len(second) != 1 or first == second:
        plan.note(f"{ctx.get('name') or 'It'}: both targets are needed for the players to control each other (608.2b)")
        return True
    name = ctx.get("name") or "An effect"
    for controller, controlled in ((first[0], second[0]), (second[0], first[0])):
        old = [c for c in plan.rules.player_control if c.controlled == controlled and c.status == "pending"]  # 723.1a: the last one works
        plan.rules.player_control = [c for c in plan.rules.player_control if c not in old]
        plan.rules.player_control.append(PlayerControl(controlled=controlled, controller=controller, label=name, extra_after=sum(c.extra_after for c in old)))
        plan.note(f"{plan.name(controller)} will control {plan.name(controlled)} during their next turn ({name}, 723.1)", actor=ctx["controller"])
    return True


def return_self_hand(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Return ~ to its owner's hand" from the battlefield (bounce) or from the graveyard (the same object, 400.7: if it moved since, nothing)."""
    from app.rules import effects

    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is None or plan.oid(card) != ctx.get("source_object"):
        return True
    if card.zone.endswith(":battlefield"):
        return effects.PRIMITIVES["bounce"](plan, ctx, {"do": "bounce", "who": "self"})
    if card.zone.endswith(":graveyard"):
        return effects.PRIMITIVES["return_card"](plan, ctx, {"do": "return_card", "to": "hand", "who": "self_gy"})
    return True


# the label delayed.apply_duration writes on the table marker
from app.rules import delayed as _delayed  # noqa: E402

_delayed.LABELS["source_tapped_power110k"] = "for as long as ~ remains tapped and its power is at most ~'s"

PRIMITIVES = {"control_swap110k": control_swap, "copies_of_revealed110k": copies_of_revealed, "villain110k": villain110k, "shuffle_other110k": shuffle_other, "extra_combat_after_first110k": extra_combat_after_first, "return_self_hand110k": return_self_hand, "opponent_mode110k": opponent_mode, "as_controller110k": as_controller, "phase_out_hold110k": phase_out_hold}
RESUME = {"copies_of_revealed110k": resume_copies_of_revealed, "opponent_mode110k": resume_opponent_mode, "shuffle_other110k": resume_shuffle_other}


# -- spell bodies: the whole body -> (the wording the grammar reads, what to do with its effects) --
_FLOURISH = ("Destroy target artifact or creature you don't control. If that permanent is destroyed this way, its controller exiles cards from the top of "
             "their library until they exile a nonland card, then they may cast that card without paying its mana cost.")


def _flourish(effects: list[Def]) -> list[Def] | None:
    """Transforming Flourish: the last instruction of the native "… its controller gains 2 life" is the exile-and-cast, done by that player (608.2d, 118.9)."""
    from app.rules import scripts

    gain = scripts.parse_effects("Exile cards from the top of your library until you exile a nonland card, then you may cast that card without paying its mana cost.")
    if gain is None or len(effects) != 3 or effects[2].get("do") != "gain_life" or effects[2].get("who") != "ref:e0.controller":
        return None
    rest = [{"do": "as_controller110k", "who": "ref:e0.controller", "skip": len(gain[0]) + 1}, *gain[0], {"do": "as_player_end"}]
    return [effects[0], {**effects[1], "skip": len(rest)}, *rest]


_ICE = "Destroy target land that is snow or could produce {C}."
_ENDS = ("Target creature's owner shuffles it into their library, then faces a villainous choice — They lose 5 life, or they shuffle another creature they "
         "own into their library.")
_CRUEL = ("Choose target player and another target player. The first player controls the second player during the second player's next turn, and the second "
          "player controls the first player during the first player's next turn.")
_ICE_EACH = "Destroy each land that is snow or could produce {C}."  # (overload, 702.96a: "target" read as "each")
_SHIP = ("After the first combat phase this turn, there's an additional combat phase. At the beginning of that combat, untap all creatures that attacked "
         "this turn.")
_TEFERI = "Each creature target opponent controls phases out. Until the end of your next turn, they can't phase in."


def _teferi(effects: list[Def]) -> list[Def] | None:
    """Teferi, Timeless Voyager -8: the creatures phase out, and those same objects (they are no longer on the battlefield to be selected) can't phase in."""
    if len(effects) != 1 or effects[0].get("do") != "phase_out":
        return None
    return [{**effects[0], "do": "phase_out_hold110k"}]


def _ship(effects: list[Def]) -> list[Def] | None:
    """Swinging Ship's visit: an extra combat after the first combat phase, with its delayed untap (500.8, 603.7)."""
    if len(effects) != 1 or effects[0].get("do") != "untap":
        return None
    return [{"do": "extra_combat_after_first110k", "then": effects}]


def _ends(effects: list[Def]) -> list[Def] | None:
    """This Is How It Ends: the creature's owner (as it last was, 608.2h) then faces the choice (701.55a, villainous.villain)."""
    if len(effects) != 1 or effects[0].get("do") != "to_library":
        return None
    return [{**effects[0], "as": "e0"},
            {"do": "villain110k", "who": "ref:e0.owner", "a": [{"do": "lose_life", "who": "THAT110K", "n": 5}],
             "b": [{"do": "shuffle_other110k", "who": "THAT110K"}],
             "labels": ["They lose 5 life", "They shuffle another creature they own into their library"]}]


def _snow_or_colorless() -> str:
    """"Land that is snow or could produce {C}": either property is enough (a union, not the two together)."""
    from app.rules import selectors

    return selectors.Selector(types=("Land",), either=(selectors.Selector(types=("Land",), supertypes=("Snow",)).key(),
                                                       selectors.Selector(types=("Land",), extras=("could_produce_c",)).key())).key()


_BODIES: dict[str, tuple[str, Any]] = {
    _ENDS: ("Shuffle target creature into its owner's library.", _ends),
    _ENDS.replace("Target creature's owner", "The owner of target creature"): ("Shuffle target creature into its owner's library.", _ends),  # (as define reads it)
    _SHIP: ("Untap all creatures that attacked this turn.", _ship),
    _TEFERI: ("Each creature target opponent controls phases out.", _teferi),
    _ICE_EACH: ("Destroy each land.", lambda effects: [{**effects[0], "who": _snow_or_colorless()}] if len(effects) == 1 else None),
    _ICE: ("Destroy target land.", lambda effects: effects),
    _FLOURISH: ("Destroy target artifact or creature you don't control. If that permanent is destroyed this way, its controller gains 2 life.", _flourish),
}


def parse(body: str) -> Any:
    from app.rules import scripts

    body = body.strip()
    if body[:1].upper() + body[1:] == _CRUEL:  # two different target players (115.3: "another target player")
        return [{"do": "control_swap110k"}], [{"what": "player", "min": 1, "max": 1}, {"what": "player", "min": 1, "max": 1, "distinct_from": [0]}], False
    if (built := _BODIES.get(body[:1].upper() + body[1:])) is None:  # (a trigger's effect text starts in lower case)
        return None
    native = scripts.parse_effects(built[0])
    if native is None:
        return None
    effects = built[1](native[0])
    target = _snow_or_colorless() if body[:1].upper() + body[1:] == _ICE else native[1]
    return None if effects is None else (effects, target, native[2])


# -- one-ability wordings: the whole ability text -> (the wording the grammar reads, what to change in its definition) --
def _old_man(d: Def) -> Def:
    """Old Man of the Sea: control lasts while the source stays tapped AND the creature's power stays at most the source's (611.2b; delayed.expire)."""
    from app.rules import scripts

    held = scripts.parse_effects("Gain control of target creature for as long as ~ remains tapped.")
    if held is None or len(held[0]) != 2 or held[0][0].get("duration") != "source_tapped" or d.get("effects") != [{"do": "gain_control", "who": "target"}]:
        return d
    return {**d, "effects": [{**held[0][0], "duration": "source_tapped_power110k"}, held[0][1]]}


def _stickered_target(d: Def) -> Def:
    """Scampire: the target is a creature card "with a sticker on it" (123.4: a sticker put on a card in a graveyard stays on it, selectors "sticker101:any")."""
    from app.rules import selectors

    sel = selectors.from_key(d["target"]["what"]) if d.get("target") else None
    if sel is None or "graveyard" not in sel.zones:
        return d
    return {**d, "target": {**d["target"], "what": selectors.replace(sel, extras=(*sel.extras, "sticker101:any")).key()}}


def _deceiver(d: Def) -> Def:
    """Deceiver of Form: after the reveal and before the optional bottom, a creature card revealed may be what the other creatures become copies of."""
    eff = d["effects"]
    if len(eff) != 2 or eff[0].get("do") != "look_top" or eff[1].get("do") != "pick_looked":
        return d
    return {**d, "effects": [eff[0], {"do": "copies_of_revealed110k"}, eff[1]]}


def _flip_chandra(d: Def) -> Def:
    """Chandra, Fire of Kaladesh: after the exile, the returning instruction names the exiled card, not the old object (400.7)."""
    from app.rules import scripts

    back = scripts.parse_effects("Exile ~, then return her to the battlefield transformed under her owner's control.")
    eff = d["effects"]
    if back is None or len(eff) != 3 or eff[1].get("do") != "only_if" or eff[2].get("do") != "exile":
        return d
    return {**d, "effects": [eff[0], {**eff[1], "skip": len(back[0])}, *back[0]]}


def _chandra_emblems(d: Def) -> Def:
    """Chandra, Roaring Flame -7: only the players the damage was actually dealt to (after prevention, 120.3) get the emblem."""
    eff = d["effects"]
    if len(eff) != 1 or eff[0].get("do") != "damage":
        return d
    emblem = {"do": "emblem", "who": "ref:chandra110k", "text": "At the beginning of your upkeep, this emblem deals 3 damage to you."}
    return {**d, "effects": [{**eff[0], "bind_damage_players": "chandra110k"}, emblem]}


def _rat_roles(d: Def) -> Def:
    """Twisted Sewer-Witch: a Wicked Role token for each Rat its controller has once the token exists, each attached to its own Rat (111.1, 303.7)."""
    from app.rules import selectors

    each = {"do": "each100c", "who": selectors.Selector(subtypes=("Rat",), controller="you").key(), "then": {"do": "create_role", "role": "Wicked"}}
    return {**d, "effects": [*d["effects"], each]} if len(d["effects"]) == 1 and d["effects"][0].get("do") == "create_token" else d


_BUILD: dict[str, tuple[str, Any]] = {
    "\u22127: Chandra deals 6 damage to each opponent. Each player dealt damage this way gets an emblem with \"At the beginning of your upkeep, this emblem "
    "deals 3 damage to you.\"":
        ("\u22127: ~ deals 6 damage to each opponent.", _chandra_emblems),
    "{T}: Chandra deals 1 damage to target player or planeswalker. If Chandra has dealt 3 or more damage this turn, exile her, then return her to the "
    "battlefield transformed under her owner's control.":
        ("{T}: ~ deals 1 damage to target player or planeswalker. If ~ has dealt 3 or more damage this turn, exile ~.", _flip_chandra),
    "At the beginning of combat on your turn, reveal the top card of your library. If a creature card is revealed this way, you may have creatures you "
    "control other than this creature become copies of that card until end of turn. You may put that card on the bottom of your library.":
        ("At the beginning of combat on your turn, reveal the top card of your library. You may put that card on the bottom of your library.", _deceiver),
    "{3}{B}: Return target creature card with a sticker on it from your graveyard to the battlefield. That creature gains haste. Exile it at the beginning of "
    "the next end step. Activate only as a sorcery.":
        ("{3}{B}: Return target creature card from your graveyard to the battlefield. That creature gains haste. Exile it at the beginning of the next end "
         "step. Activate only as a sorcery.", _stickered_target),
    "{T}: Gain control of target creature with power less than or equal to this creature's power for as long as this creature remains tapped and that "
    "creature's power remains less than or equal to this creature's power.":
        ("{T}: Gain control of target creature with power less than or equal to ~'s power.", _old_man),
    'When this creature enters, create a 1/1 black Rat creature token with "This creature can\'t block." Then for each Rat you control, create a Wicked '
    'Role token attached to that Rat.':
        ('When this creature enters, create a 1/1 black Rat creature token with "This creature can\'t block."', _rat_roles),
}


_SADDLEBRUTE = "All creatures can attack your opponents and planeswalkers your opponents control as though those creatures had haste."
_NO_REGEN_DAMAGED = "Creatures dealt damage by this creature this turn can't be regenerated this turn."


def definition(ability: Any, ch: Any) -> Def | None:
    from dataclasses import replace

    from app.rules import scripts

    if ability.text.strip() == _SADDLEBRUTE:  # read by combat.attack_problem / declare_attackers through sick_may_attack and sick_target_ok
        return {"kind": "static", "static": "saddlebrute110k", "effects": []}
    if ability.text.strip() == f"{{2}}{{W}}: Return {ch.name} to its owner's hand. Activate only if {ch.name} is on the battlefield or in your graveyard." \
            and ch.name == "Skyblade's Boon":
        # costs.battlefield_too110k (casting.ability_cost, ability_problem): either zone; the effect moves it from whichever it is in
        return {"kind": "activated", "cost": "{2}{W}", "effects": [{"do": "return_self_hand110k"}], "target": None, "text": ability.text}
    if ability.text.strip().replace("this permanent", "this creature") == _NO_REGEN_DAMAGED:  # Bone Shaman's granted ability: read by regeneration.shielded / regeneration_choices.options
        return {"kind": "static", "static": "no_regen_damaged110k", "effects": []}

    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)


def damaged_unregenerable(plan: Any, card: Any) -> bool:
    """701.19c / 614.8: a creature dealt damage this turn by a permanent that has "Creatures dealt damage by this creature this turn can't be
    regenerated this turn" can't be regenerated (the damage as it was dealt: the facts of the turn, and the source still has the ability now)."""
    from app.rules import scripts
    from app.rules.history import log_for

    oid = plan.oid(card)
    sources = {f.source for f in log_for(plan).facts if f.kind == "damaged" and f.object_id == oid and f.amount > 0}
    return any(
        (src := plan.state.cards.get(s.rsplit(".", 1)[0])) is not None and src.zone.endswith(":battlefield") and plan.oid(src) == s
        and "no_regen_damaged110k" in {d.get("static") for d in scripts.definitions(plan.ch(src)).values()}
        for s in sources if s)


def old_man_kept(plan: Any, effect: Any) -> list[str]:
    """The objects Old Man of the Sea's control effect still holds: none once the source left or untapped (611.2b); else those whose power is still at
    most the source's (checked after every table change)."""
    from app.rules import sba

    src = plan.state.cards.get(effect.source_card or "")
    if src is None or not src.zone.endswith(":battlefield") or plan.oid(src) != effect.source or not src.tapped or not plan.in_game(src):
        return []
    limit = sba.power(src, plan.ch(src))
    kept = []
    for oid in effect.affected:
        held = next((c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) == oid), None)
        if held is not None and (sba.power(held, plan.ch(held)) or 0) <= (limit or 0):
            kept.append(oid)
    return kept


def _saddlebrutes(state: Any, info: Any) -> list[str]:
    """The controllers of battlefield permanents with Frenzied Saddlebrute's static."""
    from app.rules import characteristics as chars
    from app.rules import scripts

    return [c.controller for c in state.cards.values() if c.zone.endswith(":battlefield") and not c.phased_indirect
            and any(d.get("static") == "saddlebrute110k" for d in scripts.definitions(chars.of(c, info)).values())]


def sick_may_attack(state: Any, card: Any, info: Any) -> bool:
    """302.6, 508.1: a summoning-sick creature is still declared as an attacker when a Saddlebrute's controller has an opponent it could attack (the
    declared target is then checked by sick_target_ok)."""
    from app.rules.plan import live_players

    players = live_players(state)
    return any(p != card.controller and p != boss for boss in _saddlebrutes(state, info) for p in players)


def sick_target_ok(plan: Any, card: Any, ch: Any, target: str) -> bool:
    """A creature without haste (and not summoning-sick) attacks anything; a sick one only a player who is an opponent of a Saddlebrute's controller, or a
    planeswalker such an opponent controls."""
    from app.rules.casting import summoning_sick

    if "haste" in ch.keywords or not summoning_sick(plan.state, card):
        return True
    from app.rules import scripts

    if "attack_as_haste" in scripts.statics(ch):
        return True
    owner = target if target in plan.state.players else plan.state.cards[target].controller if target in plan.state.cards \
        and "Planeswalker" in plan.ch(plan.state.cards[target]).types else None
    return owner is not None and any(owner != boss for boss in _saddlebrutes(plan.state, plan.info))
