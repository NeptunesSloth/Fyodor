"""-- test opponent -- seating an opponent that plays a deck, and the table's bot speed (app/game/bot.py, app/multiplayer/bots.py).

* ``POST /games/{id}/bot``: the host seats an opponent with one of their saved decks, or a special source (``deck_id`` "@random",
  "@precon[:<id>]", "@generated": app/decks/bot_decks.py). The server builds the ``add_bot`` action
  from the deck, as it builds ``load_deck``: a client can't send card lists.
* ``POST /games/{id}/bot/speed``: Normal, Fast or Step (anyone seated: it only paces the opponents' actions).
* ``POST /games/{id}/bot/step``: Step mode's button: play the opponent's next action.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError

from app.api.deps import is_tunnel_request, room_host
from app.api.games import ServicesDep, _check_table_open, _deck_cards, _room, authorize
from app.decks import bot_decks
from app.decks import service as deck_service
from app.decks.models import DeckImportRequest
from app.decks.parser import DeckTextTooLarge
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


def _cards(services: Services, deck_id: str, seed: str = "") -> tuple[str, str | None, list[A.LoadDeckCard]]:
    """The bot's deck: one of the host's library, or a special source (app/decks/bot_decks.py: a random deck of the library, a precon,
    a generated deck; seeded from ``seed``, never saved). (name, the library deck's id or None, its cards)"""
    try:
        source = bot_decks.resolve(deck_id, library=services.decks.list_all() if deck_id == bot_decks.RANDOM else [],
                                   cards=services.cards, rng=bot_decks.seeded(seed, deck_id))
    except bot_decks.DeckSourceError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    if "text" in source:
        try:
            result = deck_service.import_any(DeckImportRequest(text=source["text"]), services.cards)
        except DeckTextTooLarge as exc:
            raise HTTPException(413, str(exc)) from exc
        entries, name, library_id = [e for e in result.entries if e.printing_id], source["name"], None  # (a card this database lacks: left out)
        if not entries:
            raise HTTPException(422, "None of that deck's cards are in the card database (update the card database)")
    else:
        try:
            deck = services.decks.get(source["deck_id"])
        except DeckNotFound:
            raise HTTPException(404, "That deck isn't in your library") from None
        entries, _ = deck_service.reconcile_entries(deck.entries, services.cards)
        name, library_id = deck.name, deck.id
    cards = [A.LoadDeckCard(section=c.section, quantity=c.quantity, name=c.name, printing_id=c.printing_id)
             for c in _deck_cards(services, entries) if c.section in ("commander", "companion", "main", "sideboard", "attractions")]
    return name, library_id, cards


@router.post("/games/{game_id}/bot", status_code=201)
async def add_bot(game_id: str, body: BotIn, request: Request, services: ServicesDep,
                  x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _room(services, game_id)
    viewer, actor = authorize(room, conn=request, token=x_seat_token, viewer=None, as_player=body.as_player)
    if actor is None:
        raise HTTPException(403, "Spectators can't seat an opponent")
    if room.mode == "lan" and not room_host(room, request, x_seat_token):
        raise HTTPException(403, "Only the host can seat an opponent")
    seed = f"{game_id}:{len(room.session.state.players)}"  # (-- bot decks -- the game and the seat it takes: the same request, the same deck)
    deck_name, library_id, cards = await run_in_threadpool(_cards, services, body.deck_id, seed)
    name = clean_text(body.name or "", 40) or None
    action = A.AddBot(name=name, level=body.level, deck_name=deck_name[:120], deck_id=library_id, cards=cards)
    async with room.lock:
        _check_table_open(room)
        try:
            room.session.perform(actor, action, trusted=True)
        except (ActionError, ValidationError) as exc:
            raise HTTPException(409, str(exc)) from exc
        services.hub.after_change(room)
    tunnel = is_tunnel_request(request)
    return {"view": await services.hub.broadcast(room, viewer=viewer, tunnel=tunnel) or services.hub.view(room, viewer, tunnel=tunnel)}


@router.post("/games/{game_id}/bot/speed")
async def bot_speed(game_id: str, body: SpeedIn, request: Request, services: ServicesDep,
                    x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _room(services, game_id)
    viewer, actor = authorize(room, conn=request, token=x_seat_token, viewer=None, as_player=body.as_player)
    if actor is None:
        raise HTTPException(403, "Spectators can't change that")
    if not bots.has_bot(room):
        raise HTTPException(409, "There is no test opponent at this table")
    bots.set_speed(services.hub, room, body.speed)
    tunnel = is_tunnel_request(request)
    return {"view": await services.hub.broadcast(room, viewer=viewer, tunnel=tunnel) or services.hub.view(room, viewer, tunnel=tunnel)}


@router.post("/games/{game_id}/bot/step")
async def bot_step(game_id: str, body: StepIn, request: Request, services: ServicesDep,
                   x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _room(services, game_id)
    viewer, actor = authorize(room, conn=request, token=x_seat_token, viewer=None, as_player=body.as_player)
    if actor is None:
        raise HTTPException(403, "Spectators can't do that")
    if not bots.has_bot(room):
        raise HTTPException(409, "There is no test opponent at this table")
    if not bots.waiting(room):
        raise HTTPException(409, "The opponent has nothing to do right now")
    bots.step_once(services.hub, room)
    return {"view": services.hub.view(room, viewer, tunnel=is_tunnel_request(request))}
