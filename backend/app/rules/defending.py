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


def per_player_attack(cond: dict[str, Any]) -> bool:
    """-- trigger other (wave 44B) -- 508.3e: "Whenever one or more creatures you control attack a player" triggers once for each player attacked
    (triggers._fire_generic keeps one per defended player), so "that player" in its effect is that one player, the event's defended player (508.5a).
    ("Whenever you attack a player" is the you_attack event, whose "that player" triggers.bind_that_player already binds to the one attacked.)"""
    return cond.get("defender") == "player" and cond.get("event") == "attack" and cond.get("subject") == "sel" and bool(cond.get("aggregate"))


def allowed(d: dict[str, Any]) -> bool:
    """Whether a definition that names the defending player (or the attacked object) is an attacking creature's trigger (above)."""
    if WHO not in (raw := json.dumps(d, default=str)) and "defended_player" not in raw and '"who": "attacked"' not in raw:
        return True
    if d.get("kind") != "triggered":
        return False
    if d.get("trigger") == "attacks_self":
        return True
    cond = d.get("cond") or {}
    if per_player_attack(cond):
        return d.get("trigger") == "event"
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


def attacked(plan: Any, ctx: dict[str, Any]) -> tuple[list[str], list[str]]:
    """-- attacked object (wave 45A) -- "the player or planeswalker it's attacking" at resolution: (players, planeswalkers). The attacking creature the event is
    about, while it is still on the battlefield: what it attacks now (508.5); removed from combat, nothing (Fathom Fleet Swordjack ruling 2020-11-10). Once it has
    left the battlefield: what it attacked as the ability triggered (608.2h; Raid Bombardment ruling 2018-12-07, Cavalcade of Calamity 2019-01-25). A battle, or a
    planeswalker that has left, is nothing (Raid Bombardment ruling 2023-09-01)."""
    ev = ctx.get("event") or {}
    obj = next(iter(ev.get("objects") or []), None) or {}
    me = plan.state.cards.get(obj.get("card"))
    if me is not None and me.zone.endswith(":battlefield") and plan.oid(me) == obj.get("object_id"):
        t = me.attacking
        if t is None:
            return [], []
        who, pw = ([t.id], None) if t.kind == "player" else ([], plan.state.cards.get(t.id))
    elif ev.get("attacked") is not None:
        who, pw = [], plan.state.cards.get(ev["attacked"]["card"])
        if pw is not None and plan.oid(pw) != ev["attacked"]["object_id"]:
            pw = None
    else:
        who, pw = players(plan, ctx), None
    live = pw is not None and pw.zone.endswith(":battlefield") and "Planeswalker" in plan.ch(pw).types
    return [p for p in who if p in plan.live()], [pw.id] if live and pw is not None else []
