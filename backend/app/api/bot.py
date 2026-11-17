"""-- test opponent -- seating an opponent that plays a deck, and the table's bot speed (app/game/bot.py, app/multiplayer/bots.py).

* ``POST /games/{id}/bot``: the host seats an opponent with one of their saved decks (or precons). The server builds the ``add_bot`` action
  from the deck, as it builds ``load_deck``: a client can't send card lists.
* ``POST /games/{id}/bot/speed``: Normal, Fast or Step (anyone seated: it only paces the opponents' actions).
* ``POST /games/{id}/bot/step``: Step mode's button: play the opponent's next action.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError

from app.api.deps import is_local_request
from app.api.games import ServicesDep, _check_table_open, _deck_cards, _room, authorize
from app.decks import service as deck_service
from app.decks.repository import DeckNotFound
from app.game import actions as A
from app.game.errors import ActionError
from app.multiplayer import bots
from app.services import Services
from app.textutil import clean_text

router = APIRouter(tags=["games"])


class BotIn(BaseModel):
    deck_id: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=40)
    level: Literal["simple", "intermediate", "advanced"] = "intermediate"  # -- bot levels -- how well it plays
    as_player: str | None = Field(default=None, alias="as", max_length=16)


class SpeedIn(BaseModel):
    speed: bots.Speed
    as_player: str | None = Field(default=None, alias="as", max_length=16)


class StepIn(BaseModel):
    as_player: str | None = Field(default=None, alias="as", max_length=16)


def _cards(services: Services, deck_id: str) -> tuple[str, list[A.LoadDeckCard]]:
    try:
        deck = services.decks.get(deck_id)
    except DeckNotFound:
        raise HTTPException(404, "That deck isn't in your library") from None
    entries, _ = deck_service.reconcile_entries(deck.entries, services.cards)
    cards = [A.LoadDeckCard(section=c.section, quantity=c.quantity, name=c.name, printing_id=c.printing_id)
             for c in _deck_cards(services, entries) if c.section in ("commander", "companion", "main", "sideboard", "attractions")]
    return deck.name, cards


@router.post("/games/{game_id}/bot", status_code=201)
async def add_bot(game_id: str, body: BotIn, request: Request, services: ServicesDep,
                  x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _room(services, game_id)
    viewer, actor = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=None, as_player=body.as_player)
    if actor is None:
        raise HTTPException(403, "Spectators can't seat an opponent")
    if room.mode == "lan" and not room.is_host(x_seat_token):
        raise HTTPException(403, "Only the host can seat an opponent")
    deck_name, cards = await run_in_threadpool(_cards, services, body.deck_id)
    name = clean_text(body.name or "", 40) or None
    action = A.AddBot(name=name, level=body.level, deck_name=deck_name[:120], deck_id=body.deck_id, cards=cards)
    async with room.lock:
        _check_table_open(room)
        try:
            room.session.perform(actor, action, trusted=True)
        except (ActionError, ValidationError) as exc:
            raise HTTPException(409, str(exc)) from exc
        services.hub.after_change(room)
    return {"view": await services.hub.broadcast(room, viewer=viewer) or services.hub.view(room, viewer)}


@router.post("/games/{game_id}/bot/speed")
async def bot_speed(game_id: str, body: SpeedIn, request: Request, services: ServicesDep,
                    x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _room(services, game_id)
    viewer, actor = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=None, as_player=body.as_player)
    if actor is None:
        raise HTTPException(403, "Spectators can't change that")
    if not bots.has_bot(room):
        raise HTTPException(409, "There is no test opponent at this table")
    bots.set_speed(services.hub, room, body.speed)
    return {"view": await services.hub.broadcast(room, viewer=viewer) or services.hub.view(room, viewer)}


@router.post("/games/{game_id}/bot/step")
async def bot_step(game_id: str, body: StepIn, request: Request, services: ServicesDep,
                   x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _room(services, game_id)
    viewer, actor = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=None, as_player=body.as_player)
    if actor is None:
        raise HTTPException(403, "Spectators can't do that")
    if not bots.has_bot(room):
        raise HTTPException(409, "There is no test opponent at this table")
    if not bots.waiting(room):
        raise HTTPException(409, "The opponent has nothing to do right now")
    bots.step_once(services.hub, room)
    return {"view": services.hub.view(room, viewer)}
