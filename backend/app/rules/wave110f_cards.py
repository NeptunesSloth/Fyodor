"""-- cards (wave 110F) -- exact Oracle bodies of PARTIAL cards, read onto existing machinery. ``BUILDERS``: whole spell body -> parsed effects."""
from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

from app.game.errors import ActionError

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


def _fires() -> Parsed:
    """Fires of Mount Doom: "that creature" is the target (608.2c), not the trigger's event object (the entering Fires); SBAs wait for the resolution (704.3), so a
    creature the damage kills still has its Equipment attached."""
    effects, targets, optional = _p("~ deals 2 damage to target creature an opponent controls. Destroy all Equipment attached to it.")
    return json.loads(json.dumps(effects).replace("att@pron", "att@target")), targets, optional


_TYPES = ("Artifact", "Creature", "Enchantment", "Land", "Planeswalker")


def _release() -> Parsed:
    """Release: one permanent of each type, of their choice (101.4: APNAP, each knowing the earlier choices), all sacrificed at once (701.21a). One permanent can be
    sacrificed only once, so it fills one kind (the Structural Collapse reading); a player must fill as many kinds as they can (matching, below)."""
    from app.rules import selectors

    kinds = [selectors.Selector(types=(k,)).key() for k in _TYPES]
    return [{"do": "edict_match110f", "who": "each_player", "sels": kinds, "labels": [k.lower() for k in _TYPES], "n": 1, "sel": kinds[0], "label": "permanent"}], None, False


def edict_match(plan: Any, ctx: Any, e: dict[str, Any]) -> bool:
    from app.rules import effects

    who = effects._players(plan, ctx, e["who"])
    return effects._choose_next(plan, ctx, {**e, "matching110f": True}, [(p, k) for p in plan.apnap() if p in who for k in e["sels"]], [], "edict")


def _most(sets: list[set[str]]) -> int:
    """The most distinct objects that can fill the kinds (one each): sets[i] are the objects fit for kind i."""
    if not sets:
        return 0
    first, rest = sets[0], sets[1:]
    return max([_most(rest), *(1 + _most([s - {c} for s in rest]) for c in first)])


def matching(plan: Any, ctx: Any, e: dict[str, Any], pid: str, mine: list[str], picked: list[str], later: list[str]) -> list[str]:
    """effects._choose_next (edict_match110f): the permanents that still let this player fill as many kinds as they can (an object fills one kind only)."""
    from app.rules import effects

    taken = set(picked)
    now = {c for c in mine if c not in taken}
    after = [set(effects._controlled(plan, k, pid, ctx.get("source_card"))) - taken for k in later]
    best = _most([now, *after])
    return [c for c in mine if c in now and 1 + _most([s - {c} for s in after]) == best]


BLOCK_LIFE = "block_life110f"
_BLOCK_LIFE_TEXT = "Nonblue creatures can't block creatures you control unless their controller pays 1 life for each blocking creature they control."


def block_life_definition(text: str) -> dict[str, Any] | None:
    return {"kind": "static", "static": BLOCK_LIFE, "effects": []} if text.strip() == _BLOCK_LIFE_TEXT else None


def block_life_due(plan: Any, blocks: Any) -> int:
    """Heat Wave (509.1c-d, 118.3): 1 life from the blocking player for each nonblue creature they control that blocks a creature its controller controls
    (a creature blocking several of them is one blocking creature)."""
    from app.rules import scripts

    due = 0
    for source in plan.state.cards.values():
        if not source.zone.endswith(":battlefield") or not plan.in_game(source) or plan.manual(source):
            continue
        if not any(d.get("static") == BLOCK_LIFE for d in scripts.definitions(plan.ch(source)).values()):
            continue
        due += len({b.blocker_id for b in blocks if (att := plan.state.cards.get(b.attacker_id)) is not None and att.controller == source.controller
                    and "U" not in plan.ch(plan.state.cards[b.blocker_id]).colors})
    return due


def block_life_problem(plan: Any, blocks: Any) -> str | None:
    due = block_life_due(plan, blocks)
    if not due:
        return None
    from app.rules import life_lock

    if plan.state.players[plan.actor].life < due:
        return f"Blocking costs {due} life (509.1d): {plan.name(plan.actor)} can't pay it"  # 119.4
    return life_lock.pay_problem(plan.state, plan.info, plan.actor, due)


def pay_block_life(plan: Any, blocks: Any) -> None:
    if due := block_life_due(plan, blocks):
        from app.rules import replace

        replace.lose_life(plan, [(plan.actor, due)], paid=True)


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


def _remove_sets(plan: Any, me: str) -> tuple[list[str], list[str]]:
    """Remove Enchantments: (returned, other) -- the first group, then the "other" ones the destroy half takes (608.2c, 303.4)."""
    ret: list[str] = []
    other: list[str] = []
    for c in plan.state.cards.values():
        if not c.zone.endswith(":battlefield") or not plan.in_game(c):
            continue
        ch = plan.ch(c)
        host = plan.state.cards.get(c.attached_to or "")
        hosted = host is not None and host.zone.endswith(":battlefield")
        aura = "Aura" in ch.subtypes and hosted
        mine = aura and host.controller == me
        hit_attacker = aura and host.controller != me and host.attacking is not None
        if "Enchantment" in ch.types or aura:
            if c.owner == me and ((c.controller == me and "Enchantment" in ch.types) or mine or hit_attacker):
                ret.append(c.id)
            elif (c.controller == me and "Enchantment" in ch.types) or mine or hit_attacker:
                other.append(c.id)
    return ret, other


def barrier_direction(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Mystic Barrier: the last chosen direction replaces the earlier one (the restriction is combat_teyo66's, 508.1d) for as long as it stays."""
    from app.rules import combat_teyo66, layers, selectors

    value = (ctx.get("refs") or {}).get("direction110f", {}).get("value")
    if value not in ("left", "right"):
        return True
    r = plan.rules
    r.effects = [x for x in r.effects if not (x.source == ctx.get("source_object") and any(i.startswith(combat_teyo66.FIXED) for i in x.imposes))]
    layers.add_effect(plan, affected=[], layer="6", source=ctx.get("source_object"), controller=ctx["controller"],
                      who=selectors.Selector(types=("Creature",)).key(), source_card=ctx.get("source_card"),
                      imposes=(combat_teyo66.FIXED + value,), duration="source_on_battlefield", label="Attacks only " + value)  # type: ignore[arg-type]
    return True


def remove_enchantments(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import effects

    ret, other = _remove_sets(plan, ctx["controller"])
    if e["step"] == "return":
        if ret:
            plan.do({"type": "move", "card_ids": ret, "to": {"zone": "hand"}}, actor=ctx["controller"])
        return True
    return effects._destroy_cards(plan, ctx, {"do": "destroy"}, other)


def _snitch() -> Parsed:
    """Cephalid Snitch: layer-6 removal of one quality; protection.parse drops the words named in ``Characteristics.lost`` (613.1f, 702.16)."""
    effects, targets, optional = _p("Target creature loses flying until end of turn.")
    assert effects[0]["remove"] == ["flying"]
    return [{**effects[0], "remove": ["protection from black"]}], targets, optional


def vapors(plan: Any, ctx: dict[str, Any], e: dict[str, Any], st: dict[str, Any] | None = None) -> bool:
    """Noxious Vapors: each player (APNAP, 101.4) reveals their hand (701.20a) and chooses one card of each color from it; every other nonland card is
    discarded at once. 105.2b: a multicolored card is each of its colors, so a card chosen for one of its colors is the chosen card of the others too (a color with a single
    card in hand has nothing to choose). Colorless nonland cards are of no color, so are never chosen."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    st = st or {"todo": list(plan.apnap()), "keep": [], "colors": None, "toss": []}
    while st["todo"]:
        pid = st["todo"][0]
        hand = list(plan.state.zones.get(f"{pid}:hand", []))
        if st["colors"] is None:
            if hand:
                plan.do({"type": "reveal", "card_ids": hand}, actor=pid)
            st["colors"] = [c for c in "WUBRG" if any(c in plan.ch(plan.state.cards[x]).colors for x in hand)]
        while st["colors"]:
            color = st["colors"][0]
            of_color = [x for x in hand if color in plan.ch(plan.state.cards[x]).colors]
            if any(x in st["keep"] for x in of_color):  # already chosen as another color's card (105.2b): it is this color's card too
                st["colors"].pop(0)
                continue
            if len(of_color) > 1:
                decide(plan, player=pid, kind="choose_one", prompt=f"Choose one card of color {color} from your hand",
                       options=[DecisionOption(id=x, label=plan.state.cards[x].name, card_id=x) for x in of_color],
                       resume={"step": "vapors110f", "ctx": ctx, "e": e, "st": st})
                return False
            st["keep"] += of_color
            st["colors"].pop(0)
        st["toss"] += [x for x in hand if x not in st["keep"] and "Land" not in plan.ch(plan.state.cards[x]).types]
        st["todo"].pop(0)
        st["colors"] = None
    return effects._discard_next(plan, ctx, 0, [], st["toss"], None)


def resume_vapors(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    st = d.resume["st"]
    st["keep"].append(chosen[0])
    st["colors"].pop(0)
    if vapors(plan, d.resume["ctx"], d.resume["e"], st):
        effects.continue_effects(plan, d.resume["ctx"])


BUILDERS: dict[str, Callable[[], Parsed | None]] = {
    "Each player reveals their hand, chooses one card of each color from it, then discards all other nonland cards.": lambda: ([{"do": "vapors110f"}], None, False),
    "Each player sacrifices an artifact, a creature, an enchantment, a land, and a planeswalker of their choice.": _release,
    "it deals 2 damage to target creature an opponent controls. Destroy all Equipment attached to that creature.": _fires,
    "Destroy up to two target creatures the chosen player controls. They can't be regenerated. The chosen player draws up to three cards.": lambda: _lore(),
    "Target creature loses protection from black until end of turn.": _snitch,
    "Return to your hand all enchantments you both own and control, all Auras you own attached to permanents you control, and all Auras you own attached to attacking creatures your opponents control. Then destroy all other enchantments you control, all other Auras attached to permanents you control, and all other Auras attached to attacking creatures your opponents control.":
        lambda: ([{"do": "remove_enchantments110f", "step": "return"}, {"do": "remove_enchantments110f", "step": "destroy"}], None, False),
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
    "You gain 3 life plus an additional 3 life for each additional {1}{G} you paid.": "You gain 3 life. You gain 3 life for each time this spell was kicked.",  # Taste of Paradise (702.33c)
    "Destroy target attacking creature, then put this card on top of your library.": "Destroy target attacking creature. Put ~ on top of your library.",  # Vengeful Pharaoh
                "it deals 6 damage to each creature it blocked this combat.": "~ deals 6 damage to each creature blocked by it.",
}
PRIMITIVES: dict[str, Any] = {"barrier_direction110f": barrier_direction, "remove_enchantments110f": remove_enchantments, "same_colors110f": same_colors, "phase_swap110f": phase_swap, "exile_discarded110f": exile_discarded, "turn_up_choice110f": turn_up_choice, "reveal_chroma110f": reveal_chroma, "unlock110f": unlock, "vapors110f": vapors}
RESUME: dict[str, Any] = {"vapors110f": resume_vapors, "turn_up_choice110f": resume_turn_up, "reveal_chroma110f": resume_reveal_chroma, "unlock110f": resume_unlock}


# 905.2 / 103.6: nothing is drafted in Commander, so these cards never have a card, note or chosen color (app/rules/draft_only.py).
# Each wording below is an explicit do-nothing effect (no "gain 0 life" text shown to players), not a guess at a rules result.
DRAFT_NOTHING = {
    "copy a card you exiled with cards named Arcane Savant. You may cast the copy without paying its mana cost.",
    "Create a token that's a copy of a card you exiled with cards named Caller of the Untamed. X is the mana value of that card.",
    "Choose a card at random you exiled with cards named Volatile Chimera. ~ becomes a copy of that card, except it has this ability.",
}
GARBAGE_FIRE = "~ deals damage to target creature equal to the highest number you noted for cards named Garbage Fire."  # target kept, nothing was noted
REGICIDE = "Destroy target creature that's one or more of the colors chosen as you drafted cards named Regicide."


def nothing_drafted(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Nothing was drafted, exiled or noted, so there is nothing to do."""
    return True


PRIMITIVES["nothing_drafted110f"] = nothing_drafted


def _draft_parse(body: str) -> Any:
    from app.rules import selectors

    if body in DRAFT_NOTHING:
        return [{"do": "nothing_drafted110f"}], None, False
    if body == GARBAGE_FIRE:
        return [{"do": "nothing_drafted110f", "who": "target"}], "creature", False
    if body == REGICIDE:  # no color was chosen, so no creature is one of them: a selector that matches nothing (a creature that is not a creature), hence no legal target
        return [{"do": "destroy", "who": "target"}], selectors.Selector(types=("Creature",), not_types=("Creature",)).key(), False
    return None


def parse(body: str) -> Parsed | None:
    from app.rules import scripts

    if (drafted := _draft_parse(body.strip())) is not None:
        return drafted

    build = BUILDERS.get(body.strip())
    if build is not None:
        return build()
    return scripts.parse_effects(REWRITES[body.strip()]) if body.strip() in REWRITES else None


_THUNDERBLADE = ("Whenever one or more creatures you control deal combat damage to a player, if this card is in your graveyard, you may pay {2}{R}{R}{R}. "
                 "If you do, you may cast it without paying its mana cost.")
SPLIT_DAMAGE = "single_source_lethal110f"
_SPLIT_TEXT = "This creature can't be destroyed by lethal damage unless lethal damage dealt by a single source is marked on it."


def spared_by_split_damage(plan: Any, card: Any, ch: Any, toughness: int) -> bool:
    """Ogre Enforcer: 704.5g applies only if lethal damage (>= toughness, 120.6) from one source is still marked on it (card.damage_by: damage removed
    by regeneration, "remove all damage" or cleanup no longer counts)."""
    from app.rules import scripts

    if not any(d.get("static") == SPLIT_DAMAGE for d in scripts.definitions(ch).values()):
        return False
    return max(card.damage_by.values(), default=0) < toughness


# 510.1: the card changes how its controller assigns its combat damage. Butcher Orgg: divided as they choose among the defending player and/or any number
# of creatures that player controls. Wizards' ruling (2004-10-04): usable even if unblocked; blocked with every blocker removed before damage it deals none (510.1c). Cunning Giant: all to one creature the defending player controls, if unblocked.
DIVIDE, GIANT = "divide_damage110f", "giant_damage110f"
_DIVIDE_TEXT = "You may assign this creature's combat damage divided as you choose among defending player and/or any number of creatures they control."
_GIANT_TEXT = "If this creature is unblocked, you may have it assign its combat damage to a creature defending player controls."


def _mode(plan: Any, ch: Any) -> str | None:
    from app.rules import scripts

    names = scripts.statics(ch)
    return DIVIDE if DIVIDE in names else GIANT if GIANT in names else None


def _defenders(plan: Any, att: Any, mode: str) -> list[Any]:
    """The defending player (Orgg only) and their creatures, as options."""
    from app.game.rules_state import DecisionOption
    from app.rules import combat

    pid = combat.defender_of(plan.state, att.attacking)
    if pid is None or pid not in plan.state.players:
        return []
    mine = [DecisionOption(id=pid, label=plan.state.players[pid].name)] if mode == DIVIDE else []
    return mine + [DecisionOption(id=c.id, label=c.name or "Creature", card_id=c.id) for c in plan.state.cards.values()
                   if c.controller == pid and c.zone.endswith(":battlefield") and plan.ch(c).is_creature]


def ask_divide(plan: Any, att: Any, rnd: str, then: str, deals: bool, power: int | None) -> bool:
    """Ask (once per combat damage round) whether to use the card's assignment and how; True: a decision is open. Called from combat.ask_split."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    r = plan.rules
    mode = _mode(plan, plan.ch(att)) if att.is_attacking and att.zone.endswith(":battlefield") else None
    if mode is None or not deals or not power or power <= 0 or att.attacking is None or att.id in r.block_split:
        return False
    if mode == GIANT and att.id in r.blocked:
        return False
    if att.id in r.blocked and not any(c.blocks(att.id) and c.zone.endswith(":battlefield") for c in plan.state.cards.values()):
        return False  # blocked, no blocker left: 510.1c, it assigns no combat damage (and so can't use the ability)
    options = _defenders(plan, att, mode)
    if not options:
        return False
    if att.id not in r.assign_unblocked:
        decide(plan, player=att.controller, kind="confirm", prompt=f"Assign {att.name}'s combat damage with its ability?",
               options=[DecisionOption(id="yes", label="Choose where it goes"), DecisionOption(id="no", label="Assign it normally")],
               resume={"step": "assign_unblocked", "round": rnd, "then": then, "creature": att.id})
        return True
    if not r.assign_unblocked[att.id]:
        return False
    resume = {"round": rnd, "then": then, "creature": att.id, "total": power, "least": 0}
    if mode == DIVIDE:
        decide(plan, player=att.controller, kind="divide", prompt=f"Divide {att.name}'s {power} combat damage among the defending player and their creatures",
               options=options, min_choices=len(options), max_choices=len(options), display={"kind": "divide", "total": power, "what": "damage", "least": 0},
               resume={**resume, "step": "block_split"})
    else:
        decide(plan, player=att.controller, kind="choose_one", prompt=f"Choose the creature {att.name} assigns its {power} combat damage to", options=options,
               resume={**resume, "step": "giant110f"})
    return True


def resume_giant(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import engine

    plan.rules.block_split[d.resume["creature"]] = {chosen[0]: int(d.resume["total"])}
    engine.combat_damage(plan, d.resume["round"], d.resume["then"])
    if plan.rules.decision is None:
        engine._after_resolution(plan)


def divided_shares(plan: Any, att: Any, ach: Any) -> dict[str, int] | None:
    """The shares its controller chose (combat.compute_combat_damage); None: assign as usual (declined, or not asked)."""
    r = plan.rules
    if _mode(plan, ach) is None or not r.assign_unblocked.get(att.id):
        return None
    return r.block_split.get(att.id) or None


COPY_ENTRY = "copy_entry110f"
_COPY_ENTRY_TEXT = "Creatures you control enter as a copy of this creature."


_STICKER_BACK = "Whenever you put {k} sticker on a creature, you may return this card from your graveyard to your hand."


_FIRES = "{2}{R}: Exile the top card of your library. You may play that card this turn. When you play a card this way, ~ deals 2 damage to each player."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    """Essence of the Wild: the static is read at entry (copying.entering -> :func:`copy_on_entry`), it has no effect of its own."""
    from dataclasses import replace

    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == "triggered" and text == "When ~ enters and at the beginning of your upkeep, choose left or right.":
        native = scripts.define(replace(ability, text="When ~ enters and at the beginning of your upkeep, draw a card."), ch)
        if native is not None:  # Mystic Barrier: both triggers, the same choice
            return {**native, "effects": [{"do": "choose_value", "who": "you", "what": "direction", "as": "direction110f"}, {"do": "barrier_direction110f"}]}
    if ability.kind == "activated" and text == _FIRES:  # 603.7c-like reflexive trigger of the permission used (permission_use_triggers43 "native"): playing the exiled card, land or spell
        native = scripts.define(replace(ability, text=_FIRES.replace(" When you play a card this way, ~ deals 2 damage to each player.", "")), ch)
        if native is not None and (grant := native["effects"][-1]).get("do") == "grant_play":
            dmg = scripts.parse_effects("~ deals 2 damage to each player.")
            assert dmg is not None
            grant["use_trigger"] = {"kind": "native", "index": ability.index, "definition": {"effects": dmg[0]}}
            return native
    if ability.kind == "static" and text == "Each player may attack only the nearest opponent in the last chosen direction and planeswalkers controlled by that opponent.":
        return {"kind": "static", "static": "barrier_direction110f", "effects": []}  # (the effect is added by the choice)
    # Unlawful Entry, A Good Day to Pie: a graveyard trigger (603.4 intervening "if", gy_watch) on the sticker event (events.py)
    for k in ("an art", "a name"):
        if ability.kind == "triggered" and ability.text.strip() == _STICKER_BACK.format(k=k):
            return scripts.define(replace(ability, text=_STICKER_BACK.format(k=k).replace("sticker on a creature,", "sticker on a creature, if this card is in your graveyard,")), ch)
    if ability.kind == "triggered" and ability.text.strip() == _THUNDERBLADE:  # 603.4 intervening "if" (graveyard trigger), then the payment, then a free cast of itself (118.9, 601.2)
        native = scripts.define(replace(ability, text=_THUNDERBLADE.replace("you may cast it without paying its mana cost", "draw a card")), ch)
        if native is not None and native["effects"][-1].get("do") == "draw":
            cast = {"do": "free_cast", "zone": "that", "who": "self_gy", "filter": None, "optional": True, "mv": None, "n": 1}
            return {**native, "effects": [*native["effects"][:-1], cast]}
    if ability.kind == "static" and (t := scripts.self_text(ability.text, ch.name).replace("~", "this creature")) in (_DIVIDE_TEXT, _GIANT_TEXT):
        return {"kind": "static", "static": DIVIDE if t == _DIVIDE_TEXT else GIANT, "effects": []}
    if ability.kind == "static" and ability.text == _FLAME_TEXT:
        return {"kind": "static", "static": FLAME, "effects": []}
    if ability.kind == "static" and scripts.self_text(ability.text, ch.name).replace("~", "This creature") == _SPLIT_TEXT:
        return {"kind": "static", "static": SPLIT_DAMAGE, "effects": []}
    if ability.kind == "static" and scripts.self_text(ability.text, ch.name).replace("~", "this creature") == _COPY_ENTRY_TEXT:
        return {"kind": "static", "static": COPY_ENTRY, "effects": []}
    return None


def copy_on_entry(plan: Any, card: Any, controller: str) -> None:
    """614.1c, 707.9: a creature entering under the controller of a permanent with the static enters as a copy of that permanent (its
    copiable values, 707.2), no choice. Several such permanents copy to the same values, so the first is used (ponytail: a card with a
    "may enter as a copy" replacement of its own, or a different copy-entry static, is not ordered against it, 616.1)."""
    from app.game.rules_state import CopyEntrySource
    from app.game.state import zone_key
    from app.rules import copying, permissions

    probe = card.model_copy(update={"zone": zone_key(controller, "battlefield"), "controller": controller})
    if copying.entering_as_copy(plan, card) or not plan.ch(probe).is_creature:
        return
    for source, _, _ in permissions._table_statics(plan.state, plan.info, {COPY_ENTRY}):
        if source.controller == controller and source.id != card.id and plan.ch(source).is_creature:
            copying.add_copy_effect(plan, [plan.oid(card)], copying.recipe_of(plan, source), controller, source=copying.ENTERING + card.id,
                                    entry_source=CopyEntrySource(card=source.id, object_id=plan.oid(source), controller=source.controller))
            return


# 601.2b: "As an additional cost to cast this spell, choose a number between 0 and 5." is announced with the modes and before the targets (601.2c); the
# number only picks the damage split, so it is read as "Choose one" of six modes (Liquid Fire). Exact two-line match only.
_LIQUID = ("As an additional cost to cast this spell, choose a number between 0 and 5.",
           "Liquid Fire deals X damage to target creature and 5 minus X damage to that creature's controller, where X is the chosen number.")


# 700.2e: "An opponent chooses one —" (Fatal Lore, Misfortune): the opponent picks the mode when the controller normally would (601.2b); with several
# opponents the controller decides which one. That opponent is "that player" of the modes: recorded as the spell's chosen player (chosen.chosen_players,
# keyed by the spell's object, so "the chosen player" and "creatures the chosen player controls" read it; copies keep it, 707.10).
_OPP = "An opponent chooses one \u2014"
_OPP_MODES = {
    "\u2022 You draw three cards.": "\u2022 You draw three cards.",
    "\u2022 You destroy up to two target creatures that player controls. They can't be regenerated. That player draws up to three cards.":
        "\u2022 Destroy up to two target creatures the chosen player controls. They can't be regenerated. The chosen player draws up to three cards.",
    "\u2022 You put a +1/+1 counter on each creature you control and gain 4 life.": "\u2022 Put a +1/+1 counter on each creature you control and you gain 4 life.",
    "\u2022 You put a -1/-1 counter on each creature that player controls and Misfortune deals 4 damage to that player.":
        "\u2022 Put a -1/-1 counter on each creature the chosen player controls. Misfortune deals 4 damage to the chosen player.",
}


def _lore() -> Parsed | None:
    from app.rules import scripts

    got = scripts.parse_effects("Destroy up to two target creatures the chosen player controls. They can't be regenerated.")
    return None if got is None else ([*got[0], {"do": "draw_up_to110f", "who": "chosen_player", "n": 3}], got[1], got[2])


def draw_up_to(plan: Any, ctx: Any, e: Any) -> bool:
    """"[Player] draws up to N cards": that player chooses how many, 0 to N (Fatal Lore)."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    pid = next(iter(effects._players(plan, ctx, e["who"])), None)
    if pid is None:
        return True
    decide(plan, player=pid, kind="choose_one", prompt=f"{ctx.get('name', '')}: draw how many cards (up to {e['n']})?",
           options=[DecisionOption(id=str(k), label=str(k)) for k in range(e["n"], -1, -1)], resume={"step": "draw_up_to110f", "ctx": ctx, "pid": pid})
    return False


def resume_draw_up_to(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx, pid = d.resume["ctx"], d.resume["pid"]
    n = int(chosen[0]) if chosen else 0
    if n and not effects.PRIMITIVES["draw"](plan, ctx, {"do": "draw", "who": f"player:{pid}", "n": n}):
        return
    effects.continue_effects(plan, ctx)


def ask_chooser(plan: Any, a: Any) -> bool:
    """True while the caster is asked which opponent chooses (only with several). Sets ``a.chooser110f`` and records it as the spell's chosen player (so the
    modes' targets read it, 601.2c). Modes in the action only count if that opponent chose them (``modes110f``): the caster can't pick for them."""
    from app.game.rules_state import DecisionOption
    from app.rules import casting, effects
    from app.rules.plan import decide

    opps = effects._players(plan, {"controller": plan.actor}, "each_opponent")
    if not opps:
        raise ActionError("No opponent can choose the mode")
    if a.chooser110f not in opps:
        a.chooser110f = opps[0] if len(opps) == 1 else None
    if not a.modes:
        plan.rules.modes110f.pop(a.card_id, None)
    elif plan.rules.modes110f.get(a.card_id) != a.modes:
        a.modes = []
    if a.chooser110f is None:
        decide(plan, player=plan.actor, kind="choose_one", prompt="Choose the opponent who chooses the mode",
               options=[DecisionOption(id=o, label=plan.name(o)) for o in opps], resume=casting._announcing(plan, "chooser110f", a))
        return True
    plan.rules.chosen_players[plan.oid(a.card_id)] = a.chooser110f
    return False


def resume_chooser(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.actions import parse_action
    from app.rules.engine import INTENTS

    intent: Any = parse_action(d.resume["intent"])
    intent.chooser110f = chosen[0]
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)


def resume_modes(plan: Any, d: Any, chosen: list[str]) -> None:
    """The opponent's mode: the cast goes on as its caster (plan.actor), who gets priority back."""
    from app.game.actions import parse_action
    from app.rules.engine import INTENTS

    intent: Any = parse_action(d.resume["intent"])
    intent.modes = [int(c.split(":")[0]) for c in chosen]
    plan.rules.modes110f[intent.card_id] = list(intent.modes)
    chooser, plan.actor = plan.actor, d.resume["caster"]
    try:
        plan.rules.priority = plan.actor
        plan.rules.passed = []
        INTENTS[intent.type](plan, intent)
    finally:
        plan.actor = chooser


def stack_chooser(plan: Any, a: Any, card: Any) -> None:
    """The spell is on the stack as a new object (400.7): its chosen player goes with it."""
    plan.rules.modes110f.pop(card.id, None)
    if getattr(a, "chooser110f", None) is not None:
        plan.rules.chosen_players[plan.oid(card)] = a.chooser110f


def modal_lines(lines: list[Any]) -> list[Any]:
    from dataclasses import replace

    if lines and lines[0].text == _OPP and all(x.text in _OPP_MODES for x in lines[1:]):
        return [lines[0], *(replace(x, text=_OPP_MODES[x.text]) for x in lines[1:])]
    if tuple(x.text for x in lines) != _LIQUID:
        return lines
    return [replace(lines[0], text="Choose one \u2014"),
            *(replace(lines[1], text=f"\u2022 Liquid Fire deals {n} damage to target creature and {5 - n} damage to that creature's controller.") for n in range(6))]


# Ghostly Flame: "Black and/or red permanents and spells are colorless sources of damage." Ruling (Scryfall, wotc 2004): a source with at least one of those
# colors deals damage as a colorless source (other colors forgotten); it keeps its colors otherwise, so it still can't target "protection from red" (115.7)
# and triggers still see its color. Read where damage looks at its source (protection 702.16e, damage-source filters 609.7c).
FLAME = "colorless_damage110f"
_FLAME_TEXT = "Black and/or red permanents and spells are colorless sources of damage."


def damage_colors(plan: Any, ch: Any) -> Any:
    """``ch`` as the source of damage: colorless if Ghostly Flame is on the battlefield and it is black and/or red."""
    from dataclasses import replace

    from app.rules import scripts

    if ch is None or not ch.colors & {"B", "R"} or not any(
            FLAME in scripts.statics(plan.ch(c)) for c in plan.state.cards.values() if c.zone.endswith(":battlefield")):
        return ch
    return replace(ch, colors=frozenset())


PRIMITIVES["draw_up_to110f"] = draw_up_to
PRIMITIVES["edict_match110f"] = edict_match
RESUME.update({"draw_up_to110f": resume_draw_up_to, "chooser110f": resume_chooser, "cast_modes_opp110f": resume_modes})
