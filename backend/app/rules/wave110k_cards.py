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


PRIMITIVES = {"extra_combat_after_first110k": extra_combat_after_first, "return_self_hand110k": return_self_hand, "opponent_mode110k": opponent_mode, "as_controller110k": as_controller, "phase_out_hold110k": phase_out_hold}
RESUME = {"opponent_mode110k": resume_opponent_mode}


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


def _snow_or_colorless() -> str:
    """"Land that is snow or could produce {C}": either property is enough (a union, not the two together)."""
    from app.rules import selectors

    return selectors.Selector(types=("Land",), either=(selectors.Selector(types=("Land",), supertypes=("Snow",)).key(),
                                                       selectors.Selector(types=("Land",), extras=("could_produce_c",)).key())).key()


_BODIES: dict[str, tuple[str, Any]] = {
    _SHIP: ("Untap all creatures that attacked this turn.", _ship),
    _TEFERI: ("Each creature target opponent controls phases out.", _teferi),
    _ICE_EACH: ("Destroy each land.", lambda effects: [{**effects[0], "who": _snow_or_colorless()}] if len(effects) == 1 else None),
    _ICE: ("Destroy target land.", lambda effects: effects),
    _FLOURISH: ("Destroy target artifact or creature you don't control. If that permanent is destroyed this way, its controller gains 2 life.", _flourish),
}


def parse(body: str) -> Any:
    from app.rules import scripts

    body = body.strip()
    if (built := _BODIES.get(body[:1].upper() + body[1:])) is None:  # (a trigger's effect text starts in lower case)
        return None
    native = scripts.parse_effects(built[0])
    if native is None:
        return None
    effects = built[1](native[0])
    target = _snow_or_colorless() if body[:1].upper() + body[1:] == _ICE else native[1]
    return None if effects is None else (effects, target, native[2])


# -- one-ability wordings: the whole ability text -> (the wording the grammar reads, what to change in its definition) --
def _rat_roles(d: Def) -> Def:
    """Twisted Sewer-Witch: a Wicked Role token for each Rat its controller has once the token exists, each attached to its own Rat (111.1, 303.7)."""
    from app.rules import selectors

    each = {"do": "each100c", "who": selectors.Selector(subtypes=("Rat",), controller="you").key(), "then": {"do": "create_role", "role": "Wicked"}}
    return {**d, "effects": [*d["effects"], each]} if len(d["effects"]) == 1 and d["effects"][0].get("do") == "create_token" else d


_BUILD: dict[str, tuple[str, Any]] = {
    'When this creature enters, create a 1/1 black Rat creature token with "This creature can\'t block." Then for each Rat you control, create a Wicked '
    'Role token attached to that Rat.':
        ('When this creature enters, create a 1/1 black Rat creature token with "This creature can\'t block."', _rat_roles),
}


_NO_REGEN_DAMAGED = "Creatures dealt damage by this creature this turn can't be regenerated this turn."


def definition(ability: Any, ch: Any) -> Def | None:
    from dataclasses import replace

    from app.rules import scripts

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
