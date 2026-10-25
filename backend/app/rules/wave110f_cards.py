"""-- cards (wave 110F) -- exact Oracle bodies of PARTIAL cards, read onto existing machinery. ``BUILDERS``: whole spell body -> parsed effects."""
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

Parsed = tuple[list[dict[str, Any]], Any, bool]


def _p(text: str) -> Parsed:
    from app.rules import scripts

    got = scripts.parse_effects(text)
    if got is None:
        raise AssertionError(f"wave110f: the grammar no longer reads {text!r}")
    return copy.deepcopy(got)


def _rivals_duel() -> Parsed:
    """Rivals' Duel: two targets that share no creature types (601.2c, 205.3m) fight each other (701.14a-b: one gone, no fight)."""
    _, targets, optional = _p("Choose two target creatures that share a creature type.")
    spec = targets[0]
    spec["shares_none"] = spec.pop("shares")
    return [{"do": "fight", "who": "target:0", "twin110f": True}], targets, optional


def _dead_ringers() -> Parsed:
    """Dead Ringers: "unless either one is a color the other isn't" = destroy only when both targets have exactly the same colors (105.2)."""
    effects, targets, optional = _p("Destroy two target nonblack creatures. They can't be regenerated.")
    return [{"do": "same_colors110f", "skip": len(effects)}, *effects], targets, optional


def same_colors(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Skip the next ``skip`` effects unless the two chosen targets (both still legal, 608.2b) have the same set of colors.
    ponytail: with one target gone nothing is destroyed (the other's colors can't be compared)."""
    from app.rules import effects

    cards = effects._cards(plan, ctx, "target:0")
    if len(cards) != 2 or len({frozenset(plan.ch(plan.state.cards[c]).colors) for c in cards}) != 1:
        ctx["next"] = min(len(ctx["effects"]), ctx["next"] + int(e["skip"]))
    return True


def _taunt() -> Parsed:
    """Taunt: for the target player's next turn (611.2a, restrict ``their_turn``), their creatures, those arriving later too (611.2c), attack the
    controller if able (508.1d; ``attack_player``, as encore's tokens)."""
    effects, targets, optional = _p("Creatures target player controls attack this turn if able.")
    assert effects[0]["rules"] == ["must_attack"]
    return [{**effects[0], "rules": ["attack_player:@you"], "duration": "their_turn"}], targets, optional


def _don_and_leo() -> Parsed:
    """Don & Leo: exile both targets (up to one each), then return each under its owner's control (400.7: new objects; 614.1 nothing if no target)."""
    effects, targets, optional = _p("Exile up to one target artifact you control and up to one target creature you control.")
    effects = [{**effects[0], "as": "e0"}, {**effects[1], "as": "e1"}]
    back = {"do": "return_card", "to": "battlefield", "tapped": False, "under": "owner"}
    return [*effects, {**back, "who": "ref:e0"}, {**back, "who": "ref:e1"}], targets, optional


def phase_swap(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Time and Tide: 702.26a-d: at once, every phased-out creature phases in (702.26g: not one that is phased out indirectly, it comes with its
    host) and every phased-in creature with phasing phases out. The phasing set is read before anything moves, so a creature that just phased in stays."""
    from app.game.rules_state import emit
    from app.game.state import zone_key

    state = plan.state
    out = [c for p in state.players for c in state.zones.get(zone_key(p, "battlefield"), [])
           if "Creature" in plan.ch(state.cards[c]).types and "phasing" in plan.ch(state.cards[c]).keywords]
    back = [c for p in state.players for c in state.zones.get(zone_key(p, "phased"), [])
            if not state.cards[c].phased_indirect and "Creature" in plan.ch(state.cards[c]).types]
    for c in back:  # (as phasing.untap_step: "whenever ~ phases in" watchers)
        emit(state, "designation", counter="phase_in", card=c, object_id=plan.oid(c), player=state.cards[c].controller)
    if back:
        plan.do({"type": "phase_shift", "card_ids": back, "out": False}, actor=ctx["controller"])
    if out:
        plan.do({"type": "phase_shift", "card_ids": out, "out": True}, actor=ctx["controller"])
    return True


def _time_and_tide() -> Parsed:
    return [{"do": "phase_swap110f"}], None, False


def exile_discarded(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Toluz: exile the discarded cards still in your graveyard, linked to the source (607.2a); one trigger per batch (603.2c)."""
    from app.rules import context, effects

    cards = [c for c in context.objects(plan, ctx, "event.new") if plan.state.cards[c].zone == ctx["controller"] + ":graveyard"]
    return effects.exile_cards(plan, ctx, {"link": True}, cards)


def _regatha() -> Parsed:
    """Invasion of Regatha: "another target battle or opponent" = target opponent or battle other than this Siege (115.4)."""
    effects, targets, optional = _p("~ deals 4 damage to target opponent or battle and 1 damage to up to one target creature.")
    targets[0]["what"] = "opponent_or_other_battle110f"
    return effects, targets, optional


def turn_up_choice(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Bustle: "You may turn a creature you control face up." Its controller picks one of their face-down creatures, or none (701.40g via facedown._turn_up)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    pid = ctx["controller"]
    cards = [c for c in plan.state.cards.values() if c.face_down and c.controller == pid and c.zone.endswith(":battlefield")]
    if not cards:
        return True
    decide(plan, player=pid, kind="choose_cards", prompt="Bustle: you may turn a creature you control face up",
           options=[DecisionOption(id=c.id, label=c.name, card_id=c.id) for c in cards], min_choices=0, max_choices=1,
           resume={"step": "turn_up_choice110f", "ctx": ctx})
    return False


def resume_turn_up(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects, facedown

    if chosen and facedown._turn_up(plan, chosen[0], d.player):
        plan.note(f"{plan.name(d.player)} turns {plan.state.cards[chosen[0]].name} face up")
    effects.continue_effects(plan, d.resume["ctx"])


def reveal_chroma(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Phosphorescent Feast: reveal any number of cards from your hand (701.20a: shown to all, they stay in the hand), then gain 2 life for
    each green mana symbol in their mana costs (a hybrid symbol with green counts, 202.2d)."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    pid = ctx["controller"]
    hand = list(plan.state.zones.get(f"{pid}:hand", []))
    if not hand:
        return True
    decide(plan, player=pid, kind="choose_cards", prompt="Reveal any number of cards in your hand (2 life per green mana symbol in their costs)",
           options=[DecisionOption(id=c, label=plan.state.cards[c].name, card_id=c) for c in hand], min_choices=0, max_choices=len(hand),
           resume={"step": "reveal_chroma110f", "ctx": ctx})
    return False


def resume_reveal_chroma(plan: Any, d: Any, chosen: list[str]) -> None:
    import re

    from app.rules import effects

    ctx = d.resume["ctx"]
    hand = plan.state.zones.get(f"{d.player}:hand", [])
    shown = [c for c in dict.fromkeys(chosen) if c in hand]
    if shown:
        plan.do({"type": "reveal", "card_ids": shown}, actor=d.player)
        n = sum(1 for c in shown for sym in re.findall(r"\{([^}]*)\}", plan.ch(plan.state.cards[c]).mana_cost or "") if "G" in sym.split("/"))
        ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "gain_life", "who": "you", "n": 2 * n}]
    effects.continue_effects(plan, ctx)


def _bustle() -> Parsed:
    effects, targets, optional = _p("Creatures you control get +2/+2 and gain trample until end of turn.")
    return [*effects, {"do": "turn_up_choice110f"}], targets, optional


def _keybearer() -> Parsed:
    effects, targets, optional = _p("tap up to one target Room you control.")
    return [{"do": "unlock110f", "who": effects[0]["who"]}], targets, optional


def unlock(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Ghostly Keybearer: "unlock a locked door of up to one target Room you control" (709.5f: the designation, whatever the means; 709.5h triggers).
    One locked door: that one. Both locked: its controller picks (a Room with no door unlocked can only get here by entering any way but cast)."""
    from app.game.rules_state import DecisionOption
    from app.rules import characteristics as chars
    from app.rules import effects, rooms
    from app.rules.copying import room_printing
    from app.rules.plan import decide

    for cid in effects._cards(plan, ctx, e["who"]):
        card = plan.state.cards[cid]
        if not card.zone.endswith(":battlefield") or card.controller != ctx["controller"] or plan.ch(card).doors is None:
            continue
        locked = [d for d in (1, 2) if d not in rooms.doors_of(plan, cid)]
        if len(locked) == 2:
            data = plan.info.get(room_printing(plan.rules, card, plan.oid(card))) or {}
            decide(plan, player=ctx["controller"], kind="choose_cards", prompt="Unlock a locked door",
                   options=[DecisionOption(id=str(d), label=chars.half_from_data(data, d - 1).name) for d in locked], min_choices=1, max_choices=1,
                   resume={"step": "unlock110f", "ctx": ctx, "card": cid})
            return False
        if locked:
            rooms.unlock(plan, cid, locked[0])
    return True


def resume_unlock(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects, rooms

    rooms.unlock(plan, d.resume["card"], int(chosen[0]))
    effects.continue_effects(plan, d.resume["ctx"])


def _blink() -> Parsed:
    """Blink chapters I, III: the target's owner (108.3) shuffles it into their library (701.24), then that player investigates (701.16a)."""
    effects, targets, optional = _p("Shuffle target creature into its owner's library.")
    clue = _p("Investigate.")[0][0]
    return [*effects, {**clue, "who": "target_owner"}], targets, optional


def _not_creature() -> Parsed:
    """Alien Angel token: 205.1b, a continuing type-removing effect for the turn (611.2a); "this token" = the permanent itself."""
    effects, targets, optional = _p("~ loses all abilities until end of turn.")
    return [{**{k: v for k, v in effects[0].items() if k != "lose_abilities"}, "remove_types": ["Creature"]}], targets, optional


def _gatekeeper() -> Parsed:
    """Unyielding Gatekeeper: exile (LKI of its controller, 603.10), then either back tapped under its OWNER's control (110.2, 400.7: a stolen
    permanent goes home) if you controlled it, or its controller creates the Detective."""
    effects, targets, optional = _p("Exile another target nonland permanent. If you controlled it, return it to the battlefield tapped.")
    effects[2]["under"] = "owner"
    token = _p("Exile target nonland permanent. Its controller creates a 2/2 white and blue Detective creature token.")[0][1]
    gate = copy.deepcopy(effects[1])
    return [*effects, {**gate, "cond": {"not": gate["cond"]}}, token], targets, optional


def _sparkshaper() -> Parsed:
    """Sparkshaper Visionary: any number (115.4, min 0) of your planeswalkers become 3/3 blue Bird creatures (205.1a: set types, so no longer
    planeswalkers; 611.2a until end of turn; their loyalty abilities stay usable) with flying, hexproof and the scry trigger."""
    effects, sel, optional = _p('Target planeswalker you control becomes a 3/3 blue Bird creature with flying and hexproof until end of turn. '
                                'It gains "Whenever this creature deals combat damage to a player, scry 1" until end of turn.')
    return [{**e, "who": "target:0"} for e in effects], [{"what": sel, "min": 0, "max": 250}], optional


BUILDERS: dict[str, Callable[[], Parsed]] = {
    'choose any number of target planeswalkers you control. Until end of turn, they become 3/3 blue Bird creatures with flying, hexproof, and "Whenever ~ deals combat damage to a player, scry 1."': _sparkshaper,
    "exile another target nonland permanent. If you controlled it, return it to the battlefield tapped. Otherwise, its controller creates a 2/2 white and blue Detective creature token.": _gatekeeper,
    "Choose target creature. Its owner shuffles it into their library, then investigates.": _blink,
    "this token isn't a creature until end of turn.": _not_creature,
    "unlock a locked door of up to one target Room you control.": _keybearer,
    "Reveal any number of cards in your hand. You gain 2 life for each green mana symbol in those cards' mana costs.":
        lambda: ([{"do": "reveal_chroma110f"}], None, False),
    "Creatures you control get +2/+2 and gain trample until end of turn. You may turn a creature you control face up.": _bustle,
    "it deals 4 damage to another target battle or opponent and 1 damage to up to one target creature.": _regatha,
    "exile them from your graveyard.": lambda: ([{"do": "exile_discarded110f", "exile": True}], None, False),  # ("exile": marks the linking ability, exiled_with._exiles)
    "Simultaneously, all phased-out creatures phase in and all creatures with phasing phase out.": _time_and_tide,
    "exile up to one target artifact you control and up to one target creature you control. Then return them to the battlefield under their owners' control.": _don_and_leo,
    "During target player's next turn, creatures that player controls attack you if able.": _taunt,
    "Destroy two target nonblack creatures unless either one is a color the other isn't. They can't be regenerated.": _dead_ringers,
    "Choose two target creatures that share no creature types. Those creatures fight each other.": _rivals_duel,
}
# Sentences the grammar reads in other words (608.2c). 509.1g: while a combat phase is going (the only time the "dies during combat" trigger fires),
# "the creatures it blocked this combat" are the creatures blocked by it (block_events reads them off its last known information).
REWRITES = {
    # 506.4, 508.1d, 509.1c: only one of the two can apply in a given turn (it attacks on its controller's turn, blocks on another's).
    "Target creature attacks or blocks this turn if able.": "Target creature attacks this turn if able. That creature blocks this turn if able.",
    "put the cards exiled with it into their owner's hand.": "return all cards exiled with it to their owners' hands.",  # Toluz (607.2a)
    # 601.2h, 107.3: "a number of tokens equal to the amount of mana spent" = X tokens, X the amount of mana spent to cast it.
    "create a number of 1/1 black Fungus Zombie creature tokens named Cordyceps Infected equal to the amount of mana spent to cast this spell.":
        "create X 1/1 black Fungus Zombie creature tokens named Cordyceps Infected, where X is the amount of mana spent to cast this spell.",
    # 611.2 / 122.1: control change then the counter on the same (still targeted) creature, as two sentences.
    "Gain control of target nonartifact, nonblack creature that attacked you this turn and put a -1/-0 counter on it.":
        "Gain control of target nonartifact, nonblack creature that attacked you this turn, then put a -1/-0 counter on it.",
    "it deals 6 damage to each creature it blocked this combat.": "~ deals 6 damage to each creature blocked by it.",
}
PRIMITIVES: dict[str, Any] = {"same_colors110f": same_colors, "phase_swap110f": phase_swap, "exile_discarded110f": exile_discarded, "turn_up_choice110f": turn_up_choice, "reveal_chroma110f": reveal_chroma, "unlock110f": unlock}
RESUME: dict[str, Any] = {"turn_up_choice110f": resume_turn_up, "reveal_chroma110f": resume_reveal_chroma, "unlock110f": resume_unlock}


def parse(body: str) -> Parsed | None:
    from app.rules import scripts

    build = BUILDERS.get(body.strip())
    if build is not None:
        return build()
    return scripts.parse_effects(REWRITES[body.strip()]) if body.strip() in REWRITES else None
