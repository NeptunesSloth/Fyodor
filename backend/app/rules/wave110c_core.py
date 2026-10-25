"""-- core (wave 110C) -- exact Oracle wordings (whole ability or spell body) built from what the grammar already reads plus a few primitives.

Each entry matches one whole text exactly; any other wording stays unsupported. ``~`` stands for the card's name, as in multi100n.
"""
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

Parsed = tuple[list[dict[str, Any]], Any, bool]
Context = dict[str, Any]


def read(text: str) -> Parsed:
    """What scripts.parse_effects reads for a native wording (the build fails loudly if the grammar stops reading it)."""
    from app.rules import scripts

    got = scripts.parse_effects(text)
    if got is None:
        raise AssertionError(f"wave110c: the grammar no longer reads {text!r}")
    return copy.deepcopy(got)


def _soldiers() -> Parsed:
    """SOLDIER Military Program: chosen as it resolves, not targeted (608.2d, 115.1): up to two Soldiers you control, a +1/+1 counter on each (122.1)."""
    from app.rules import selectors

    key = selectors.parse("Soldier").key()  # type: ignore[union-attr]
    return [{"do": "player_chooses", "who": "you", "sel": key, "n": 2, "label": "Soldier", "upto": True, "optional": True, "as": "gco"},
            {"do": "add_counters", "who": "ref:gco", "kind": "+1/+1", "n": 1}], None, False


def _catastrophe() -> Parsed:
    """Catastrophe: the choice of lands or creatures is made as it resolves (608.2d); only the creatures' destruction can't be regenerated (701.19c)."""
    lands = read("Destroy all lands.")[0]
    creatures = read("Destroy all creatures. They can't be regenerated.")[0]
    return [{"do": "choose_branch110c", "who": "you", "options": [{"label": "Destroy all lands", "effects": lands},
                                                                  {"label": "Destroy all creatures", "effects": creatures}]}], None, False


def _paid(cost: str) -> dict[str, Any]:
    """"The {2}{U} cost was paid": the spell's one alternative cost (118.9a), read from its payment record (conditions._cast_how)."""
    from app.rules import conditions

    got = conditions.parse(f"the {cost} cost was paid", objects=True)
    assert got is not None
    return got


def _instead(cond: dict[str, Any], base: list[dict[str, Any]], alt: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """"If C, A. If not, B.": C judged once as the spell resolves (608.2c), then exactly one of the two (base runs when C fails)."""
    return [{"do": "only_if", "cond": {"not": cond}, "skip": len(base), "bind": "cond0"}, *base,
            {"do": "only_if", "cond": {"flag": "cond0", "negate": True}, "skip": len(alt)}, *alt]


def _ingenious_mastery() -> Parsed:
    """Ingenious Mastery: paid, you draw three cards, then an opponent (one you choose as it resolves: its 2021-04-16 ruling) creates two Treasure
    tokens and scries 2; else you draw X cards. A copy resolves as if the cost was paid (its ruling; the copy's record is the original's)."""
    opponent = read("An opponent draws a card.")[0][0]
    treasure = read("Each opponent creates two Treasure tokens.")[0][0]
    scry = read("Scry 2.")[0][0]
    paid = [*read("Draw three cards.")[0], opponent, {**treasure, "who": "ref:copp"}, {**scry, "who": "ref:copp"}]
    return _instead(_paid("{2}{U}"), read("Draw X cards.")[0], paid), None, False


def _devastating_mastery() -> Parsed:
    """Devastating Mastery: paid, an opponent you choose as it resolves chooses up to two nonland permanents they control and returns them to
    their owner's hand (their choice: 701.? no — the player returns them; a "returns" is theirs to make, not a bounce of yours)."""
    opponent = read("An opponent draws a card.")[0][0]
    chosen = read("Target opponent chooses up to two creatures they control. Return those creatures to their owner's hand.")[0]
    pick = {**chosen[0], "who": "ref:copp", "sel": read("Target opponent chooses up to two nonland permanents they control.")[0][0]["sel"],
            "label": "nonland permanents"}
    return [{"do": "only_if", "cond": _paid("{2}{W}{W}"), "skip": 3}, opponent, pick, chosen[1]], None, False


def _bounty_of_the_hunt() -> Parsed:
    """Bounty of the Hunt: the counters actually put on each creature (122.6: a replacement may change the number) come off again at the beginning
    of the next cleanup step (514.3a), as a delayed triggered ability per creature (603.7)."""
    effects, groups, optional = read("Distribute three +1/+1 counters among one, two, or three target creatures.")
    return [{**effects[0], "receipt": "bounty110c"}, {"do": "temporary_counters110c", "receipt": "bounty110c"}], groups, optional


def _scrap_mastery() -> Parsed:
    """Scrap Mastery: every player's artifact cards leave their graveyards together, then every artifact is sacrificed, then the cards exiled
    by the first instruction (not those a replacement effect exiled instead: its 2014-11-07 ruling) are put onto the battlefield, each under its
    owner's control — a player puts back what came from their own graveyard (404.1)."""
    return read("Exile all artifact cards from all graveyards. Each player sacrifices all artifacts they control. Return all cards exiled this way "
                "to the battlefield under their owners' control.")


def _retether() -> Parsed:
    """Retether: every Aura returns together (400.7); each is attached as it enters to a creature its controller chooses (303.4f, 303.4g), so an
    Aura that can't enchant a creature (Enchant land) stays in the graveyard. The host is any creature, not only yours."""
    from app.rules import selectors

    effects, groups, optional = read("Return all Aura cards from your graveyard to the battlefield attached to a creature you control.")
    effects[0]["host_choice"] = selectors.parse("creatures").key()  # type: ignore[union-attr]
    return effects, groups, optional


def _another_round() -> Parsed:
    """Another Round: you choose any number of creatures you control as it resolves (608.2d, not targets), exile them and return them under their
    owners' control (400.7); the whole process repeats X more times (608.2c: each repeat chooses again, among what is there now)."""
    from app.rules import selectors, values

    key = selectors.parse("creatures you control").key()  # type: ignore[union-attr]
    step: list[dict[str, Any]] = [{"do": "player_chooses", "who": "you", "sel": key, "n": 250, "label": "creatures", "upto": True, "optional": True, "as": "gco"},
            {"do": "exile", "who": "ref:gco", "as": "e0"},
            {"do": "return_card", "who": "ref:e0", "to": "battlefield", "tapped": False, "under": "owner"}]
    return [*step, {"do": "repeat", "n": values.parse_amount("X"), "span": 3}, *copy.deepcopy(step)], None, False


def _spry_and_mighty() -> Parsed:
    """Spry and Mighty: exactly two creatures are chosen as it resolves (608.2d, not targets); X, the difference of the chosen creatures' powers (608.2h),
    is fixed once, then used for the cards drawn and for the +X/+X (the chosen creatures also gain trample)."""
    from app.rules import selectors

    key = selectors.parse("creatures you control").key()  # type: ignore[union-attr]
    x = {"ref_amount": "x110c"}
    return [{"do": "player_chooses", "who": "you", "sel": key, "n": 2, "label": "creatures", "as": "gco"},
            {"do": "power_gap110c", "who": "ref:gco", "bind_amount": "x110c"},
            {"do": "draw", "who": "you", "n": x},
            {"do": "pump", "who": "ref:gco", "p": x, "t": x},
            {"do": "grant", "who": "ref:gco", "keywords": ["trample"]}], None, False


def _slime() -> Parsed:
    """Slime Against Humanity: the counters are put after the token is created (122.1); X = 2 + the cards you own in your graveyard and in exile that are
    Oozes or are named like this one. The two kinds can't overlap (Slime Against Humanity is a sorcery), so the four counts add up exactly."""
    effects, groups, optional = read("Create a 0/0 green Ooze creature token with trample. Put X +1/+1 counters on it, where X is two plus the number of Ooze cards in your graveyard.")
    counts = [read(f"Draw X cards, where X is the number of {what} {where}.")[0][0]["n"] for what in ("Ooze cards", "cards named Slime Against Humanity")
              for where in ("in your graveyard", "you own in exile")]
    effects[1]["n"] = {"plus": [2, *counts]}
    return effects, groups, optional


def _back_for_seconds() -> Parsed:
    """Back for Seconds: bargained (702.166b, read as kicked) the controller may put one chosen target with mana value 4 or less onto the battlefield (608.2d)."""
    effects, groups, optional = read("Return up to two target creature cards from your graveyard to your hand.")
    return [{"do": "kicked_gate", "kicked": False, "n": 1}, *effects, {"do": "kicked_gate", "kicked": True, "n": 1}, {"do": "bargain_return110c"}], groups, optional


BUILDERS: dict[str, Callable[[], Parsed]] = {
    "Return up to two target creature cards from your graveyard to your hand. If this spell was bargained, you may put one of those cards with mana value 4 "
    "or less onto the battlefield instead of putting it into your hand.": _back_for_seconds,
    # (scripts.py reads "bargained" as "kicked", 702.166b, before the body gets here)
    "Return up to two target creature cards from your graveyard to your hand. If this spell was kicked, you may put one of those cards with mana value 4 "
    "or less onto the battlefield instead of putting it into your hand.": _back_for_seconds,
    # 100.2a: a deck-building rule on an instant or sorcery has no effect in the game (on a permanent statics.py reads the same line)
    "A deck can have any number of cards named Slime Against Humanity.": lambda: ([], None, False),
    "Create a 0/0 green Ooze creature token with trample. Put X +1/+1 counters on it, where X is two plus the total number of cards you own in exile "
    "and in your graveyard that are Oozes or are named Slime Against Humanity.": _slime,
    "Choose exactly two creatures you control. You draw X cards and the chosen creatures get +X/+X and gain trample until end of turn, where X is "
    "the difference between the chosen creatures' powers.": _spry_and_mighty,
    "Return each Aura card from your graveyard to the battlefield. Only creatures can be enchanted this way.": _retether,
    "Exile any number of creatures you control, then return them to the battlefield under their owner's control. Then repeat this process X more times.":
        _another_round,
    "Each player reveals a number of cards from the top of their library equal to the number of nonland permanents they control, puts all "
    "permanent cards they revealed this way onto the battlefield, and puts the rest into their graveyard.":
        lambda: ([{"do": "over_the_top110c"}], None, False),
    "Each player exiles all artifact cards from their graveyard, then sacrifices all artifacts they control, then puts all cards they exiled this "
    "way onto the battlefield.": _scrap_mastery,
    "Distribute three +1/+1 counters among one, two, or three target creatures. For each +1/+1 counter you put on a creature this way, remove a "
    "+1/+1 counter from that creature at the beginning of the next cleanup step.": _bounty_of_the_hunt,
    "If the {2}{U} cost was paid, you draw three cards, then an opponent creates two Treasure tokens and they scry 2. If that cost wasn't paid, "
    "you draw X cards.": _ingenious_mastery,
    "If the {2}{W}{W} cost was paid, an opponent chooses up to two nonland permanents they control and returns them to their owner's hand.":
        _devastating_mastery,
    "Each opponent sacrifices a creature they control with the greatest power.":  # (Szat's Will: the wording the grammar reads is "…with the greatest power among creatures they control.")
        lambda: read("Each opponent sacrifices a creature with the greatest power among creatures they control."),
    "Put a +1/+1 counter on each of up to two Soldiers you control.": _soldiers,
    "Destroy all lands or all creatures. Creatures destroyed this way can't be regenerated.": _catastrophe,
}


def parse(body: str) -> Parsed | None:
    build = BUILDERS.get(body.strip())
    return build() if build is not None else None


_MEATHOOK = {  # Meathook Massacre II: 400.7 the card returns as a new object "under your control" (the grammar reads the "to the battlefield" wording)
    "Whenever a creature you control dies, you may pay 3 life. If you do, return that card under your control with a finality counter on it.",
    "Whenever a creature an opponent controls dies, they may pay 3 life. If they don't, return that card under your control with a finality counter on it.",
}


_NEXUS = "If ~ would be put into a graveyard from the battlefield, instead exile it and take an extra turn after this one."


_CHANDRA = "+1: Surveil 1. If you put a noncreature, nonland card into your graveyard this way, put that card into your hand."


def definition(ability: AbilityText, ch: Any) -> dict[str, Any] | None:
    if ability.text.replace("Ugin's Nexus", "~") == _NEXUS:  # 614.6, 500.7: the exile replaces the move; the extra turn is part of the same replacement (rider)
        from app.rules import scripts

        parsed = scripts.parse_effects("Take an extra turn after this one.")
        assert parsed is not None
        return {"kind": "replacement", "replacement": "exile_instead", "from": "battlefield", "effects": [],
                "rider": {"effects": parsed[0], "reflexive": False}}
    if ability.text == _CHANDRA:  # Chandra, Chill of Compliance: surveil 1, then the card goes to hand only if it is a noncreature, nonland card put into the graveyard
        from dataclasses import replace

        from app.rules import scripts

        native = scripts.define(replace(ability, text="+1: Surveil 1."), ch)
        return None if native is None else {**native, "effects": [{"do": "surveil_take110c"}]}
    if ability.text in _MEATHOOK:
        from dataclasses import replace

        from app.rules import scripts

        return scripts.define(replace(ability, text=ability.text.replace("return that card under", "return that card to the battlefield under")), ch)
    return None


# -- carrying it out -----------------------------------------------------------------------------------
def choose_branch(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """``who`` (a player) chooses one of ``options`` ({"label", "effects"}); its effects run in place of this instruction (608.2d)."""
    from app.game.rules_state import DecisionOption
    from app.rules.effects import _players
    from app.rules.plan import decide

    chooser = (_players(plan, ctx, e["who"]) or [ctx["controller"]])[0]
    decide(plan, player=chooser, kind="choose_one", prompt=f"{ctx.get('name') or 'Effect'}: choose one",
           options=[DecisionOption(id=str(i), label=o["label"]) for i, o in enumerate(e["options"])],
           resume={"step": "choose_branch110c", "ctx": ctx, "e": e}, source=plan.state.cards.get(ctx.get("source_card") or ""))
    return False


def resume_branch(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules.effects import continue_effects

    ctx, e = d.resume["ctx"], d.resume["e"]
    if len(chosen) != 1 or chosen[0] not in {o.id for o in d.options}:
        raise ActionError("Choose one of the offered options")
    option = e["options"][int(chosen[0])]
    plan.note(f"{plan.name(d.player)} chooses {option['label'].lower()}", actor=d.player)
    at = ctx["next"]
    ctx["effects"] = [*ctx["effects"][:at], *copy.deepcopy(option["effects"]), *ctx["effects"][at:]]
    continue_effects(plan, ctx)


def temporary_counters(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """One delayed "remove that many of those counters from that creature" per creature that got counters, each bound to the object it was (603.7c)."""
    from app.rules import context, counter_receipts

    steps: list[dict[str, Any]] = []
    for i, entry in enumerate(counter_receipts.placements(ctx, e["receipt"])):
        card = context._same(plan, entry.destination)
        if entry.amount <= 0 or card is None or not card.zone.endswith(":battlefield"):
            continue
        context.bind_objects(plan, ctx, f"_temp110c{i}", [card.id])
        steps += [{"do": "delayed", "when": {"kind": "step", "step": "cleanup", "whose": "next"}, "n": 1},
                  {"do": "deferred:remove_counters", "who": f"ref:_temp110c{i}", "kind": entry.kind, "n": entry.amount}]
    ctx["effects"][ctx["next"]:ctx["next"]] = steps
    return True


def surveil_take(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.25a: surveil 1 looks at the top card; 608.2c the card put into the graveyard this way (read as it is there, 608.2h) returns to hand only if noncreature and nonland."""
    from app.rules import context

    context.bind_objects(plan, ctx, "_surveil110c", plan.state.zones.get(ctx["controller"] + ":library", [])[:1])
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "surveil", "who": "you", "n": 1}, {"do": "surveil_take_end110c"}]
    return True


def surveil_take_end(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context

    context.bind_moved(plan, ctx, "_surveil110c", context._object_refs(ctx, "_surveil110c", was=True))
    found = context.objects(plan, ctx, "_surveil110c")
    card = plan.state.cards[found[0]] if found else None
    if card is None or card.zone != ctx["controller"] + ":graveyard":
        return True
    ch = plan.ch(card)
    if ch.is_creature or "Land" in ch.types:
        return True
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "return_card", "who": "ref:_surveil110c", "to": "hand"}]
    return True


def power_gap(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Binds the difference between the greatest and least power among the chosen creatures (0 if fewer than two could be chosen)."""
    from app.rules import context, values

    powers = [values._stat_of(plan.ch(plan.state.cards[c]), "power") or 0 for c in context.objects(plan, ctx, e["who"].removeprefix("ref:"))]
    context.bind_amount(ctx, e["bind_amount"], max(powers) - min(powers) if powers else 0)
    return True


def bargain_return(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Offers each target card (still in the graveyard, mana value 4 or less) as the one to put onto the battlefield; the other targets go to hand."""
    from app.rules import context
    from app.rules.effects import _cards
    from app.rules.stack_interaction import mana_value

    ids = [c for c in _cards(plan, ctx, "target:0") if plan.state.cards[c].zone.endswith(":graveyard")]
    context.bind_objects(plan, ctx, "_bt110c", ids)
    options: list[dict[str, Any]] = [{"label": "Return them to your hand", "effects": [{"do": "return_card", "who": "ref:_bt110c", "to": "hand", "under": "you"}]}]
    for i in ids:
        if mana_value(plan.state.cards[i], plan.ch(plan.state.cards[i])) <= 4:
            context.bind_objects(plan, ctx, f"_bo110c{i}", [i])
            context.bind_objects(plan, ctx, f"_br110c{i}", [x for x in ids if x != i])
            options.append({"label": f"Battlefield: {plan.state.cards[i].name}", "effects": [
                {"do": "return_card", "who": f"ref:_bo110c{i}", "to": "battlefield", "tapped": False, "under": "you"},
                {"do": "return_card", "who": f"ref:_br110c{i}", "to": "hand", "under": "you"}]})
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "choose_branch110c", "who": "you", "options": options}] if ids else []
    return True


PRIMITIVES = {"bargain_return110c": bargain_return, "power_gap110c": power_gap, "surveil_take110c": surveil_take, "surveil_take_end110c": surveil_take_end, "choose_branch110c": choose_branch, "temporary_counters110c": temporary_counters}
RESUME = {"choose_branch110c": resume_branch}
from app.rules import wave110c_mass  # noqa: E402

PRIMITIVES.update(wave110c_mass.PRIMITIVES)
