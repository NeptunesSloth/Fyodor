"""-- wave 110O -- exact Oracle wordings of single cards, read as native instructions or built from parts of them.

Each entry matches one whole ability's (or spell body's) Oracle text exactly and nothing else; any other wording stays unsupported.
Researched against the Comprehensive Rules of 2026-09-25.
"""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]

# spell body (exact) -> the native wording
REWRITES: dict[str, str] = {}


_REMEMBRANCE = "Shuffle Serene Remembrance and up to three target cards from a single graveyard into their owners' libraries."


_THRALL = ("Gain control of target creature until end of turn. If you control a Villain with greater mana value than that creature, gain control of that "
           "creature until the end of your next turn instead. Untap that creature. It gains haste until end of turn.")


_PORTENT = ("Reveal the top X cards of your library. For each card type, you may exile a card of that type from among them. Put the rest into your graveyard. "
            "You may cast a spell from among the exiled cards without paying its mana cost if you exiled four or more cards this way. Then put the rest of "
            "the exiled cards into your hand.")
_SANDS = "Redistribute any number of players' life totals."


def parse(body: str) -> Any:
    from app.rules import scripts

    if body.strip() == _PORTENT:
        # 701.20a (reveal), 608.2c: one card of each type at most (each exiled card stands for one type), the rest to the graveyard, then the free cast
        # gated on the number exiled (603.4-style count, judged as it is read), then what is still exiled goes to the hand
        look = scripts.parse_effects("Reveal the top X cards of your library. For each card type, you may put a card of that type from among them into your hand. "
                                     "Put the rest into your graveyard.")
        cast = scripts.parse_effects("Exile the top four cards of your library. You may cast a spell from among them without paying its mana cost.")
        assert look and cast and look[0][1]["do"] == "pick_looked" and cast[0][1]["do"] == "free_cast"
        looked, pick, rest = look[0]
        free = {**cast[0][1], "who": "ref:portent110o"}
        return [looked, {**pick, "to": "exile", "as": "portent110o"}, rest, {"do": "only_if", "cond": {"w110o": "portent_four"}, "skip": 1}, free,
                {"do": "portent_hand110o"}], None, False
    if body.strip() == _SANDS:
        return [{"do": "redistribute110o"}], None, False

    if body.strip() == _THRALL:  # 608.2c: the "instead" duration replaces the first one, so exactly one control effect is made
        short = scripts.parse_effects("Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn.")
        long = scripts.parse_effects("Gain control of target creature until the end of your next turn.")
        assert short and long
        (control, *others), (until, long_control) = short[0], long[0]
        bigger = {"w110o": "villain_bigger"}
        return [{"do": "only_if", "cond": bigger, "skip": 2}, until, long_control, {"do": "only_if", "cond": {"not": bigger}, "skip": 1}, control, *others], short[1], False

    if body.strip() == _REMEMBRANCE.replace("Serene Remembrance", "~"):  # 701.24a: the spell and the cards are shuffled in, each owner's library shuffled
        own = scripts.parse_effects("Shuffle ~ into its owner's library.")
        cards = scripts.parse_effects("Shuffle up to three target cards from a single graveyard into their owner's library.")
        assert own and cards
        return [*own[0], *cards[0]], cards[1], False
    return scripts.parse_effects(same) if (same := REWRITES.get(body.strip())) is not None else None


_HELM = ("{X}, {T}: Target opponent mills a card, then repeats this process until a creature card or X cards have been put into their graveyard this way, "
         "whichever comes first. If one or more creature cards were put into that graveyard this way, sacrifice ~ and put one of them onto the "
         "battlefield under your control. X can't be 0.")
_WITCH = ("Whenever ~ deals combat damage to a player, look at the top two cards of your library, then exile them face down. Then you may cast a Hero or "
          "noncreature spell from among cards exiled with ~ without paying its mana cost.")
_RINOA = ("Whenever one or more attacking creatures you control die, you may return one of them to the battlefield tapped under its owner's control with a "
          "flying counter on it. Do this only once each turn.")
_SYRIX_END = ("At the beginning of each end step, if a creature card left your graveyard this turn, target Phoenix you control deals damage equal to its "
              "power to any target.")
_SYRIX_DIES = "Whenever another Phoenix you control dies, you may cast this card from your graveyard."
_LAZAV = ("Whenever you commit a crime, put a +1/+1 counter on ~. Then you may exile a card from a graveyard. If a creature card was exiled this way, you may have "
          "~ become a copy of that card until end of turn. This ability triggers only once each turn.")
_STRIP = ("{3}, {T}: Until end of turn, you may cast instant and sorcery spells from the top of your graveyard. If a spell cast this way would be put into a "
          "graveyard, exile it instead.")
_WITCHES = "{T}: ~ deals 1 damage to any target and 1 damage to any target of an opponent's choice."
_MAGUS = ("{3}, {T}: Tap target creature you control and target creature of an opponent's choice they control. Those creatures fight each other.")
_MINOTAUR = "Whenever you lose a coin flip, ~ deals 1 damage to any target of an opponent's choice."
_WORM = ("Whenever you attack with creatures with total power 12 or greater for the first time each turn, untap all attacking creatures. After this phase, "
         "there is an additional combat phase.")
_PHANTASM = "When ~ enters, if you guessed correctly for a card named Spire Phantasm, draw a card."
_CODIE = "{W}{U}{B}{R}{G}, {T}: Each creature you control becomes prepared."
_OKO_TYPES = "+2: Up to one target creature gains all creature types."
_OKO_EMBLEM = ('−6: Choose a creature type. You get an emblem with "Creatures you control of the chosen type get +3/+3 and have vigilance and '
               'hexproof."')


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import conditions, scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == "loyalty" and text == _OKO_TYPES:  # Oko: 613.1d layer 4, "(This effect doesn't end.)": a permanent effect on the object
        native = scripts.define(replace(ability, text="+2: Up to one target creature gets +0/+0 until end of turn."), ch)
        if native is None:
            return None
        return {**native, "effects": [{"do": "become", "who": "target", "types": [], "all_creature_types": True, "duration": "permanent"}]}
    if ability.kind == "loyalty" and text == _OKO_EMBLEM:
        native = scripts.define(replace(ability, text="−6: You get an emblem with \"Elf creatures you control get +3/+3 and have vigilance and hexproof.\""), ch)
        if native is None:
            return None
        return {**native, "effects": [{"do": "type_emblem110o"}]}
    if ability.kind == "activated" and text == _CODIE:  # 722.3a: each creature that has a prepare spell gains the designation (the effect skips the others)
        from app.rules import selectors

        native = scripts.define(replace(ability, text="{W}{U}{B}{R}{G}, {T}: Target creature becomes prepared."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["prepare"]:
            return None
        return {**native, "target": None, "effects": [{**native["effects"][0], "who": selectors.parse("creature you control").key()}]}  # type: ignore[union-attr]
    if ability.kind == "triggered" and text == _PHANTASM:  # 905.2: a guess is made only during a draft, and a game here has none
        native = scripts.define(replace(ability, text="When ~ enters, draw a card."), ch)
        return None if native is None else {**native, "if": {"w110o": "guessed"}}
    if ability.kind == "triggered" and text == _WORM:  # "for the first time each turn": it triggers only the first time the attack is that strong, 603.2h
        return scripts.define(replace(ability, text=_WORM.replace(" for the first time each turn", "") + " This ability triggers only once each turn."), ch)
    if ability.kind == "triggered" and text == _MINOTAUR:  # "of an opponent's choice": the controller picks the opponent, who announces the target (115.1d-style)
        native = scripts.define(replace(ability, text="Whenever you lose a coin flip, ~ deals 1 damage to any target."), ch)
        return None if native is None else {**native, "target_choice": "opponent110o"}
    if ability.kind == "activated" and text == _WITCHES:  # 115.1d-style delegation: an opponent (the activator's choice) announces the second target
        native = scripts.define(replace(ability, text="{T}: ~ deals 1 damage to any target and 1 damage to any target."), ch)
        if native is None or len(native.get("targets") or []) != 2:
            return None
        return {**native, "delegated_target": "opponent_second"}
    if ability.kind == "activated" and text == _MAGUS:
        native = scripts.define(replace(ability, text="{3}, {T}: Tap target creature you control and target creature an opponent controls."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["tap", "tap"] or len(native.get("targets") or []) != 2:
            return None
        return {**native, "delegated_target": "opponent_second", "delegated_controls110d": True,
                "effects": [*native["effects"], {"do": "fight", "who": "target:0", "with": "target:1"}]}
    if ability.kind == "activated" and text == _STRIP:  # 404.1: only the top card (the last one put there) may be cast, judged as each cast is announced
        native = scripts.define(replace(ability, text=_STRIP.replace("from the top of your graveyard", "from your graveyard")), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["grant_play"]:
            return None
        from app.rules import selectors

        top = selectors.Selector(zones=("graveyard",), card=True, extras=("top_graveyard110o",)).key()
        return {**native, "effects": [{**native["effects"][0], "card_filter": top}]}
    if ability.kind == "triggered" and text == _LAZAV:
        native = scripts.define(replace(ability, text="Whenever you commit a crime, put a +1/+1 counter on ~. This ability triggers only once each turn."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["add_counters"]:
            return None
        return {**native, "effects": [*native["effects"], {"do": "lazav110o"}]}
    if ability.kind == "triggered" and text == _SYRIX_DIES:  # 113.6k: it triggers from the graveyard; 601.2: a normal (paid) cast
        native = scripts.define(replace(ability, text="Whenever another Phoenix you control dies, return this card from your graveyard to the battlefield."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["return_card"]:
            return None
        return {**native, "optional": False, "effects": [{"do": "free_cast", "zone": "that", "who": "self_gy", "filter": None, "optional": True, "mv": None,
                                                           "n": 1, "paid": True}]}
    if ability.kind == "triggered" and text == _SYRIX_END:
        native = scripts.define(replace(ability, text=_SYRIX_END.split(", if ")[0] + ", " + _SYRIX_END.split("this turn, ")[1]), ch)
        if native is None or native.get("if") is not None:
            return None
        return {**native, "if": conditions.parse("a creature card left your graveyard this turn")}
    if ability.kind == "triggered" and text == _RINOA:
        # 700.4: "dies" is the batch that went to the graveyard together; 603.10a looks back at which were attacking (the base trigger); 603.2h the "once"
        base = scripts.define(replace(ability, text=_RINOA.replace(" return one of them to the battlefield tapped under its owner's control with a flying "
                                                                   "counter on it.", " draw a card.")), ch)
        back = scripts.parse_effects("Return target creature card from a graveyard to the battlefield tapped under its owner's control with a flying counter on it.")
        if base is None or back is None or len(back[0]) != 1 or [e["do"] for e in base["effects"]] != ["draw"]:
            return None
        return {**base, "effects": [{"do": "rinoa_pick110o"}, {**back[0][0], "who": "ref:rinoa110o"}]}
    if ability.kind == "triggered" and text == _WITCH:
        # 607.2a: the cards exiled with it by every resolution so far (accumulating link), this resolution's two among them; 406.3b: a face-down card is
        # cast only by a player allowed to look at it (she looked at these two as she exiled them, 406.3)
        native = scripts.define(replace(ability, text=_WITCH.split(" Then")[0] + " Then you may cast a Hero or noncreature spell from among them without paying "
                                                      "its mana cost."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["look_top", "pick_looked", "free_cast"]:
            return None
        look, exile, cast = native["effects"]
        return {**native, "accumulating_link": True,
                "effects": [look, {**exile, "link": True}, {"do": "linked_cards", "as": "witch110o"}, {**cast, "who": "ref:witch110o"}]}
    if ability.kind == "activated" and text == _HELM:
        native = scripts.define(replace(ability, text="{X}, {T}: Target opponent mills a card. X can't be 0."), ch)
        if native is None or [e["do"] for e in native["effects"]] != ["mill"] or native.get("x_min") != 1:
            return None
        mill = {**native["effects"][0], "as": "helm110o"}
        # 701.17a, 608.2c: one card at a time, each its own mill (616.1 replacements ask as usual); the process stops with a creature card or X cards
        # in the graveyard (the total counts cards that really went there)
        return {**native, "effects": [mill, {"do": "helm_test110o"}, {"do": "helm_again110o", "rewind": 3},
                                      {"do": "only_if", "cond": {"w110o": "helm_creature"}, "skip": 2}, {"do": "sacrifice", "who": "self"},
                                      {"do": "helm_pick110o"}]}
    return None


def type_emblem(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Oko, Shadowmoor Scion: the creature type is chosen as the ability resolves (the loyalty ability's controller, 608.2d); the emblem (114.1) then
    names that type, since an emblem keeps no "chosen" value of its own (114.2: it has no source)."""
    from app.game.rules_state import DecisionOption
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.plan import decide

    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a creature type",
           options=[DecisionOption(id=t, label=t) for t in sorted(CREATURE_TYPES)], resume={"step": "type_emblem110o", "ctx": ctx, "e": e})
    return False


def resume_type_emblem(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import designations, effects
    from app.rules.creature_types import CREATURE_TYPES

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in CREATURE_TYPES:
        raise ActionError("Choose one creature type")
    plan.note(f"{plan.name(d.player)} chooses {chosen[0]}", actor=d.player)
    designations.emblem(plan, ctx, {"who": "you", "text": f"{chosen[0]} creatures you control get +3/+3 and have vigilance and hexproof."})
    effects.continue_effects(plan, ctx)


def holds(plan: Plan, ctx: Context, cond: dict[str, Any]) -> bool:
    """Evil's Thrall: you control a Villain whose mana value is greater than the target creature's (the target as it is now, 608.2b)."""
    from app.rules import effects, stack_interaction

    if cond["w110o"] == "guessed":
        return False  # Spire Phantasm: no draft, no guess, so no correct guess (905.2b: the information is noted during the draft)
    if cond["w110o"] == "portent_four":

        return len(_bound(plan, ctx, "portent110o")) >= 4
    if cond["w110o"] == "helm_creature":
        return bool(ctx.get("helm_creatures110o"))
    assert cond["w110o"] == "villain_bigger"
    target = [stack_interaction.mana_value(plan.state.cards[c], plan.ch(plan.state.cards[c])) for c in effects._cards(plan, ctx, "target")]
    return bool(target) and any(
        "Villain" in plan.ch(c).subtypes and stack_interaction.mana_value(c, plan.ch(c)) > target[0]
        for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and c.controller == ctx["controller"])



# -- Reverse the Sands: "Redistribute any number of players' life totals." (119.7-8) ------------------------------------------------------------
def _allowed(plan: Plan, pid: str, total: int) -> bool:
    """119.7-8: a player who can't gain life can't receive a higher total, one who can't lose life no lower one."""
    from app.rules import cant_gain, life_lock

    now = plan.state.players[pid].life
    return not ((total > now and cant_gain.why_not(plan, pid)) or (total < now and life_lock.why_not(plan, pid, "lose")))


def _completable(plan: Plan, players: list[str], totals: dict[str, int], left: list[str], given: dict[str, str]) -> bool:
    """Can the players not yet given a total still all be given one of the totals left (each source once)?"""
    todo = [p for p in players if p not in given]
    if not todo:
        return True
    p = todo[0]
    return any(_allowed(plan, p, totals[src]) and _completable(plan, players, totals, [x for x in left if x != src], {**given, p: src}) for src in left)


def redistribute(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    live = [p for p in plan.apnap() if p in plan.live()]
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: choose any number of players whose life totals are redistributed",
           options=[DecisionOption(id=p, label=f"{plan.name(p)} ({plan.state.players[p].life} life)") for p in live], min_choices=0, max_choices=len(live),
           resume={"step": "redistribute_players110o", "ctx": ctx, "e": e})
    return False


def resume_redistribute_players(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx = d.resume["ctx"]
    live = [p for p in plan.apnap() if p in plan.live()]
    if len(set(chosen)) != len(chosen) or any(p not in live for p in chosen):
        raise ActionError("Choose players still in the game")
    players = [p for p in live if p in chosen]
    if len(players) < 2:  # one player given back their own total, or none: nothing changes
        effects.continue_effects(plan, ctx)
        return
    totals = {p: plan.state.players[p].life for p in players}  # (the totals as the choice is made, 608.2h)
    _next_assignment(plan, ctx, players, totals, {})


def _next_assignment(plan: Plan, ctx: Context, players: list[str], totals: dict[str, int], given: dict[str, str]) -> None:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    todo = [p for p in players if p not in given]
    left = [p for p in players if p not in given.values()]
    p = todo[0]
    options = [src for src in left if _allowed(plan, p, totals[src])
               and _completable(plan, players, totals, [x for x in left if x != src], {**given, p: src})]
    if len(todo) == 1:  # the last total goes to the last player
        _finish(plan, ctx, players, totals, {**given, p: options[0]})
        return
    decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: which life total does {plan.name(p)} get?",
           options=[DecisionOption(id=src, label=f"{totals[src]} (was {plan.name(src)}'s)") for src in options],
           resume={"step": "redistribute_give110o", "ctx": ctx, "players": players, "totals": totals, "given": given})


def resume_redistribute_give(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError

    r = d.resume
    players, totals, given = r["players"], r["totals"], r["given"]
    p = [x for x in players if x not in given][0]
    left = [x for x in players if x not in given.values()]
    if len(chosen) != 1 or chosen[0] not in left or not _allowed(plan, p, totals[chosen[0]]):
        raise ActionError("Choose one of the life totals offered")
    plan.note(f"{plan.name(p)} gets {totals[chosen[0]]}", actor=d.player)
    _next_assignment(plan, r["ctx"], players, totals, {**given, p: chosen[0]})


def _finish(plan: Plan, ctx: Context, players: list[str], totals: dict[str, int], given: dict[str, str]) -> None:
    """An exchange of every chosen player's total (119.7-8, life_changes44.change: replacements, 616.1, are applied there)."""
    from app.rules import effects, life_changes44, replace

    request = {"mode": "exchange", "participants": players, "changes": [[p, totals[given[p]] - plan.state.players[p].life] for p in players],
               "actor": ctx["controller"], "bind": None, "operation": replace._life_operation(plan, None)}
    if life_changes44.change(plan, request, then={"do": "continue", "ctx": ctx}, ctx=ctx):
        effects.continue_effects(plan, ctx)


# -- Helm of Obedience ------------------------------------------------------------------------------------------------------------------------
def helm_test(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """After each mill: the cards that really reached the graveyard count (a replacement may have sent it elsewhere); stop (skip the "repeat") with a
    creature card among them, with X cards in all, or when nothing could be milled (an empty library: the process can't go on)."""
    from app.rules import context

    milled = [c for c in context.objects(plan, ctx, "helm110o") if plan.state.cards[c].zone.endswith(":graveyard")]
    ctx["helm_total110o"] = int(ctx.get("helm_total110o", 0)) + len(milled)
    ctx["helm_creatures110o"] = [*ctx.get("helm_creatures110o", []), *(c for c in milled if "Creature" in plan.ch(plan.state.cards[c]).types)]
    if ctx["helm_creatures110o"] or ctx["helm_total110o"] >= int(ctx.get("x") or 0) or not context.objects(plan, ctx, "helm110o"):
        ctx["next"] += 1
    return True


def helm_again(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    ctx["next"] -= e["rewind"]
    return True


def helm_pick(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Put one of them onto the battlefield under your control": the only creature card, else the controller picks one (608.2d)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    found = [c for c in ctx.get("helm_creatures110o", []) if plan.state.cards[c].zone.endswith(":graveyard")]
    if len(found) > 1:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a creature card to put onto the battlefield",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "a card", card_id=c) for c in found],
               resume={"step": "helm_pick110o", "ctx": ctx})
        return False
    return _put_onto_battlefield(plan, ctx, found[0]) if found else True


def _put_onto_battlefield(plan: Plan, ctx: Context, cid: str) -> bool:
    from app.rules import context, effects

    context.bind_objects(plan, ctx, "helm_pick110o", [cid])
    return bool(effects.PRIMITIVES["return_card"](plan, ctx, {"do": "return_card", "who": "ref:helm_pick110o", "to": "battlefield", "tapped": False, "under": "you"}))


def resume_helm_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in ctx.get("helm_creatures110o", []):
        raise ActionError("Choose one of the creature cards offered")
    if _put_onto_battlefield(plan, ctx, chosen[0]):
        effects.continue_effects(plan, ctx)


def _bound(plan: Plan, ctx: Context, name: str) -> list[str]:
    """The objects of the binding called ``name`` (a spell's lines get the line number as a prefix, scripts.rename_bindings: l0_name)."""
    from app.rules import context

    return [c for key in context.refs(ctx) if key == name or key.endswith("_" + name) for c in context.objects(plan, ctx, key)]


def portent_hand(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """Portent of Calamity: what is still exiled of the cards exiled this way goes into the controller's hand (a cast one is on the stack, or beyond)."""
    rest = [c for c in _bound(plan, ctx, "portent110o") if plan.state.cards[c].zone.endswith(":exile")]
    if rest:
        plan.do({"type": "move", "card_ids": rest, "to": {"player": ctx["controller"], "zone": "hand"}}, actor=ctx["controller"])
    return True


# -- Rinoa, Angel Wing -------------------------------------------------------------------------------------------------------------------------
def rinoa_pick(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Return one of them": the controller picks one of the creature cards that died together and are still in a graveyard (608.2d)."""
    from app.game.rules_state import DecisionOption
    from app.rules import context
    from app.rules.plan import decide

    found = [c for c in context.objects(plan, ctx, context.EVENT_NEW) if plan.state.cards[c].zone.endswith(":graveyard")]
    if len(found) > 1:
        decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: choose a creature to return",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "a card", card_id=c) for c in found],
               resume={"step": "rinoa_pick110o", "ctx": ctx})
        return False
    context.bind_objects(plan, ctx, "rinoa110o", found)
    return True


def resume_rinoa_pick(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects

    ctx = d.resume["ctx"]
    if len(chosen) != 1 or chosen[0] not in context.objects(plan, ctx, context.EVENT_NEW):
        raise ActionError("Choose one of the creatures that died")
    context.bind_objects(plan, ctx, "rinoa110o", chosen)
    effects.continue_effects(plan, ctx)


# -- Lazav, Familiar Stranger --------------------------------------------------------------------------------------------------------------
def lazav(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """"Then you may exile a card from a graveyard" (not a target: any graveyard, chosen as the ability resolves, 608.2d)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    cards = [c.id for c in plan.state.cards.values() if c.zone.endswith(":graveyard") and plan.in_game(c)]
    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: exile a card from a graveyard?",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name or "a card", card_id=c) for c in cards], min_choices=0, max_choices=1,
           resume={"step": "lazav110o", "ctx": ctx})
    return False


def resume_lazav(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, effects
    from app.rules.plan import decide

    ctx = d.resume["ctx"]
    if len(chosen) > 1 or any(not plan.state.cards[c].zone.endswith(":graveyard") for c in chosen):
        raise ActionError("Choose at most one card from a graveyard")
    if chosen:
        card = plan.state.cards[chosen[0]]
        plan.do({"type": "move", "card_ids": chosen, "to": {"player": card.owner, "zone": "exile"}}, actor=ctx["controller"])
        context.bind_objects(plan, ctx, "lazav110o", chosen)
        if "Creature" in plan.ch(plan.state.cards[chosen[0]]).types:
            from app.game.rules_state import DecisionOption

            decide(plan, player=ctx["controller"], kind="choose_one", prompt=f"{ctx.get('name') or 'It'}: become a copy of {card.name}?",
                   options=[DecisionOption(id="yes", label="Become a copy"), DecisionOption(id="no", label="Don't")],
                   resume={"step": "lazav_copy110o", "ctx": ctx})
            return
    effects.continue_effects(plan, ctx)


def resume_lazav_copy(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    if chosen == ["yes"] and not effects.PRIMITIVES["become_copy"](plan, ctx, {"do": "become_copy", "who": "self", "with": "ref:lazav110o", "duration": "end_of_turn"}):
        return
    effects.continue_effects(plan, ctx)


PRIMITIVES: dict[str, Any] = {"type_emblem110o": type_emblem, "redistribute110o": redistribute,
              "helm_test110o": helm_test, "helm_again110o": helm_again, "helm_pick110o": helm_pick, "portent_hand110o": portent_hand, "rinoa_pick110o": rinoa_pick, "lazav110o": lazav}
RESUME: dict[str, Any] = {"type_emblem110o": resume_type_emblem, "redistribute_players110o": resume_redistribute_players,
                          "redistribute_give110o": resume_redistribute_give, "helm_pick110o": resume_helm_pick, "rinoa_pick110o": resume_rinoa_pick, "lazav110o": resume_lazav, "lazav_copy110o": resume_lazav_copy}
