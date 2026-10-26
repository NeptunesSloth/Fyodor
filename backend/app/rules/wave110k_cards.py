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


PRIMITIVES = {"opponent_mode110k": opponent_mode, "as_controller110k": as_controller, "phase_out_hold110k": phase_out_hold}
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


_TEFERI = "Each creature target opponent controls phases out. Until the end of your next turn, they can't phase in."


def _teferi(effects: list[Def]) -> list[Def] | None:
    """Teferi, Timeless Voyager -8: the creatures phase out, and those same objects (they are no longer on the battlefield to be selected) can't phase in."""
    if len(effects) != 1 or effects[0].get("do") != "phase_out":
        return None
    return [{**effects[0], "do": "phase_out_hold110k"}]


_BODIES: dict[str, tuple[str, Any]] = {
    _TEFERI: ("Each creature target opponent controls phases out.", _teferi),
    _FLOURISH: ("Destroy target artifact or creature you don't control. If that permanent is destroyed this way, its controller gains 2 life.", _flourish),
}


def parse(body: str) -> Any:
    from app.rules import scripts

    if (built := _BODIES.get(body.strip())) is None:
        return None
    native = scripts.parse_effects(built[0])
    if native is None:
        return None
    effects = built[1](native[0])
    return None if effects is None else (effects, native[1], native[2])


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


def definition(ability: Any, ch: Any) -> Def | None:
    from dataclasses import replace

    from app.rules import scripts

    if (built := _BUILD.get(ability.text.strip())) is None:
        return None
    native = scripts.define(replace(ability, text=built[0]), ch)
    return None if native is None else built[1](native)
