"""Creating a new game from decks."""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.game import placement
from app.game.ops import log, text
from app.game.resolve import new_id
from app.game.state import (
    CardInstance,
    CollectionCard,
    GameSettings,
    GameState,
    PlanarCard,
    Planechase,
    PlayerState,
    TurnState,
    zone_key,
)

PLAYER_COLORS = ("#d4a852", "#5fa8d3", "#c9677a", "#6fbf8f", "#a68bd6", "#d98c4a")
SECTION_ZONES = {"commander": "command", "companion": "companion", "main": "library", "sideboard": "sideboard",
                 "attractions": "attractions"}  # -- Attractions (wave 100L) -- 717.2: the supplementary Attraction deck
STARTING_LIFE = {"commander": 40, "sandbox": 40}  # Sandbox plays Commander decks, so Commander's life (editable)
_rng = secrets.SystemRandom()


@dataclass
class DeckCard:
    section: str
    quantity: int
    name: str
    printing_id: str | None
    categories: list[str] = field(default_factory=list)  # Archidekt categories (private to the owner)


@dataclass
class PlayerSetup:
    name: str
    deck_id: str | None = None
    deck_name: str | None = None
    cards: list[DeckCard] = field(default_factory=list)
    color: str | None = None
    collection: list[CollectionCard] = field(default_factory=list)
    bot_level: str | None = None  # -- LAN bots -- a seat the server plays for, at this level (app/game/bot.py); None: a person


def deck_tokens(cards: list[DeckCard], related_tokens: Callable[[str], list[str]] | None = None) -> list[str]:
    """The tokens a deck makes (the Bag of Extras' tokens, private to its owner): its Tokens section, then the tokens its
    cards list (Scryfall's related tokens, ``related_tokens``), each printing once, at most 30."""
    ids = [c.printing_id for c in cards if c.section == "tokens" and c.printing_id]
    if related_tokens is not None:
        for c in cards:
            if c.printing_id and c.section in ("commander", "companion", "main"):
                ids += related_tokens(c.printing_id)
    return list(dict.fromkeys(ids))[:30]


def new_game(
    players: list[PlayerSetup],
    *,
    name: str = "Game",
    format: str = "commander",
    settings: GameSettings | None = None,
    shuffle: bool = True,
    first_player: int | None = None,
    rng: Any = _rng,
    related_tokens: Callable[[str], list[str]] | None = None,
    deck_rows: Callable[[str], dict[str, str]] | None = None,
    planar_pool: Callable[[], list[PlanarCard]] | None = None,
) -> GameState:
    """``deck_rows``: a saved deck's remembered battlefield rows by deck id (-- saved rows --, app/game/placement.py).
    ``planar_pool``: every plane and phenomenon (-- planechase --), when ``settings.planechase`` deals the table a planar deck."""
    if not 1 <= len(players) <= 6:
        raise ValueError("A game needs 1–6 players")
    settings = settings or GameSettings(starting_life=STARTING_LIFE.get(format, 40))
    state_players: dict[str, PlayerState] = {}
    seat_order: list[str] = []
    cards: dict[str, CardInstance] = {}
    zones: dict[str, list[str]] = {}
    collections: dict[str, list[CollectionCard]] = {}
    commander_count = 0

    for index, setup in enumerate(players):
        pid = f"p{index + 1}"
        seat_order.append(pid)
        state_players[pid] = PlayerState(
            id=pid,
            name=setup.name,
            color=setup.color or PLAYER_COLORS[index % len(PLAYER_COLORS)],
            life=settings.starting_life,
            deck_id=setup.deck_id,
            deck_name=setup.deck_name,
            token_shortcuts=deck_tokens(setup.cards, related_tokens),
            row_overrides=placement.saved_rows(deck_rows(setup.deck_id)) if deck_rows is not None and setup.deck_id else {},
            **({"bot": "simple", "bot_level": setup.bot_level} if setup.bot_level else {}),
        )
        from app.game.state import StickerSheet101
        from app.rules import sticker_sheets101

        requested = [c for c in setup.cards if c.section == "stickers"]
        if requested:
            found = [sticker_sheets101.sheet(c.name, c.printing_id) for c in requested]
            # Table starts are advisory, like main/Attraction deck legality. Invalid
            # pools are warned by deck validation; unknown sheets grant no authority.
            unique = {s['id']: s for s in found if s is not None}
            sheets_available101 = list(unique.values())
            state_players[pid].sticker_pool101 = [{k: s[k] for k in ('id', 'name', 'printing_id')} for s in sheets_available101]
            rng.shuffle(sheets_available101)
            state_players[pid].sticker_sheets101 = [StickerSheet101.model_validate(s) for s in sheets_available101[:3]]
        for zone_name in ("library", "hand", "battlefield", "graveyard", "exile", "command", "sideboard", "companion", "foretell", "setaside", "phased", "attractions"):
            zones[zone_key(pid, zone_name)] = []
        for entry in setup.cards:
            zone = SECTION_ZONES.get(entry.section)
            if zone is None:
                continue
            for _ in range(entry.quantity):
                cid = new_id()
                card = CardInstance(
                    id=cid, card_id=entry.printing_id, name=entry.name, owner=pid, controller=pid, zone=zone_key(pid, zone),
                    categories=entry.categories[:10], origin=zone,  # type: ignore[arg-type]
                )
                if entry.section == "commander":
                    commander_count += 1
                    card.commander_key = f"cmd-{pid}-{commander_count}"
                    card.protected = True
                    state_players[pid].commander_tax[card.commander_key] = 0
                cards[cid] = card
                zones[card.zone].append(cid)
        # CR 400.11: keep owned imports outside the game, without inflating card/zone scans.
        # An imported deck's starting cards are already represented on this table.
        available = {c.oracle_id: c.model_copy(deep=True) for c in setup.collection}
        for entry in setup.cards:
            if entry.section in SECTION_ZONES:
                for owned in available.values():
                    if owned.name == entry.name:
                        owned.quantity = max(0, owned.quantity - entry.quantity)
                        break
        collections[pid] = [c for c in available.values() if c.quantity > 0]
        if shuffle:
            rng.shuffle(zones[zone_key(pid, "library")])
            rng.shuffle(zones[zone_key(pid, "attractions")])  # (wave 100L) 103.3a

    first = seat_order[first_player % len(seat_order)] if first_player is not None else seat_order[0]
    state = GameState(
        id=secrets.token_hex(8),
        name=name,
        format=format,  # type: ignore[arg-type]
        created_at=time.time(),
        settings=settings,
        players=state_players,
        seat_order=seat_order,
        cards=cards,
        zones=zones,
        collections=collections,
        turn=TurnState(active_player=first, starting_life={pid: p.life for pid, p in state_players.items()}),
        hidden_salt=secrets.token_hex(16),
    )
    if settings.planechase:  # -- planechase -- the planar deck is dealt with the libraries: part of the game's base state
        from app.game.handlers import planechase

        deck = planechase.deal(planar_pool() if planar_pool is not None else [], settings.planar_deck_size, settings.planar_phenomena, rng)
        state.planechase = Planechase(deck=deck)
        settings.planar_deck_size = len(deck)
        log(state, None, time.time(), [text(f"Planechase: a planar deck of {len(deck)} cards. The table starts on "),
                                       planechase.card_part(deck[0])], kind="planar")
    if settings.mulligan is not None:
        from app.game.handlers import mulligan

        mulligan.begin(state)
    return state
