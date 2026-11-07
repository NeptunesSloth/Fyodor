"""Game night endpoints: agreed endings and the rematch vote (docs/GAME_NIGHT_FLOW.md §4 and §6).

* **Propose / answer:** any remaining player proposes ending the game with a result; it is recorded
  only when every remaining player agrees, and it is marked as an agreed result, never as one the
  rules engine decided. One decline and the game simply continues.
* **Rules result:** when the rules engine ends the game (a winner, 104.2, or a draw, 104.4) the server opens the same
  proposal with the engine's result (``app.multiplayer.night.follow_rules``); the players who were in the game when it ended
  each confirm it with one click, and it is recorded as the engine's result. Undoing the deciding action withdraws it.
* **Vote:** after a recorded result each seated player picks Rematch (same decks) or Lobby. Everyone
  rematch: a brand-new game at the same table. Anyone lobby: the pod goes back to the lobby with
  every deck still selected. The host can settle a vote that hangs (someone left or disconnected).
"""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import is_local_request
from app.api.games import ServicesDep, _room, authorize, record_game_result
from app.game.factory import PlayerSetup, new_game
from app.game.rules_state import start_rules
from app.game.session import GameSession
from app.game.state import GameState, PlayerState
from app.game.visibility import publicly_visible
from app.multiplayer.hub import Room
from app.multiplayer.lobby import LobbySeatInfo, LobbySettings, SubmittedDeck
from app.multiplayer.night import Night, Proposal
from app.services import Services

router = APIRouter(tags=["game night"])

ResultType = Literal["single", "multiple", "draw", "no_result"]


class ProposeIn(BaseModel):
    result_type: ResultType
    winners: list[str] = Field(default_factory=list, max_length=6)
    as_player: str | None = Field(default=None, max_length=8)


class AnswerIn(BaseModel):
    agree: bool
    as_player: str | None = Field(default=None, max_length=8)


class VoteIn(BaseModel):
    choice: Literal["rematch", "lobby"]
    as_player: str | None = Field(default=None, max_length=8)
    force: bool = False  # host: settle the vote now with this choice


def remaining(state: GameState) -> list[str]:
    """Players still in the game: not removed from the table, not conceded or lost (800.4a)."""
    r = state.rules
    return [pid for pid in state.seat_order
            if not state.players[pid].left and (r is None or (pid not in r.conceded and pid not in r.lost))]


def _actor(room: Room, request: Request, token: str | None, as_player: str | None) -> str:
    _, actor = authorize(room, local=is_local_request(request), token=token, viewer=None, as_player=as_player)
    if actor is None:
        raise HTTPException(403, "Spectators can't do that")
    return actor


def _check_result(state: GameState, result_type: str, winners: list[str]) -> None:
    if any(w not in state.players for w in winners) or len(set(winners)) != len(winners):
        raise HTTPException(422, "Unknown winner")
    wanted = {"single": (1, 1), "multiple": (2, 6), "draw": (0, 0), "no_result": (0, 0)}[result_type]
    if not wanted[0] <= len(winners) <= wanted[1]:
        raise HTTPException(422, {"single": "Pick one winner", "multiple": "Pick at least two winners"}.get(
            result_type, "A draw has no winner"))


@router.post("/games/{game_id}/night/propose")
async def propose_end(game_id: str, body: ProposeIn, request: Request, services: ServicesDep,
                      x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _room(services, game_id)
    async with room.lock:
        actor = _actor(room, request, x_seat_token, body.as_player)
        state = room.session.state
        night = room.night
        if night.result is not None:
            raise HTTPException(409, "This game's result is already recorded")
        if actor not in remaining(state):
            raise HTTPException(403, "Only players still in the game can propose ending it")
        _check_result(state, body.result_type, body.winners)
        night.proposal = Proposal(by=actor, result_type=body.result_type, winners=list(body.winners), agreed={actor})
        room.session.notice(f"{room.seat_name(actor)} proposes ending the game ({_describe(room, night.proposal)}).")
        _settle_proposal(services, room)
    await services.hub.broadcast(room)
    return room.night.public(room.seat_name)


@router.post("/games/{game_id}/night/answer")
async def answer_proposal(game_id: str, body: AnswerIn, request: Request, services: ServicesDep,
                          x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _room(services, game_id)
    async with room.lock:
        actor = _actor(room, request, x_seat_token, body.as_player)
        night = room.night
        proposal = night.proposal
        if proposal is None:
            raise HTTPException(409, "Nobody has proposed ending the game")
        if proposal.rules is not None:  # -- rules result -- the players in the game when it ended confirm it
            if room.mode != "local" and actor not in proposal.voters:
                raise HTTPException(403, "Only the players still in the game when it ended confirm this")
        elif actor not in remaining(room.session.state):
            raise HTTPException(403, "Only players still in the game answer this")
        if not body.agree:
            night.proposal = None
            if proposal.rules is not None:
                room.session.notice(f"{room.seat_name(actor)} didn't confirm the rules result. Undo to take back the last action, "
                                    "or record the result by hand with End game.")
            else:
                room.session.notice(f"{room.seat_name(actor)} declined. The game continues.")
        else:
            proposal.agreed.add(actor)
            _settle_proposal(services, room)
    await services.hub.broadcast(room)
    return room.night.public(room.seat_name)


def _describe(room: Room, p: Proposal) -> str:
    if p.result_type in ("single", "multiple"):
        return " and ".join(room.seat_name(w) for w in p.winners) + (" wins" if len(p.winners) == 1 else " win")
    return {"draw": "a draw", "no_result": "no result"}[p.result_type]


def _settle_proposal(services: Services, room: Room) -> None:
    p = room.night.proposal
    if p is not None and p.rules is not None:
        # -- rules result -- recorded as the engine's result once every player in the game at the end confirmed it (a seat
        # nobody has taken can't answer, so it isn't waited for); one person runs a hot-seat table: their click settles it
        state = room.session.state
        needed = {pid for pid in p.voters if pid in state.players and not state.players[pid].left
                  and (room.mode == "local" or (pid in room.seats and room.seats[pid].token))}
        if room.mode == "local" or needed <= p.agreed:
            record_game_result(services, room, p.result_type, p.winners, rules=p.rules)
    elif p is not None and set(remaining(room.session.state)) <= p.agreed:
        record_game_result(services, room, p.result_type, p.winners, agreed=True)


@router.post("/games/{game_id}/night/vote")
async def vote(game_id: str, body: VoteIn, request: Request, services: ServicesDep,
               x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    room = _room(services, game_id)
    async with room.lock:
        night = room.night
        if room.game is None or night.result is None:
            raise HTTPException(409, "The game isn't over yet")
        if body.force:
            if room.mode == "lan" and not room.is_host(x_seat_token):
                raise HTTPException(403, "Only the host can settle the vote")
            decision: str | None = body.choice
        else:
            actor = _actor(room, request, x_seat_token, body.as_player)
            night.votes[actor] = body.choice
            voters = [pid for pid in room.session.state.seat_order if room.mode == "local" or room.seats[pid].token]
            # one person runs a hot-seat table: their choice decides
            if room.mode == "local" or body.choice == "lobby":
                decision = body.choice
            elif all(night.votes.get(pid) == "rematch" for pid in voters):
                decision = "rematch"
            else:
                decision = None
        if decision == "rematch":
            rematch(services, room)
        elif decision == "lobby":
            if room.mode == "local":
                raise HTTPException(409, "A hot-seat table has no lobby; start a new game from Play")
            to_lobby(services, room)
    await services.hub.broadcast(room)
    return {"decision": decision, "night": room.night.public(room.seat_name)}


def rematch(services: Services, room: Room) -> None:
    """A completely fresh game with the same pod and decks; nothing match-local carries over (§6)."""
    old = room.session.state
    night = room.night
    seats = [pid for pid in old.seat_order if not old.players[pid].left]
    missing = [room.seat_name(pid) for pid in seats if pid not in night.setups]
    if missing:
        raise HTTPException(409, f"The decks for {', '.join(missing)} aren't known here; return to the lobby instead")
    result = night.result or {}
    winner = result["winners"][0] if result.get("result_type") == "single" and len(result.get("winners") or []) == 1 else None
    order, source, rolls = Night.plan(seats, winner)
    settings = old.settings.model_copy(deep=True)
    state = new_game([night.setups[pid] for pid in order], name=old.name, format=old.format, settings=settings,
                     shuffle=True, first_player=0, related_tokens=services.related_tokens)
    state.id = room.game_id  # the table keeps its address for the whole night
    if settings.automation != "off":
        start_rules(state)
    session = GameSession(state, cards=services.cards, history_limit=services.settings.history_limit, rules=services.rules)
    night.number += 1
    night.order_source, night.rolls, night.previous_winner = source, rolls, winner
    night.proposal, night.result, night.votes = None, None, {}
    room.result_id = None
    services.hub.start(room, session, order)
    session.notice(f"Game {night.number}: rematch with the same decks. {state.players[state.turn.active_player].name} goes first.")
    if source == "winner_last":
        session.notice(f"Turn order: {room.seat_name(night.previous_winner or '')} won the last game and goes last.")
    else:
        session.notice("Turn order: everyone rolled a d20, highest first.")
    services.autosave(room)


def _info_from_setup(setup: PlayerSetup | None, player: PlayerState) -> LobbySeatInfo:
    info = LobbySeatInfo(name=player.name, color=player.color)
    if setup is not None and setup.cards:
        info.deck = SubmittedDeck(
            name=setup.deck_name or "Deck", cards=list(setup.cards),
            commanders=[c.name for c in setup.cards if c.section == "commander"], color_identity=[],
            card_count=sum(c.quantity for c in setup.cards if c.section != "maybeboard"), collection=list(setup.collection))
    return info


def to_lobby(services: Services, room: Room) -> None:
    """Back to the persistent lobby: same seats and tokens, each player's deck still selected (§1)."""
    old = room.session.state
    night = room.night
    infos: dict[str, LobbySeatInfo] = {}
    for pid in old.seat_order:
        info = night.infos.get(pid) or _info_from_setup(night.setups.get(pid), old.players[pid])
        info.ready = False
        infos[pid] = info
    if room.lobby is None:
        room.lobby = LobbySettings(name=old.name, format=old.format, seats=len(old.seat_order))
    # (-- table permissions -- the host's latest choice, made in the lobby or at the table, holds for the next game too)
    room.lobby = room.lobby.model_copy(update={"seats": max(room.lobby.seats, len(room.seats)),
                                               "card_permissions": old.settings.card_permissions})
    room.session.history.listener = None
    if services.hub.journal is not None:
        services.hub.journal.forget(room.id)
    room.game = None
    room.phase = "lobby"
    room.lobby_seats = infos
    services.hub.resize_lobby(room, room.lobby.seats)
    night.number += 1
    night.order_source, night.rolls, night.previous_winner = "host", [], None
    night.proposal, night.result, night.votes = None, None, {}
    night.setups, night.infos = {}, {}
    room.result_id = None
    # (spectator activities) a deck queued while out of that game becomes the proposed deck (not ready: they confirm or change it)
    for pid, info in infos.items():
        token = room.seats[pid].token if pid in room.seats else None
        queued = night.queued.pop(token, None) if token else None
        if queued is not None:
            queued.collection = list(info.collection)
            info.deck = info.queued = queued


@router.get("/games/{game_id}/night/deck")
async def own_deck(game_id: str, request: Request, services: ServicesDep, viewer: str | None = None,
                   x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """The deck this seat brought to the current game, for its own side activities (opening-hand
    practice while eliminated, ELIMINATION_HUB.md). Only ever the asking seat's own deck."""
    room = _room(services, game_id)
    seat, _ = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=viewer, as_player=None)
    setup = room.night.setups.get(seat)
    if setup is None:
        raise HTTPException(404, "Your deck isn't available at this table")
    return {"name": setup.deck_name, "cards": [
        {"section": c.section, "quantity": c.quantity, "name": c.name, "printing_id": c.printing_id}
        for c in setup.cards if c.section in ("main", "commander")]}


# --------------------------------------------------------------------------- nudges, reactions and pings

REACTIONS = ("👍", "😂", "😮", "🔥", "💀", "👏")
EMOTES = ("Nice!", "GG", "Ouch", "Thinking…", "Hold on", "Well played", "Oops")  # short table talk from players still in the game
NUDGE_COOLDOWN = 30.0  # seconds between nudges from one player, and to one player
REACT_COOLDOWN = 3.0
PING_COOLDOWN = 0.6  # a ping is a quick "this one!", not a stream


class SignalIn(BaseModel):
    kind: Literal["nudge", "react", "ping"]
    emoji: str | None = Field(default=None, max_length=16)
    as_player: str | None = Field(default=None, max_length=8)
    # a ping points at a card everyone can see, or at a spot on someone's battlefield (virtual units, as card x/y)
    card: str | None = Field(default=None, max_length=80)
    player: str | None = Field(default=None, max_length=8)
    x: float | None = Field(default=None, ge=-200, le=1200)
    y: float | None = Field(default=None, ge=-200, le=800)


def waiting_on(state: GameState) -> str:
    """Who the game is waiting on: the player making a decision, the one with priority, else the active player."""
    r = state.rules
    if r is not None and r.decision is not None:
        return r.decision.player
    if r is not None and r.priority:
        return r.priority
    return state.turn.active_player


@router.post("/games/{game_id}/night/signal")
async def signal(game_id: str, body: SignalIn, request: Request, services: ServicesDep,
                 x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """A soft social signal (TABLETOP_QOL_MILESTONE #13-14): a nudge, a reaction, or a ping ("look here", as in Tabletop
    Simulator). Nothing here touches the game: it is never logged, saved or replayed, carries no hidden information
    and is rate limited."""
    room = _room(services, game_id)
    viewer, actor = authorize(room, local=is_local_request(request), token=x_seat_token, viewer=None, as_player=body.as_player)
    state = room.session.state
    now = time.monotonic()
    who = actor or f"spectator:{x_seat_token or ''}"
    last = room.night.signals
    if body.kind == "nudge":
        if actor is None:
            raise HTTPException(403, "Spectators can't nudge")
        target = waiting_on(state)
        if target == actor:
            raise HTTPException(409, "The game is waiting on you")
        if now - last.get(f"nudge-from:{actor}", -1e9) < NUDGE_COOLDOWN or now - last.get(f"nudge-to:{target}", -1e9) < NUDGE_COOLDOWN:
            raise HTTPException(429, "Give them a moment: you can nudge again in half a minute")
        last[f"nudge-from:{actor}"] = last[f"nudge-to:{target}"] = now
        await services.hub.send_to(room, target, {"type": "signal", "kind": "nudge", "from": actor,
                                                 "from_name": room.seat_name(actor), "to": target})
        return {"to": target}
    if body.kind == "ping":
        if actor is None:
            raise HTTPException(403, "Spectators can't ping")
        if now - last.get(f"ping:{actor}", -1e9) < PING_COOLDOWN:
            raise HTTPException(429, "One ping at a time")
        ping: dict[str, Any] = {"type": "signal", "kind": "ping", "from": actor, "from_name": room.seat_name(actor)}
        if body.card is not None:
            card = state.cards.get(body.card)
            # only a card every seat and spectator can see: pointing at a hidden one would hand out its id
            if card is None or not publicly_visible(state, card):
                raise HTTPException(404, "Nothing everyone can see there")
            ping["card"] = card.id
        elif body.player in state.players and body.x is not None and body.y is not None:
            ping.update(player=body.player, x=round(body.x, 1), y=round(body.y, 1))
        else:
            raise HTTPException(422, "Point at a card or at a spot on a battlefield")
        last[f"ping:{actor}"] = now
        await _to_everyone(services, room, ping)
        return {"sent": True}
    # reactions: from spectators and players already out of the game; emotes (fixed table talk): from anyone at the table
    emote = body.emoji in EMOTES
    if body.emoji not in REACTIONS and not emote:
        raise HTTPException(422, "Unknown reaction")
    if not room.night.reactions:  # (spectator activities) the host's table-wide switch
        raise HTTPException(409, "The host has turned reactions off at this table")
    if actor is not None and actor in remaining(state) and not emote:
        raise HTTPException(403, "Reactions are for players who are out and spectators")
    if now - last.get(f"react:{who}", -1e9) < REACT_COOLDOWN:
        raise HTTPException(429, "One reaction every few seconds")
    last[f"react:{who}"] = now
    message: dict[str, Any] = {"type": "signal", "kind": "react", "from": actor, "from_name": room.seat_name(actor) if actor else "A spectator",
               "emoji": body.emoji}
    await _to_everyone(services, room, message)
    return {"sent": True}


class ReactionsIn(BaseModel):
    on: bool


@router.post("/games/{game_id}/night/reactions")
async def set_reactions(game_id: str, body: ReactionsIn, request: Request, services: ServicesDep,
                        x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    """(spectator activities) The host turns reactions on or off for the whole table (each player can still mute them for
    themselves). A table setting for the session: it is not part of the game, its log or its history."""
    room = _room(services, game_id)
    if room.practice is not None:
        raise HTTPException(409, "A practice table has no reactions")
    if room.mode == "lan" and not room.is_host(x_seat_token):
        raise HTTPException(403, "Only the host can change that")
    if room.mode == "local" and not is_local_request(request):
        raise HTTPException(403, "This is a hot-seat game on the host computer")
    room.night.reactions = body.on
    services.hub.persist(room)
    await services.hub.broadcast(room)
    return {"reactions": room.night.reactions}


async def _to_everyone(services: Services, room: Room, message: dict[str, Any]) -> None:
    for conn in list(room.connections.values()):
        try:
            await conn.send(message)
        except Exception:  # noqa: BLE001 - best effort, like every push
            services.hub.disconnect(room, conn)
