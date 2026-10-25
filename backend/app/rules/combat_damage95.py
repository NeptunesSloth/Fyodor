"""Exact positive combat receipts and safe negative history for original objects."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.rules.plan import Plan

HOPE = "Sacrifice ~: Until your next turn, target player who was dealt combat damage by ~ this turn can't cast noncreature spells."
BECKETT = "At the beginning of your end step, gain control of target nonland permanent controlled by a player who was dealt combat damage by three or more Pirates this turn."
AXE = "At the beginning of your end step, if equipped creature didn't deal combat damage to a creature this turn, sacrifice it."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, selectors

    text = scripts.self_text(ability.text, ch.name)
    if text == BECKETT:
        native = scripts.define(
            replace(
                ability, text="At the beginning of your end step, gain control of target nonland permanent."
            ),
            ch,
        )
        if native:
            target = selectors.parse("nonland permanent")
            assert target is not None
            return {
                **native,
                "target": {"what": replace(target, extras=(*target.extras, "combat_pirate_player95")).key()},
            }
    if text == AXE:
        native = scripts.define(replace(ability, text="At the beginning of your end step, draw a card."), ch)
        if native:
            return {**native, "if": {"axe_combat95": True}, "effects": [{"do": "axe_sacrifice95"}]}
    return None


def pirate_player(plan: Plan, player: str) -> bool:
    from app.rules.history import log_for

    originals = {
        f.object_id
        for f in log_for(plan).facts
        if f.kind == "damage"
        and f.player == player
        and f.amount > 0
        and f.combat
        and f.object_id is not None
        and "Pirate" in (f.source_subtypes or [])
    }
    return len(originals) >= 3


def host_result(plan: Plan, ctx: Any) -> bool | None:
    """True means the current/last-known host did not deal qualifying combat damage."""
    from app.rules import effects
    from app.rules.history import log_for

    hosts = effects._cards(plan, ctx, "host")
    if len(hosts) != 1 or not plan.in_game(plan.state.cards[hosts[0]]):
        return False
    oid = plan.oid(hosts[0])
    log = log_for(plan)
    if any(
        f.kind == "damaged"
        and f.source == oid
        and f.amount > 0
        and f.combat
        and "Creature" in (f.types or [])
        for f in log.facts
    ):
        return False
    return True if log.combat_damage95_known is True else None


def holds(plan: Plan, ctx: Any) -> bool:
    # Unknown history must reach the explicit legacy continuation rather than
    # silently inventing a negative receipt or omitting a potentially due trigger.
    return host_result(plan, ctx) is not False


def sacrifice(plan: Plan, ctx: Any, effect: Any) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    result = host_result(plan, ctx)
    if result is None:
        decide(
            plan,
            player=ctx["controller"],
            kind="manual_resolution",
            prompt="This older save does not record complete combat-damage history. If the equipped creature didn't deal combat damage to a creature this turn, sacrifice it by hand, then press Done.",
            options=[DecisionOption(id="done", label="Done")],
            resume={"step": "combat_damage95_legacy", "ctx": ctx},
        )
        return False
    if result:
        ctx["effects"][ctx["next"] : ctx["next"]] = [{"do": "sacrifice", "who": "host"}]
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.rules.effects import continue_effects

    continue_effects(plan, d.resume["ctx"])


PRIMITIVES = {"axe_sacrifice95": sacrifice}
RESUME = {"combat_damage95_legacy": resume}
