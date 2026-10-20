"""Persistent named combat damage and native player-loss look-back events."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

NAME = "Gollum, Obsessed Stalker"


def begin(plan: Plan) -> None:
    if plan.state.turn.number == 1:
        plan.rules.named_combat_history_known = True


def damage_names(plan: Plan, event: dict[str, Any]) -> list[str]:
    from app.rules.card_names import normalize_name

    source = event.get("src") or {}
    if "Creature" not in source.get("types", ()):
        return []
    return list(dict.fromkeys(normalize_name(n) for n in source.get("names", ()) if n))


def _loss_condition(condition: dict[str, Any]) -> bool:
    return condition.get('event') == 'lose_game' or (
        condition.get('event') == 'either' and any(_loss_condition(part) for part in condition.get('conds', [])))


def loss_events(plan: Plan, players: list[str], *, prior_leave: bool = False) -> None:
    """603.10f normal loss looks back;104.3a concession leaves before the loss event."""
    from app.game.rules_state import emit, snapshot
    from app.rules import characteristics, granted, triggers

    players = list(dict.fromkeys(p for p in players if p in plan.live() or (prior_leave and p in plan.rules.conceded)))
    if not players:
        return
    cohort = []
    for card in list(plan.state.cards.values()):
        if not card.zone.endswith(":battlefield") or not plan.in_game(card) or plan.manual(card):
            continue
        ch = plan.ch(card)
        if not any(
            _loss_condition(d.get("cond", {})) for _, d in triggers.abilities(plan, ch, "event")
        ):
            continue
        snap = snapshot(plan.state, card.id)
        snap.abilities, snap.keywords, snap.traits = granted.last_existed(
            characteristics.of(card, plan.info), ch
        )
        snap.name = ch.name
        snap.power, snap.toughness = ch.pt or (None, None)
        cohort.append(snap)
    for player in players:
        start=plan.state.turn.starting_life
        emit(plan.state, "player_lost_game", player=player, loss_watchers=cohort,
             turn_start_life=start.get(player) if start is not None else None)


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if (
        text
        == "At the beginning of your end step, each opponent dealt combat damage this game by a creature named Gollum, Obsessed Stalker loses life equal to the amount of life you gained this turn."
    ):
        base = scripts.define(
            replace(ability, text="At the beginning of your end step, you gain 1 life."), ch
        )
        return {**base, "effects": [{"do": "life_game_history", "mode": "gollum"}]} if base else None
    if (
        text
        == "At the beginning of your upkeep, each player loses 1 life. Put a +1/+1 counter on ~ for each 1 life lost this way."
    ):
        base = scripts.define(replace(ability, text="At the beginning of your upkeep, you gain 1 life."), ch)
        return (
            {
                **base,
                "effects": [
                    {"do": "lose_life", "who": "each_player", "n": 1, "bind": "tyrant_loss"},
                    {
                        "do": "add_counters",
                        "who": "self",
                        "kind": "+1/+1",
                        "n": {"ref_amount": "tyrant_loss"},
                    },
                ],
            }
            if base
            else None
        )
    if text == "Whenever a player loses the game, put five +1/+1 counters on ~.":
        return {
            "kind": "triggered",
            "trigger": "event",
            "cond": {"event": "lose_game", "subject": "player", "player": "any"},
            "effects": [{"do": "add_counters", "who": "self", "kind": "+1/+1", "n": 5}],
        }
    return None


def run(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import context, history
    from app.rules.card_names import normalize_name

    if not plan.rules.named_combat_history_known:
        if not plan.rules.named_combat_history_notice:
            plan.note(
                "Earlier named combat damage is unavailable in this save. Resolve this life-loss ability by hand."
            )
            plan.rules.named_combat_history_notice = True
        return True
    victims = [
        p
        for p in plan.live()
        if p != ctx["controller"] and p in plan.rules.named_combat_damage.get(normalize_name(NAME), ())
    ]
    context.bind_players(ctx, "gollum_victims", victims)
    amount = history.log_for(plan).gained.get(ctx["controller"], 0)
    ctx["effects"][ctx["next"] : ctx["next"]] = [
        {"do": "lose_life", "who": "ref:gollum_victims", "n": amount}
    ]
    return True


PRIMITIVES = {"life_game_history": run}
