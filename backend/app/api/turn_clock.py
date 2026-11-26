"""-- turn clock (stage 3) -- the host's controls at a started LAN table: change the clock's settings (turn it on or off), add time to a
player's clock, or give a player who dropped more time to reconnect. Host only, never through the tunnel (it is not an allowed route
there). Nothing is recorded in history: each change is one notice in the log."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import get_services, room_host
from app.api.games import authorize
from app.game.turn_clock import ClockSettings, TurnClock
from app.multiplayer import turn_clock_driver as driver
from app.services import Services

router = APIRouter(tags=["turn clock"])
ServicesDep = Annotated[Services, Depends(get_services)]


class ClockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["settings", "add_time", "grace"]
    settings: ClockSettings | None = None
    player: str | None = Field(default=None, pattern=r"^p\d{1,2}$")
    seconds: int | None = Field(default=None, ge=1, le=3600)


def _mss(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


@router.post("/games/{game_id}/clock")
async def change_clock(
    game_id: str, body: ClockIn, request: Request, services: ServicesDep, x_seat_token: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    room = services.hub.get(game_id)
    if room is None:
        raise HTTPException(404, "Game not found (it may have been closed; load it from Saves)")
    if room.mode != "lan" or room.practice is not None:
        raise HTTPException(409, "The turn clock is for LAN tables")
    if not room_host(room, request, x_seat_token):
        raise HTTPException(403, "Only the host can change the turn clock")
    if not room.started or room.game is None:
        raise HTTPException(409, "The game has not started")
    if room.game.state.format != "commander":
        raise HTTPException(409, "A Sandbox table has no turn clock")
    if body.op == "settings":
        if body.settings is None:
            raise HTTPException(422, "settings is required")
    else:
        if body.player is None or body.seconds is None:
            raise HTTPException(422, "player and seconds are required")
        seat = room.seats.get(body.player)
        if seat is None or seat.bot or body.player not in room.session.state.players:
            raise HTTPException(422, "No such player")
    viewer, _ = authorize(room, conn=request, token=x_seat_token, viewer=None, as_player=None)
    async with room.lock:
        session = room.session
        if body.op == "settings":
            assert body.settings is not None
            old = session.clock
            was_on = old is not None and old.settings.on
            if old is None:
                session.clock = TurnClock(settings=body.settings)
            else:
                old.settings = body.settings  # (banks untouched)
            now_on = body.settings.on
            session.notice("The host turned the turn clock on." if now_on and not was_on
                           else "The host turned the turn clock off." if was_on and not now_on
                           else "The host changed the turn clock settings.")
        else:
            clock = session.clock
            if clock is None:
                clock = session.clock = TurnClock(settings=ClockSettings.model_validate({}))
            assert body.player is not None and body.seconds is not None
            name = room.seat_name(body.player)
            if body.op == "add_time":
                clock.add_time(body.player, body.seconds, driver.now())
                session.notice(f"The host added {_mss(body.seconds)} to {name}'s clock.")
            else:
                clock.extend_grace(body.player, body.seconds)
                session.notice(f"The host gave {name} {_mss(body.seconds)} more to reconnect.")
        driver.poke(services.hub, room)
    await services.hub.broadcast(room)
    return {"view": services.hub.view(room, viewer)}
