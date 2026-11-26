"""Spectator side activities (docs/SPECTATOR_ACTIVITIES_MILESTONE.md) for players who are out and spectators.

* ``GET /games/{id}/watch``: a compact live summary for the practice table's corner, from the public (spectator) view.
* ``GET /games/{id}/sandbox/board`` and ``POST /games/{id}/sandbox/combat``: the damage sandbox. The board comes from the
  public view; a "what if" combat is worked out on a throwaway table from what the person sent, never from the live game.
* ``/games/{id}/predictions``: fake-point predictions, in memory only, revealed and scored when the game ends.
* ``/games/{id}/next-deck``: queue the deck for the next game; it becomes the proposed lobby deck when the pod returns to
  the lobby (a same-decks rematch ignores it). Nothing about the current game or lobby changes.

None of these creates a game action or touches the live game's state, log, history, revision or saves. The live view is
always built for SPECTATOR (never OMNISCIENT), whoever asks: being out of the game grants nothing hidden.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.api.deps import is_local_request
from app.api.games import LobbyDeckIn, ServicesDep, _import_for_lobby, _room, authorize
from app.game.resolve import NoCardInfo
from app.game.visibility import SPECTATOR
from app.multiplayer.elimination import out_players
from app.multiplayer.hub import Room
from app.multiplayer.lobby import DeckTooLarge, SubmittedDeck
from app.multiplayer.night import still_in
from app.multiplayer.sandbox import Scenario, ScenarioError, public_board, simulate
from app.multiplayer.spectate import MARKETS, STAKES, Market, PredictionError, live_summary, person_key
from app.services import Services
from app.textutil import clean_text

router = APIRouter(tags=["spectator activities"])


def _live(services: Services, game_id: str) -> Room:
    room = _room(services, game_id)
    if room.practice is not None:
        raise HTTPException(409, "This is a practice table, not a live game")
    if not room.started:
        raise HTTPException(409, "The game hasn't started yet")
    return room


def _who(room: Room, request: Request, token: str | None, viewer: str | None) -> str | None:
    """Anyone who may watch this table (a seat, a spectator, the host computer); returns the acting seat, if any."""
    _, actor = authorize(room, conn=request, token=token, viewer=viewer, as_player=None)
    return actor


def public_view(room: Room) -> dict[str, Any]:
    """The live table as a spectator sees it: the only view these activities read."""
    return room.session.view(SPECTATOR)


@router.get("/games/{game_id}/watch")
async def watch(game_id: str, request: Request, services: ServicesDep, viewer: str | None = None,
                x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """A compact public summary of the live game (life, poison, commander damage, turn, stack, latest log lines)."""
    room = _live(services, game_id)
    _who(room, request, x_seat_token, viewer)
    summary = live_summary(public_view(room))
    night = room.night
    return {**summary, "game": night.number, "result": night.result, "revision": room.revision}


# --------------------------------------------------------------------------- damage sandbox


@router.get("/games/{game_id}/sandbox/board")
async def sandbox_board(game_id: str, request: Request, services: ServicesDep, viewer: str | None = None,
                        x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """The public creatures and players to start a "what if" from (COPY CURRENT PUBLIC COMBAT)."""
    room = _live(services, game_id)
    _who(room, request, x_seat_token, viewer)
    view = public_view(room)
    return public_board(view, room.session.state, services.cards if services.cards.available else NoCardInfo())


@router.post("/games/{game_id}/sandbox/combat")
async def sandbox_combat(game_id: str, body: Scenario, request: Request, services: ServicesDep, viewer: str | None = None,
                         x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Work out a combat the person set up. Informational only: it reads nothing from the live game and changes nothing."""
    room = _live(services, game_id)
    _who(room, request, x_seat_token, viewer)
    try:
        return await run_in_threadpool(simulate, body)
    except ScenarioError as exc:
        raise HTTPException(422, str(exc)) from exc


# --------------------------------------------------------------------------- predictions


class PredictIn(BaseModel):
    market: Market
    choice: str = Field(max_length=8)
    stake: int
    name: str | None = Field(default=None, max_length=40)  # a spectator's name for the recap


def _predictor(room: Room, request: Request, token: str | None) -> tuple[str | None, str | None, bool]:
    """(person key, seat, may predict). Predictions are for LAN tables, among players who are out and spectators."""
    actor = _who(room, request, token, None)
    if room.mode != "lan" or not token:
        return None, actor, False
    allowed = actor is None or actor in out_players(room.session.state)
    return person_key(token), actor, allowed


def _predictions_view(room: Room, key: str | None, allowed: bool) -> dict[str, Any]:
    night = room.night
    state = room.session.state
    room.pulse.observe(state, night.number, night.result, room.seat_name)
    room.predictions.observe(room.pulse, night.result)
    names = room.seat_name
    return {
        "game": night.number,
        "can_predict": allowed and night.result is None,
        "stakes": list(STAKES),
        "markets": list(MARKETS),
        "candidates": [{"id": pid, "name": names(pid)} for pid in still_in(state)] if night.result is None else [],
        **room.predictions.mine(key, night.number, names),
        "standings": room.predictions.standings(),
        "recap": room.predictions.recap(night.number, names) if night.result is not None else None,
    }


@router.get("/games/{game_id}/predictions")
async def get_predictions(game_id: str, request: Request, services: ServicesDep,
                          x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _live(services, game_id)
    key, _, allowed = _predictor(room, request, x_seat_token)
    return _predictions_view(room, key, allowed)


@router.post("/games/{game_id}/predictions")
async def predict(game_id: str, body: PredictIn, request: Request, services: ServicesDep,
                  x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Place (or change) your pick for one market. Hidden from everyone else until the game ends."""
    room = _live(services, game_id)
    key, actor, allowed = _predictor(room, request, x_seat_token)
    if room.mode != "lan":
        raise HTTPException(409, "Predictions are for LAN tables")
    if key is None or not allowed:
        raise HTTPException(403, "Predictions are for players who are out and spectators")
    if room.night.result is not None:
        raise HTTPException(409, "This game is over: predictions are settled")
    name = room.seat_name(actor) if actor else clean_text(body.name or "", 24) or "Spectator"
    view = _predictions_view(room, key, allowed)  # (follows the table first, so a "next out" pick counts from now)
    try:
        room.predictions.place(key, name, game=room.night.number, market=body.market, choice=body.choice, stake=body.stake,
                               candidates=[c["id"] for c in view["candidates"]])
    except PredictionError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _predictions_view(room, key, allowed)


@router.delete("/games/{game_id}/predictions/{market}")
async def withdraw_prediction(game_id: str, market: Market, request: Request, services: ServicesDep,
                              x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _live(services, game_id)
    key, _, allowed = _predictor(room, request, x_seat_token)
    if key is None or room.night.result is not None:
        raise HTTPException(409, "Nothing to withdraw")
    room.predictions.withdraw(key, room.night.number, market)
    return _predictions_view(room, key, allowed)


# --------------------------------------------------------------------------- next-game deck queue


def _queue_key(room: Room, request: Request, token: str | None) -> str:
    """The seat or spectator token a queued deck belongs to: a player who is out (or any player once the game is over), or a
    spectator. Players still in the game are busy playing it."""
    if room.mode != "lan":
        raise HTTPException(409, "A hot-seat table has no lobby; pick the next deck when you start a new game")
    actor = _who(room, request, token, None)
    if not token or room.seat_for_token(token) is None:
        raise HTTPException(403, "Join the table to queue a deck")
    if actor is not None and room.night.result is None and actor not in out_players(room.session.state):
        raise HTTPException(403, "You can queue your next deck once you are out of this game or it is over")
    return token


def _queued_summary(deck: SubmittedDeck | None) -> dict[str, Any] | None:
    if deck is None:
        return None
    return {"name": deck.name, "commanders": list(deck.commanders), "commander_ids": list(deck.commander_ids),
            "color_identity": list(deck.color_identity), "card_count": deck.card_count}


def _table(services: Services, game_id: str, token: str | None) -> Room:
    """A live table or its lobby (a queued deck waits there until its owner takes a seat)."""
    room = _room(services, game_id)
    if room.practice is not None:
        raise HTTPException(409, "This is a practice table, not a live game")
    if room.seat_for_token(token) is None:
        raise HTTPException(403, "Join the table first")
    return room


@router.get("/games/{game_id}/next-deck")
async def get_next_deck(game_id: str, services: ServicesDep,
                        x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _table(services, game_id, x_seat_token)
    return {"queued": _queued_summary(room.night.queued.get(x_seat_token or ""))}


@router.post("/games/{game_id}/next-deck")
async def queue_next_deck(game_id: str, body: LobbyDeckIn, request: Request, services: ServicesDep,
                          x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """Queue a deck (a saved list, or a deck from the host's library on the host computer) for the next game. It is resolved
    now, so the lobby can propose it at once; the current game and lobby are not touched."""
    room = _live(services, game_id)
    key = _queue_key(room, request, x_seat_token)
    if body.archidekt:
        raise HTTPException(422, "Queue a saved deck or a pasted list; fetch Archidekt decks in the lobby")
    try:
        deck = await run_in_threadpool(_import_for_lobby, services, body, is_local_request(request))
    except DeckTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc
    async with room.lock:
        if room.seat_for_token(key) is None:
            raise HTTPException(409, "Your seat changed while the deck was loading")
        room.night.queued[key] = deck
    return {"queued": _queued_summary(deck)}


@router.delete("/games/{game_id}/next-deck", status_code=204)
async def clear_next_deck(game_id: str, services: ServicesDep,
                          x_seat_token: Annotated[str | None, Header()] = None) -> Response:
    """Keep the current deck after all (forget the queued one)."""
    room = _table(services, game_id, x_seat_token)
    room.night.queued.pop(x_seat_token or "", None)
    return Response(status_code=204)
