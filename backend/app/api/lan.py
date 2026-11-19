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
from app.cards import share
from app.cards.images import UUID_RE
from app.decks import sharing
from app.decks.models import Deck
from app.decks.parser import format_deck_text
from app.multiplayer import lan_art
from app.multiplayer.discovery import Discovery, computer_name, on_local_network
from app.multiplayer.handoff import (
    MAX_BYTES,
    MAX_CARDS,
    MAX_DECKS,
    MAX_LIST_BYTES,
    TTL,
    BroughtDeck,
    HandoffRefused,
    Library,
)
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
    cover: str | None = Field(default=None, max_length=64)


class HandoffIn(BaseModel):
    source: str = Field(alias="from", min_length=1, max_length=64)
    port: int | None = Field(default=None, ge=1, le=65535)  # the player's own Fyodor: the art this table lacks comes from it
    decks: list[BroughtDeckIn] = Field(max_length=MAX_DECKS)
    cards: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_CARDS)  # Scryfall cards the host lacked (checked on use)


class MissingIn(BaseModel):
    ids: list[str] = Field(max_length=20_000)


def _origin(sender: str, port: int | None) -> str | None:
    if port is None:
        return None
    try:
        ip = ipaddress.ip_address(sender)
    except ValueError:
        return None
    return f"http://{f'[{ip}]' if ip.version == 6 else ip}:{port}"


@router.post("/lan/handoff/missing")
async def missing_cards(body: MissingIn, request: Request, services: ServicesDep) -> dict[str, Any]:
    """Which of these printings this computer's card database lacks: a player's Fyodor sends just those along with its decks."""
    sender = _sender(request)
    if not on_local_network(sender):
        raise HTTPException(403, "Only computers on this network can bring decks")
    if not services.cards.available:
        return {"missing": []}
    return {"missing": await run_in_threadpool(share.unknown_ids, services.cards, body.ids)}


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
                         text=d.text, cover=d.cover if d.cover and UUID_RE.match(d.cover) else None) for d in body.decks]
    library = Library(source=clean_text(body.source, 40) or "another computer", decks=decks, origin=_origin(sender, body.port),
                      cards=body.cards)
    try:
        token = services.handoffs.offer(library, sender)
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
        return {"from": None, "decks": [], "unknown": []}

    def covers() -> list[str | None]:
        # each deck's commander, for its art: the printing the player has when this database knows it, else by name
        out: list[str | None] = []
        if not services.cards.available:
            return [None] * len(library.decks)
        known = services.cards.get_many([d.cover for d in library.decks if d.cover])
        for d in library.decks:
            if d.cover and d.cover in known:
                out.append(d.cover)
                continue
            card = services.cards.resolve(d.commanders[0]) if d.commanders else None
            out.append(card["id"] if card else None)
        return out

    try:
        cover_ids = await run_in_threadpool(covers)
    except Exception:  # noqa: BLE001 - art is a nicety; the list still works without it
        cover_ids = [None] * len(library.decks)
    if not library.covers_fetched:  # the commanders' art this table lacks, from the player's own Fyodor
        library.covers_fetched = True
        lan_art.bring_art(services, room, library.origin, [c for c in cover_ids if c])
    return {"from": library.source, "unknown": library.unknown, "decks": [
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


def library_payload(services: Services, library: list[Deck] | None = None) -> tuple[dict[str, Any], list[str]]:
    """This computer's deck library (or ``library``) as the host's lobby reads a pasted list (newest first, within the size
    caps), and every printing in it (the host says which it lacks)."""
    decks: list[dict[str, Any]] = []
    printings: list[str] = []
    size = 200
    for deck in services.decks.list_all() if library is None else library:
        if len(decks) >= MAX_DECKS:
            break
        if not deck.entries:
            continue
        commanders = [e for e in deck.entries if e.section == "commander"]
        item: dict[str, Any] = {"name": deck.name, "commanders": [e.name for e in commanders][:4],
                                "text": format_deck_text([e.model_dump() for e in deck.entries])}
        if commanders and commanders[0].printing_id:
            item["cover"] = commanders[0].printing_id
        cost = len(json.dumps(item).encode()) + 2
        if size + cost > MAX_LIST_BYTES or len(item["text"]) > 200_000:
            continue
        size += cost
        decks.append(item)
        printings += [e.printing_id for e in deck.entries if e.printing_id and e.section not in ("maybeboard", "tokens")]
    return {"from": computer_name(), "port": services.settings.port, "decks": decks}, list(dict.fromkeys(printings))


def card_records(services: Services, missing: list[str], room: int) -> list[dict[str, Any]]:
    """The card objects for the printings the host lacks, within ``room`` bytes and ``MAX_CARDS``."""
    out: list[dict[str, Any]] = []
    for record in share.records(services.cards, missing[:MAX_CARDS]):
        cost = len(json.dumps(record).encode()) + 2
        if cost > room:
            break
        room -= cost
        out.append(record)
    return out


async def post_json(target: str, path: str, data: bytes) -> dict[str, Any]:
    """POST to another Fyodor on the LAN. Straight to its address: no system proxy, no internet."""
    async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(5.0)) as client:
        res = await client.post(f"{target}{path}", content=data, headers={"Content-Type": "application/json"})
        res.raise_for_status()
        body = res.json()
    if not isinstance(body, dict):
        raise ValueError("not a Fyodor reply")
    return body


@router.post("/lan/send-decks")
async def send_decks(body: SendIn, request: Request, services: ServicesDep) -> dict[str, Any]:
    """Before joining a table found on the network: send this computer's deck library to that table's computer, for the
    player's seat there alone. This computer only (another device can't send its library anywhere)."""
    require_local(request)
    target = handoff_target(body.url)
    if target is None:
        raise HTTPException(422, "Decks only go to a Fyodor on this network (http://address:port)")
    payload, printings = await run_in_threadpool(library_payload, services)
    if not payload["decks"]:
        return {"token": None, "decks": 0, "cards": 0}
    # the cards the host's card database lacks (a newer set) travel along, Scryfall-shaped
    cards: list[dict[str, Any]] = []
    if printings and services.cards.available:
        try:
            reply = await post_json(target, "/api/lan/handoff/missing", json.dumps({"ids": printings[:20_000]}).encode())
            missing = [i for i in reply.get("missing", []) if isinstance(i, str)]
        except (httpx.HTTPError, ValueError):
            missing = []  # an older Fyodor without the lookup: the decks still go; the lobby there names what it lacks
        if missing:
            used = len(json.dumps(payload).encode())
            cards = await run_in_threadpool(card_records, services, missing, MAX_BYTES - used - 1000)
    payload["cards"] = cards
    data = json.dumps(payload, separators=(",", ":")).encode()
    try:
        reply = await post_json(target, "/api/lan/handoff", data)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Couldn't reach that table's computer to bring your decks") from None
    token = reply.get("token")
    if not isinstance(token, str) or not 16 <= len(token) <= 64:
        raise HTTPException(502, "That table's computer didn't take your decks")
    return {"token": token, "decks": len(payload["decks"]), "cards": len(cards)}


# --------------------------------------------------------------------------- friends' decks (app/decks/sharing.py)


@router.get("/lan/decks")
async def shared_decks(request: Request, services: ServicesDep) -> dict[str, Any]:
    """The decks this computer shares with friends on the network: names, commanders and card lists, nothing else. Read only;
    nothing at all while sharing is off (the owner's opt-in, Settings)."""
    if not on_local_network(_sender(request)):
        raise HTTPException(403, "Only computers on this network can browse shared decks")
    prefs = sharing.load(services.settings.data_dir)
    if not prefs["enabled"]:
        raise HTTPException(404, "This computer isn't sharing its decks")
    payload, _ = await run_in_threadpool(lambda: library_payload(services, sharing.shared(services.decks.list_all(), prefs)))
    return {"from": payload["from"], "decks": [{k: d[k] for k in ("name", "commanders", "text")} for d in payload["decks"]]}


@router.get("/lan/friend-decks")
async def friend_decks(url: str, request: Request) -> dict[str, Any]:
    """A friend's shared decks, asked by this computer's server (straight to their address: no proxy, no internet). This
    computer only."""
    require_local(request)
    target = handoff_target(url)
    if target is None:
        raise HTTPException(422, "Decks only come from a Fyodor on this network (http://address:port)")
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(5.0)) as client:
            res = await client.get(f"{target}/api/lan/decks")
    except httpx.HTTPError:
        raise HTTPException(502, "Couldn't reach that computer") from None
    if res.status_code == 404:
        raise HTTPException(404, "That computer isn't sharing its decks")
    if res.status_code != 200 or len(res.content) > MAX_BYTES:
        raise HTTPException(502, "That computer didn't send a deck list")
    try:
        body = res.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or not isinstance(body.get("decks"), list):
        raise HTTPException(502, "That computer didn't send a deck list")
    decks = []
    for raw in body["decks"][:MAX_DECKS]:  # from the network: checked deck by deck
        try:
            d = BroughtDeckIn.model_validate(raw)
        except ValidationError:
            continue
        decks.append({"name": clean_text(d.name, 120) or "Deck", "commanders": [clean_text(c, 200) for c in d.commanders if c.strip()],
                      "text": d.text})
    source = body.get("from")
    return {"from": clean_text(source, 40) if isinstance(source, str) else "", "url": target, "decks": decks}
