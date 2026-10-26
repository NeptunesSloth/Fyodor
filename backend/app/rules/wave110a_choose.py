"""Wave 110A: Celestial Reunion: "you may choose a creature type and behold two creatures of that type" as an additional cost (601.2b: the caster chooses
the type while announcing; the choice is public, 205.3m). The type rides on the intent as ``pick110e`` (the wave 110E cast-time choice) and on the spell's
payment record; the search then puts a revealed card of that type onto the battlefield when the cost was paid (conditional_search_destination)."""

from __future__ import annotations

from typing import Any


def announce(plan: Any, a: Any, card: Any, ch: Any) -> str | None:
    """The chosen creature type, or None while the caster is asked."""
    from app.game.errors import ActionError
    from app.game.rules_state import DecisionOption
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.plan import decide

    if a.pick110e is None:
        decide(plan, player=plan.actor, kind="choose_one", prompt=f"{ch.name}: choose a creature type (then behold two creatures of that type)",
               options=[DecisionOption(id=t, label=t) for t in sorted(CREATURE_TYPES)],
               resume={"step": "pick110e", "intent": a.model_dump(mode="json", exclude={"r", "actor", "ts"})}, source=card)
        return None
    if a.pick110e not in CREATURE_TYPES:
        raise ActionError("Choose a creature type")
    return str(a.pick110e)
