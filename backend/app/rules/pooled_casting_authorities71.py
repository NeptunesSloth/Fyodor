"""Scoped linked-exile and current-turn graveyard casting authorities."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.characteristics import CardInfo
    from app.rules.plan import Plan


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import permissions, scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    lines = tuple(a.text for a in ch.abilities)
    if (
        text
        == "{T}: Draw a card, then exile a card from your hand face down. You may look at that card for as long as it remains exiled. You may pay {4}{U}{U}. If you do, transform ~."
    ):
        native = scripts.define(replace(ability, text=ability.text.replace(", then exile", ". Exile")), ch)
        return (
            {
                **native,
                "effects": [
                    {**e, "link": True, "blind": True} if e["do"] == "exile_hand_down" else e
                    for e in native["effects"]
                ],
            }
            if native
            else None
        )
    if (
        text
        == "Once during each of your turns, you may play a land or cast a spell from among the cards exiled with ~ without paying its mana cost."
    ):
        native = permissions.define_static("You may play cards exiled with ~.", "static", lines)
        return (
            {
                **native,
                "once": True,
                "free": True,
                "during": "your_turn",
                "linked_face_down": True,
                "once_per_object71": True,
            }
            if native
            else None
        )
    if (
        text
        == "Whenever ~ or another Elf or Faerie you control enters, exile the top two cards of target opponent's library."
    ):
        native = scripts.define(
            replace(ability, text=ability.text.replace("the top two cards", "the top three cards")), ch
        )
        if native is None:
            return None
        effects = []
        for e in native["effects"]:
            if e["do"] == "exile_top":
                effects.extend(
                    [
                        {**e, "n": 2, "link": True, "as": "maralen71"},
                        {"do": "stamp_linked_turn71", "binding": "maralen71"},
                    ]
                )
            else:
                effects.append(e)
        return {**native, "effects": effects}
    if (
        text
        == "Once each turn, you may cast a spell with mana value less than or equal to the number of Elves and Faeries you control from among cards exiled with ~ this turn without paying its mana cost."
    ):
        native = permissions.define_static(
            "You may cast spells from among cards exiled with ~.", "static", lines
        )
        creatures = selectors.Selector(
            zones=("battlefield",), types=("Creature",), subtypes=("Elf", "Faerie"), controller="you"
        ).key()
        return (
            {
                **native,
                "once": True,
                "once_any": True,
                "free": True,
                "once_per_object71": True,
                "linked_current_turn71": True,
                "free68_ceiling": {"count": creatures},
            }
            if native
            else None
        )
    if (
        text
        == "During each of your turns, you may play a land and cast a spell from among cards in graveyards that were put there from libraries this turn."
    ):
        native = permissions.define_static(
            "You may play lands and cast spells from your graveyard.", "static", lines
        )
        return (
            {
                **native,
                "once": True,
                "during": "your_turn",
                "zone_owner": "any",
                "put_there": "library",
                "separate_verb71": True,
            }
            if native
            else None
        )
    return None


def stamp(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, exiled_with

    scope = exiled_with.link_key(ctx)
    if not scope:
        raise ValueError("Linked turn receipt needs its native source object")
    receipt = plan.rules.linked_exile_turns71.setdefault(scope, {})
    for cid in context.objects(plan, ctx, e["binding"]):
        current = plan.state.cards[cid]
        if current.zone.endswith(":exile"):
            receipt[plan.oid(current)] = plan.state.turn.number
    return True


PRIMITIVES = {"stamp_linked_turn71": stamp}


def external_candidates(state: GameState, player: str, info: CardInfo) -> list[str]:
    """Visible external objects with an actual cast/play authority, without exposing hidden faces."""
    from app.game.state import zone_key
    from app.game.visibility import can_see
    from app.rules import characteristics, permissions

    rules = state.rules
    if rules is None:
        return []
    named = {o for objects in rules.exiled_with.values() for o in objects}
    named.update(
        o
        for p in rules.permissions
        if p.player == player
        for o in (p.object_id, rules.object_id(p.card) if p.card else None)
        if o
    )
    candidates = [
        cid
        for pid in state.players
        if pid != player
        for zone in ("graveyard", "exile")
        for cid in state.zones.get(zone_key(pid, zone), [])
        if zone == "graveyard" or rules.object_id(cid) in named or cid in rules.free_casts
    ]
    library = state.zones.get(zone_key(player, "library"), [])
    if library:
        candidates.append(library[0])
    return [
        cid
        for cid in candidates
        if can_see(state, state.cards[cid], player)
        and any(
            permissions.grants(
                state, player, state.cards[cid], characteristics.of(state.cards[cid], info), info, verb=verb
            )
            for verb in ("cast", "play")
        )
    ]
