"""CR 118.9a, 601.2b, 702.34: announce one of multiple flashback costs."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.actions import CastSpell
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import Characteristics
    from app.rules.costs import AbilityCost
    from app.rules.plan import Plan


def options(state: GameState, card: CardInstance, ch: Characteristics, info: Any) -> list[tuple[str, AbilityCost | None]]:
    from app.rules import casting, graveyard_grants

    found = [parts for ab in ch.abilities if ab.kind == 'keywords' and 'flashback' in ab.keywords
             if (parts := casting.flashback_parts(ab.text)) is not None]
    found.extend((cost, None) for cost in graveyard_grants.flashback_costs(state, card, ch, info))
    unique: list[tuple[str, AbilityCost | None]] = []
    for option in found:
        if option not in unique:
            unique.append(option)
    return unique


def selected(ways: list[tuple[str, AbilityCost | None]], index: int | None) -> tuple[str, AbilityCost | None]:
    from app.game.errors import ActionError

    index = 0 if index is None else index
    if index >= len(ways):
        raise ActionError('That flashback cost is no longer available')
    return ways[index]


def extra(state: GameState, card: CardInstance, ch: Characteristics, info: Any, index: int | None) -> AbilityCost | None:
    ways = options(state, card, ch, info)
    return selected(ways, index)[1] if ways else None


def announce(plan: Plan, a: CastSpell, card: CardInstance, ch: Characteristics) -> bool:
    from app.game.rules_state import DecisionOption
    from app.rules import casting
    from app.rules.plan import decide

    ways = options(plan.state, card, ch, plan.info)
    if a.flashback_choice is not None:
        selected(ways, a.flashback_choice)
        return False
    if len(ways) < 2:
        return False
    labels = [f'{cost}' + (f', {", ".join(p.text for p in other.components)}' if other is not None else '') for cost, other in ways]
    decide(plan, player=plan.actor, kind='choose_one', prompt=f'{ch.name}: choose a flashback cost',
           options=[DecisionOption(id=str(i), label=label[:190]) for i, label in enumerate(labels)],
           resume=casting._announcing(plan, 'flashback_choice', a), source=card)
    return True


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    from app.game import actions as A
    from app.rules import casting
    from app.rules.engine import INTENTS

    if casting.cancelled(plan, d, chosen):
        return
    intent = A.parse_action(d.resume['intent'])
    assert isinstance(intent, A.CastSpell)
    intent.flashback_choice = int(chosen[0])
    plan.rules.priority = d.player
    plan.rules.passed = []
    INTENTS[intent.type](plan, intent)
