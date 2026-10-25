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


BUILDERS: dict[str, Callable[[], Parsed]] = {
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
    "put the cards exiled with it into their owner's hand.": "return all cards exiled with it to their owners' hands.",  # Toluz (607.2a)
    # 601.2h, 107.3: "a number of tokens equal to the amount of mana spent" = X tokens, X the amount of mana spent to cast it.
    "create a number of 1/1 black Fungus Zombie creature tokens named Cordyceps Infected equal to the amount of mana spent to cast this spell.":
        "create X 1/1 black Fungus Zombie creature tokens named Cordyceps Infected, where X is the amount of mana spent to cast this spell.",
    # 611.2 / 122.1: control change then the counter on the same (still targeted) creature, as two sentences.
    "Gain control of target nonartifact, nonblack creature that attacked you this turn and put a -1/-0 counter on it.":
        "Gain control of target nonartifact, nonblack creature that attacked you this turn, then put a -1/-0 counter on it.",
    "it deals 6 damage to each creature it blocked this combat.": "~ deals 6 damage to each creature blocked by it.",
}
PRIMITIVES: dict[str, Any] = {"same_colors110f": same_colors, "phase_swap110f": phase_swap, "exile_discarded110f": exile_discarded}


def parse(body: str) -> Parsed | None:
    from app.rules import scripts

    build = BUILDERS.get(body.strip())
    if build is not None:
        return build()
    return scripts.parse_effects(REWRITES[body.strip()]) if body.strip() in REWRITES else None
