"""-- defending player (wave 6D) -- "Whenever this creature attacks, defending player discards a card."

508.5: an ability of an attacking creature that refers to "defending player" means the player that creature is
attacking, the controller of the planeswalker it's attacking, or the protector of the battle it's attacking (310.9d);
if it's no longer attacking, the player it was attacking before it was removed from combat. 508.5a: in multiplayer
that is one specific player, determined for each attacking creature. So the trigger event of an attacking creature
(its "attacks", "attacks and isn't blocked", "becomes blocked" event) captures that player as it triggers
(TriggerEvent.defended: whom it attacks can't change while it stays attacking, and a creature removed from combat
afterwards keeps the player it was attacking, 508.5), and ``who: "defending_player"`` reads it at resolution.

Read only in the triggered abilities of the attacking creature — this one ("Whenever ~ attacks"), the one a
condition names ("Whenever a creature you control attacks", "Whenever equipped creature attacks"), one creature
at a time. "One or more creatures attack" (several defending players, 508.5a: the controller would choose),
"attacks or blocks", any other trigger and any static, activated or spell wording stay manual.
"""

from __future__ import annotations

import json
from typing import Any

WHO = "defending_player"
_EVENTS = ("attack", "unblocked", "blocked")
_SUBJECTS = ("self", "sel", "host", "self_or_host", "self_or")


def allowed(d: dict[str, Any]) -> bool:
    """Whether a definition that names the defending player is an attacking creature's trigger (above)."""
    if WHO not in json.dumps(d, default=str):
        return True
    if d.get("kind") != "triggered":
        return False
    if d.get("trigger") == "attacks_self":
        return True
    cond = d.get("cond") or {}
    return d.get("trigger") == "event" and cond.get("event") in _EVENTS and cond.get("subject") in _SUBJECTS \
        and not cond.get("aggregate")


def defended(plan: Any, card: Any) -> str | None:
    """The defending player of an attacking creature (508.5), or None when it isn't attacking."""
    from app.rules import battles

    t = getattr(card, "attacking", None)
    if t is None:
        return None
    if t.kind == "player":
        return str(t.id)
    attacked = plan.state.cards.get(t.id)
    if attacked is None:
        return None
    if battles.is_battle(plan.ch(attacked)):
        return battles.protector(plan.state, attacked)  # 310.9d
    return attacked.controller


def players(plan: Any, ctx: dict[str, Any]) -> list[str]:
    """``who: "defending_player"`` at resolution: the player the trigger event captured, while they're in the game."""
    pid = (ctx.get("event") or {}).get("defended")
    return [pid] if pid and pid in plan.live() else []
