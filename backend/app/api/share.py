"""-- invite over the internet -- the host's share tools: share a LAN table through the Cloudflare quick tunnel (an invite code, a
password, the link), check on it, stop sharing it. The host's cookie only, so never through the tunnel (these routes are not in
app/netguard.py TUNNEL_ROUTES: a 404 there)."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import GAME_NOT_FOUND, get_services, require_host
from app.multiplayer.hub import Room
from app.services import STOPPED_SHARING, Services
from app.tunnel.binary import TunnelUnavailable
from app.tunnel.manager import TURNED_OFF

router = APIRouter(tags=["share"], dependencies=[Depends(require_host)])
ServicesDep = Annotated[Services, Depends(get_services)]

NO_LAUNCHER = "Start Fyodor from its launcher to share over the internet."
NO_NETWORK = "Internet features are turned off on this computer (FYODOR_ALLOW_NETWORK=0)."  # (app/tunnel/binary.py's words)


class ShareStatus(BaseModel):
    shared: bool
    state: Literal["stopped", "starting", "running", "failed"]
    reason: str | None
    link: str | None  # only while this table is shared and the tunnel runs
    has_password: bool
    available: bool  # internet features on, and started from the launcher (a tunnel port)


class ShareIn(BaseModel):
    password: str | None = Field(None, min_length=8, max_length=100)  # (needed unless the table has one; never replaces one)


def _unavailable(services: Services) -> str | None:
    if not services.settings.allow_network:
        return NO_NETWORK
    if services.tunnel.port is None:
        return NO_LAUNCHER
    return None


def _status(services: Services, room: Room) -> ShareStatus:
    tunnel = services.tunnel
    hostname = tunnel.hostname
    link = (f"https://{hostname}/#/play?code={room.invite_code}&join=1"
            if room.shared and room.invite_code and tunnel.state == "running" and hostname else None)
    return ShareStatus(shared=room.shared, state=tunnel.state, reason=tunnel.reason, link=link,
                       has_password=room.password_state()[1] is not None, available=_unavailable(services) is None)


def _lan_room(services: Services, game_id: str) -> Room:
    room = services.hub.get(game_id)
    if room is None:
        raise HTTPException(404, GAME_NOT_FOUND)
    if room.mode != "lan" or room.practice is not None:
        raise HTTPException(409, "Only a LAN table can be shared")
    return room


def _check_password(room: Room, password: str | None) -> None:
    has_password = room.password_state()[1] is not None
    if password is None and not has_password:
        raise HTTPException(422, "A table shared over the internet needs a password.")
    if password is not None and has_password:
        raise HTTPException(409, "This table already has a password.")


@router.get("/games/{game_id}/share")
def share_status(game_id: str, services: ServicesDep) -> ShareStatus:
    return _status(services, _lan_room(services, game_id))


@router.post("/games/{game_id}/share")
async def share_table(game_id: str, body: ShareIn, services: ServicesDep) -> ShareStatus:
    room = _lan_room(services, game_id)
    if (why := _unavailable(services)) is not None:
        raise HTTPException(409, why)
    _check_password(room, body.password)
    try:
        await services.tunnel.start()  # (outside every lock: a first start downloads cloudflared)
    except TunnelUnavailable as exc:
        raise HTTPException(502, str(exc)) from exc  # (nothing about the table was changed)
    # the password, the invite code and the share together, once the link is up; under share_lock, so a DELETE's stop-when-unused
    # can't run between the check that the tunnel runs and the share
    async with services.share_lock:
        try:
            if services.hub.get(game_id) is not room:  # closed while the tunnel started
                raise HTTPException(404, GAME_NOT_FOUND)
            async with room.lock:
                if services.tunnel.state != "running":  # stopped in between: never shared with no link
                    raise HTTPException(502, services.tunnel.reason or TURNED_OFF)
                _check_password(room, body.password)  # (again: another request may have set one meanwhile)
                if body.password is not None:  # (PBKDF2, ~0.2 s: on the join hashing pool, not the loop)
                    await asyncio.get_running_loop().run_in_executor(services.hash_pool, services.hub.set_password, room, body.password)
                services.hub.new_invite_code(room)
                room.shared = True
                services.hub.persist(room)
        except HTTPException:
            await services.stop_tunnel_if_unused()  # (the tunnel started for nothing)
            raise
    await services.hub.broadcast(room)
    return _status(services, room)


@router.delete("/games/{game_id}/share")
async def stop_sharing(game_id: str, services: ServicesDep) -> ShareStatus:
    room = _lan_room(services, game_id)
    await services.stop_sharing(room, STOPPED_SHARING)
    return _status(services, room)
