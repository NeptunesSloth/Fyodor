"""The eliminated player's side activities (docs/ELIMINATION_HUB.md): a Practice Table and Deck Lab.

* **Practice Table:** a private sandbox game with the player's own deck while the live game goes on. It is a
  separate room with its own ``GameState``, history and seat token. Nothing flows from it to the live game
  (actions, log, revision, saves, pod stats, reconnects) and nothing flows from the live game into it but the
  player's own deck list. Only that player holds its token; it is never listed or joinable by code.
* **Deck Lab:** a copy of the deck the player brought to this game, to edit and save for the next one. The
  host computer gets a new deck in its library (opened in the deck editor); a guest's browser gets the list
  to keep in its own "My decks". The running game's deck snapshot and the library deck it came from are
  never touched; choosing the next deck still happens in the lobby.
"""

from __future__ import annotations

from typing import Annotated, Any, get_args

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import is_local_request
from app.api.games import ServicesDep, _room, authorize
from app.decks.models import DeckEntry, DeckIn, Section
from app.decks.parser import format_deck_text
from app.game.factory import PlayerSetup, new_game
from app.game.mulligan import resolve_policy
from app.game.session import GameSession
from app.game.state import GameSettings
from app.multiplayer.elimination import PracticeLink, out_players
from app.multiplayer.hub import GameHub, Room
from app.services import Services

router = APIRouter(tags=["elimination hub"])


class SeatIn(BaseModel):
    viewer: str | None = Field(default=None, max_length=32)  # hot-seat tables: whose activity this is
    as_player: str | None = Field(default=None, max_length=8)


class PracticeIn(SeatIn):
    reset: bool = False  # start a fresh practice table instead of resuming the one you have


def _seat(room: Room, request: Request, token: str | None, body: SeatIn) -> str:
    """The live game's seat asking (never a spectator: a practice table is built from your own deck)."""
    _, actor = authorize(room, local=is_local_request(request), token=token, viewer=body.viewer,
                         as_player=body.as_player or (body.viewer if room.mode == "local" else None))
    if actor is None:
        raise HTTPException(403, "Spectators have no deck here")
    return actor


async def _put_away(hub: GameHub, room: Room) -> None:
    """Close a practice table, and the sockets still open on it (they stop; nothing reconnects to it)."""
    hub.close(room.id)
    for pid in list(room.seats):
        await hub.drop_connections(room, pid, code=4404, reason="This practice table was put away")


async def sweep(hub: GameHub) -> None:
    """Close practice tables whose live game is gone or has moved on (a rematch, the lobby)."""
    for room in list(hub.rooms.values()):
        link = room.practice
        if link is None:
            continue
        live = hub.get(link.live)
        if live is None or not live.started or live.night.number != link.game:
            await _put_away(hub, room)


def _practice_of(hub: GameHub, live: Room, seat: str) -> list[Room]:
    return [r for r in hub.rooms.values() if r.practice is not None and r.practice.live == live.id and r.practice.seat == seat]


@router.post("/games/{game_id}/practice")
async def open_practice(game_id: str, body: PracticeIn, request: Request, services: ServicesDep,
                        x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Your private practice table for this game: resumed if you have one, else dealt fresh from your own deck."""
    hub = services.hub
    await sweep(hub)
    live = _room(services, game_id)
    if live.practice is not None:
        raise HTTPException(409, "This is already a practice table")
    async with live.lock:
        seat = _seat(live, request, x_seat_token, body)
        state = live.session.state
        if live.night.result is not None or seat not in out_players(state):
            raise HTTPException(409, "A practice table is for players who are out while the game goes on")
        setup = live.night.setups.get(seat)
        if setup is None or not setup.cards:
            raise HTTPException(404, "Your deck isn't available at this table")
        mine = _practice_of(hub, live, seat)
        if mine and not body.reset:
            practice = mine[0]
            return {"game_id": practice.id, "token": hub.reissue_seat(practice, "p1"), "resumed": True}
        for old in mine:
            await _put_away(hub, old)
        player = state.players[seat]
        settings = GameSettings(starting_life=state.settings.starting_life, deck_privacy="private", allow_test_objects=True,
                                mulligan=resolve_policy("commander_london"))
        table = new_game([PlayerSetup(name=player.name, deck_name=setup.deck_name, cards=list(setup.cards), color=player.color)],
                         name=f"Practice — {player.name}", format=state.format, settings=settings, shuffle=True,
                         related_tokens=services.related_tokens)
        session = GameSession(table, cards=services.cards, history_limit=services.settings.history_limit, rules=services.rules)
        session.notice("Practice table: only you see it. Nothing here reaches the live game.")
        practice = hub.create_practice(session, PracticeLink(live=live.id, seat=seat, game=live.night.number,
                                                             local=live.mode == "local"))
        _, token = hub.claim_seat(practice, name=player.name, seat="p1")
    return {"game_id": practice.id, "token": token, "resumed": False}


@router.delete("/games/{game_id}/practice", status_code=204)
async def close_practice(game_id: str, request: Request, services: ServicesDep, viewer: str | None = None,
                         x_seat_token: Annotated[str | None, Header()] = None) -> Response:
    """Put your practice table away (the live game is over, or you are done)."""
    live = _room(services, game_id)
    seat = _seat(live, request, x_seat_token, SeatIn(viewer=viewer))
    for room in _practice_of(services.hub, live, seat):
        await _put_away(services.hub, room)
    await sweep(services.hub)
    return Response(status_code=204)


SECTIONS = set(get_args(Section))


def _copy_entries(services: Services, setup: PlayerSetup) -> list[DeckEntry]:
    known = services.cards.get_many([c.printing_id for c in setup.cards if c.printing_id]) if services.cards.available else {}
    out = []
    for c in setup.cards:
        if c.section not in SECTIONS:
            continue
        card = known.get(c.printing_id or "")
        out.append(DeckEntry(section=c.section, quantity=c.quantity, name=c.name,  # type: ignore[arg-type]
                             printing_id=c.printing_id if card else None, oracle_id=card["oracle_id"] if card else None,
                             set_code=card["set_code"] if card else None,
                             collector_number=card["collector_number"] if card else None, categories=list(c.categories)[:20]))
    return out


@router.post("/games/{game_id}/deck-lab")
async def deck_lab(game_id: str, body: SeatIn, request: Request, services: ServicesDep,
                   x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """A copy of the deck you brought to this game, for the next one. On the host computer the copy is a new deck in
    the library (``deck_id``, opened in the deck editor); elsewhere it is the list, for this browser's "My decks"."""
    live = _room(services, game_id)
    async with live.lock:
        seat = _seat(live, request, x_seat_token, body)
        setup = live.night.setups.get(seat)
        if setup is None or not setup.cards:
            raise HTTPException(404, "Your deck isn't available at this table")
        entries = _copy_entries(services, setup)
    name = f"{setup.deck_name or live.seat_name(seat) + '’s deck'} (copy)"[:120]
    deck_id = None
    if is_local_request(request):
        deck_id = services.decks.create(DeckIn(name=name, entries=entries)).id
    return {"deck_id": deck_id, "name": name, "text": format_deck_text([e.model_dump() for e in entries]),
            "commanders": [e.name for e in entries if e.section == "commander"]}
