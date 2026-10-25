"""Creating a new game from decks."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from app.game.resolve import new_id
from app.game.state import (
    CardInstance,
    CollectionCard,
    GameSettings,
    GameState,
    PlayerState,
    TurnState,
    zone_key,
)

PLAYER_COLORS = ("#d4a852", "#5fa8d3", "#c9677a", "#6fbf8f", "#a68bd6", "#d98c4a")
SECTION_ZONES = {"commander": "command", "companion": "companion", "main": "library", "sideboard": "sideboard",
                 "attractions": "attractions"}  # -- Attractions (wave 100L) -- 717.2: the supplementary Attraction deck
STARTING_LIFE = {"commander": 40, "constructed": 20, "sandbox": 20}
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


def new_game(
    players: list[PlayerSetup],
    *,
    name: str = "Game",
    format: str = "commander",
    settings: GameSettings | None = None,
    shuffle: bool = True,
    first_player: int | None = None,
    rng: Any = _rng,
) -> GameState:
    if not 1 <= len(players) <= 6:
        raise ValueError("A game needs 1–6 players")
    settings = settings or GameSettings(starting_life=STARTING_LIFE.get(format, 20))
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
            token_shortcuts=[c.printing_id for c in setup.cards if c.section == "tokens" and c.printing_id][:30],
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
    if settings.mulligan is not None:
        from app.game.handlers import mulligan

        mulligan.begin(state)
    return state
