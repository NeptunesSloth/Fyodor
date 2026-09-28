"""Per-viewer sanitized game views.

The server never sends the full state to a client. ``build_view`` produces exactly what one
viewer may know: hidden cards are reduced to opaque placeholders (no printing id, name,
note or face), libraries are sent as a count plus the cards the viewer knows, and log
entries name cards only for viewers who could see them.
"""

from __future__ import annotations

from typing import Any

from app.game.state import (
    ALL,
    PUBLIC_ZONES,
    STACK,
    CardInstance,
    GameState,
    LogEntry,
    LogPart,
    split_zone,
)
from app.game.visibility import OMNISCIENT, SPECTATOR, can_see

VIEW_VERSION = 1


def card_view(state: GameState, c: CardInstance, viewer: str) -> dict[str, Any]:
    _, zone = split_zone(c.zone)
    if can_see(state, c, viewer):
        view: dict[str, Any] = {
            "id": c.id,
            "card_id": c.card_id,
            "name": c.name,
            "owner": c.owner,
            "controller": c.controller,
            "zone": c.zone,
            "face": c.face,
            "face_down": c.face_down,
            "revealed": c.revealed,
            "note": c.note,
            "is_token": c.is_token,
        }
        if c.token:
            view["token"] = c.token.model_dump()
        if c.copy_of:
            view["copy_of"] = c.copy_of.model_dump()
        if c.ability:
            view["ability"] = c.ability.model_dump()
        if c.commander_key:
            view["commander_key"] = c.commander_key
        if c.categories and viewer in (c.owner, OMNISCIENT):
            view["categories"] = list(c.categories)
    else:
        view = {"id": c.id, "hidden": True, "owner": c.owner, "controller": c.controller, "zone": c.zone,
                "face_down": c.face_down}
    if c.protected:
        view["protected"] = True
    if zone in PUBLIC_ZONES:
        # Position, tapped state, counters and combat roles are public even for face-down cards.
        view.update(x=c.x, y=c.y, tapped=c.tapped, flipped=c.flipped)
        if c.rotation:
            view["rotation"] = c.rotation
        if c.locked:
            view["locked"] = True
        if c.attached_to:
            view["attached_to"] = c.attached_to
        if c.group:
            view["group"] = c.group
        if c.quantity != 1:
            view["quantity"] = c.quantity
        if c.counters:
            view["counters"] = dict(c.counters)
        if c.attacking:
            view["attacking"] = c.attacking.model_dump()
        if c.blocking:
            view["blocking"] = c.blocking
    return view


def _render_part(part: LogPart, viewer: str) -> dict[str, Any] | list[dict[str, Any]]:
    if part.group is not None:
        names = []
        hidden = 0
        for p in part.group:
            if _sees(p, viewer):
                names.append({"card": {"name": p.name, "card_id": p.card_id}})
            else:
                hidden += 1
        return {"group": names, "hidden": hidden}
    if part.t is not None:
        return {"t": part.t}
    if _sees(part, viewer):
        return {"card": {"name": part.name, "card_id": part.card_id}}
    return {"group": [], "hidden": 1}


def _sees(part: LogPart, viewer: str) -> bool:
    return viewer == OMNISCIENT or ALL in part.visible_to or viewer in part.visible_to


def render_log(entries: list[LogEntry], viewer: str) -> list[dict[str, Any]]:
    return [
        {
            "seq": e.seq,
            "ts": e.ts,
            "turn": e.turn,
            "phase": e.phase,
            "actor": e.actor,
            "kind": e.kind,
            "parts": [_render_part(p, viewer) for p in e.parts],
        }
        for e in entries
    ]


def build_view(
    state: GameState,
    viewer: str,
    *,
    log_limit: int = 250,
    extra_log: list[LogEntry] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if viewer not in state.players and viewer not in (SPECTATOR, OMNISCIENT):
        raise ValueError(f"unknown viewer {viewer}")
    cards: dict[str, dict[str, Any]] = {}
    zones: dict[str, Any] = {}
    for key, ids in state.zones.items():
        _, zone = split_zone(key)
        if zone == "library":
            searching = state.searches.get(viewer) == key
            known = []
            for index, cid in enumerate(ids):
                c = state.cards[cid]
                if viewer == OMNISCIENT or searching or can_see(state, c, viewer):
                    known.append([index, cid])
                    cards[cid] = card_view(state, c, viewer if not searching else OMNISCIENT)
            zones[key] = {"count": len(ids), "known": known}
        else:
            zones[key] = list(ids)
            searching = state.searches.get(viewer) == key
            for cid in ids:
                cards[cid] = card_view(state, state.cards[cid], OMNISCIENT if searching else viewer)

    commanders: dict[str, list[dict[str, Any]]] = {pid: [] for pid in state.seat_order}
    for c in state.cards.values():
        if c.commander_key:
            commanders[c.owner].append(
                {"key": c.commander_key, "name": c.name, "card_id": c.card_id, "instance_id": c.id if can_see(state, c, viewer) else None,
                 "zone": c.zone, "tax": state.players[c.owner].commander_tax.get(c.commander_key, 0)}
            )

    players = []
    for pid in state.seat_order:
        p = state.players[pid]
        data = p.model_dump(exclude={"token_shortcuts"} if viewer != pid and viewer != OMNISCIENT else set())
        data["commanders"] = sorted(commanders[pid], key=lambda x: x["key"])
        data["hand_count"] = len(state.zones.get(f"{pid}:hand", []))
        data["library_count"] = len(state.zones.get(f"{pid}:library", []))
        players.append(data)

    log = list(state.log)
    if extra_log:
        log = sorted(log + extra_log, key=lambda e: (e.ts, e.seq))
    return {
        "view_version": VIEW_VERSION,
        "game": {
            "id": state.id,
            "name": state.name,
            "format": state.format,
            "seq": state.seq,
            "settings": state.settings.model_dump(),
            **(meta or {}),
        },
        "viewer": viewer,
        "players": players,
        "seat_order": list(state.seat_order),
        "turn": state.turn.model_dump(),
        "table": state.table.model_dump(),
        "searches": dict(state.searches),
        "reminders": [r.model_dump() for r in state.reminders],
        "cards": cards,
        "zones": zones,
        "stack": list(state.zones.get(STACK, [])),
        "log": render_log(log[-log_limit:], viewer),
    }
