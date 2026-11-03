"""Fyodor tables on the network (app/multiplayer/discovery.py) and bringing my decks to them (app/multiplayer/handoff.py)."""

from __future__ import annotations

import ipaddress
import json
from typing import Annotated, Any
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError

from app.api.deps import get_services, require_local
from app.decks.parser import format_deck_text
from app.multiplayer.discovery import Discovery, computer_name, on_local_network
from app.multiplayer.handoff import MAX_BYTES, MAX_DECKS, TTL, BroughtDeck, HandoffRefused, Library
from app.services import Services
from app.textutil import clean_text

router = APIRouter(tags=["lan"])
ServicesDep = Annotated[Services, Depends(get_services)]


def get_discovery(request: Request) -> Discovery:
    discovery: Discovery = request.app.state.discovery
    return discovery


@router.get("/lan/nearby")
async def nearby(request: Request) -> list[dict[str, Any]]:
    """Other Fyodor servers answering on the network, and their LAN tables. The host computer only: another device can't
    make this computer broadcast. No network: an empty list."""
    require_local(request)
    return await get_discovery(request).nearby()


# --------------------------------------------------------------------------- bringing my decks: the receiving side


class BroughtDeckIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    commanders: list[str] = Field(default_factory=list, max_length=4)
    text: str = Field(min_length=1, max_length=200_000)


class HandoffIn(BaseModel):
    source: str = Field(alias="from", min_length=1, max_length=64)
    decks: list[BroughtDeckIn] = Field(max_length=MAX_DECKS)


def _sender(request: Request) -> str:
    from app.api.games import client_ip

    return client_ip(request)


@router.post("/lan/handoff")
async def receive_handoff(request: Request, services: ServicesDep) -> dict[str, Any]:
    """A player's own Fyodor sends their deck library ahead of their join; it waits here, in memory, for one join."""
    sender = _sender(request)
    if not on_local_network(sender):
        raise HTTPException(403, "Only computers on this network can bring decks")
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BYTES:
        raise HTTPException(413, "That deck library is too large (1 MB at most)")
    raw = bytearray()
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "That deck library is too large (1 MB at most)")
    try:
        body = HandoffIn.model_validate_json(bytes(raw))
    except ValidationError:
        raise HTTPException(422, f"Not a deck library (at most {MAX_DECKS} decks)") from None
    decks = [BroughtDeck(name=clean_text(d.name, 120) or "Deck", commanders=[clean_text(c, 200) for c in d.commanders if c.strip()],
                         text=d.text) for d in body.decks]
    try:
        token = services.handoffs.offer(Library(source=clean_text(body.source, 40) or "another computer", decks=decks), sender)
    except HandoffRefused as exc:
        raise HTTPException(exc.status, str(exc)) from None
    return {"token": token, "expires_in": TTL}


@router.get("/games/{game_id}/lobby/brought")
async def brought_decks(game_id: str, services: ServicesDep, x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """The deck library this seat brought from its own computer: to that seat alone, while the lobby is open."""
    room = services.hub.get(game_id)
    if room is None:
        raise HTTPException(404, "Game not found")
    if not x_seat_token or room.seat_for_token(x_seat_token) not in room.seats:
        raise HTTPException(403, "Only a seated player sees the decks they brought")
    library = services.handoffs.brought(room, x_seat_token)
    if library is None:
        return {"from": None, "decks": []}

    def covers() -> list[str | None]:  # the host has the card database: each deck's first commander, for its art
        out: list[str | None] = []
        for d in library.decks:
            card = services.cards.resolve(d.commanders[0]) if d.commanders and services.cards.available else None
            out.append(card["id"] if card else None)
        return out

    try:
        cover_ids = await run_in_threadpool(covers)
    except Exception:  # noqa: BLE001 - art is a nicety; the list still works without it
        cover_ids = [None] * len(library.decks)
    return {"from": library.source, "decks": [
        {"name": d.name, "commanders": d.commanders, "text": d.text, "cover_id": cover}
        for d, cover in zip(library.decks, cover_ids, strict=True)
    ]}


# --------------------------------------------------------------------------- bringing my decks: the sending side


class SendIn(BaseModel):
    url: str = Field(min_length=8, max_length=200)


def handoff_target(url: str) -> str | None:
    """``http://<address on this network>:<port>`` (a server found under Games on your network), normalized; else None."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "http" or port is None or parts.username or parts.password or parts.path.strip("/") or parts.query:
        return None
    try:
        ip = ipaddress.ip_address(parts.hostname or "")
    except ValueError:
        return None
    if not on_local_network(str(ip)):
        return None
    return f"http://{f'[{ip}]' if ip.version == 6 else ip}:{port}"


def library_payload(services: Services) -> dict[str, Any]:
    """This computer's deck library as the host's lobby reads a pasted list: newest first, within the size caps."""
    decks: list[dict[str, Any]] = []
    size = 200
    for deck in services.decks.list_all():
        if len(decks) >= MAX_DECKS:
            break
        if not deck.entries:
            continue
        item = {"name": deck.name, "commanders": [e.name for e in deck.entries if e.section == "commander"][:4],
                "text": format_deck_text([e.model_dump() for e in deck.entries])}
        cost = len(json.dumps(item).encode()) + 2
        if size + cost > MAX_BYTES or len(item["text"]) > 200_000:
            continue
        size += cost
        decks.append(item)
    return {"from": computer_name(), "decks": decks}


async def post_handoff(target: str, data: bytes) -> str:
    """Send the library to the host's server; returns its one-time token. Straight to the LAN address: no system proxy."""
    async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(5.0)) as client:
        res = await client.post(f"{target}/api/lan/handoff", content=data, headers={"Content-Type": "application/json"})
        res.raise_for_status()
        token = res.json().get("token")
    if not isinstance(token, str) or not 16 <= len(token) <= 64:
        raise ValueError("no token in the reply")
    return token


@router.post("/lan/send-decks")
async def send_decks(body: SendIn, request: Request, services: ServicesDep) -> dict[str, Any]:
    """Before joining a table found on the network: send this computer's deck library to that table's computer, for the
    player's seat there alone. This computer only (another device can't send its library anywhere)."""
    require_local(request)
    target = handoff_target(body.url)
    if target is None:
        raise HTTPException(422, "Decks only go to a Fyodor on this network (http://address:port)")
    payload = await run_in_threadpool(library_payload, services)
    if not payload["decks"]:
        return {"token": None, "decks": 0}
    data = json.dumps(payload, separators=(",", ":")).encode()
    try:
        token = await post_handoff(target, data)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Couldn't reach that table's computer to bring your decks") from None
    return {"token": token, "decks": len(payload["decks"])}
