"""Creating a new game from decks."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from app.game.resolve import new_id
from app.game.state import (
    ALL,
    CardInstance,
    GameSettings,
    GameState,
    PlayerState,
    TurnState,
    zone_key,
)

PLAYER_COLORS = ("#d4a852", "#5fa8d3", "#c9677a", "#6fbf8f", "#a68bd6", "#d98c4a")
SECTION_ZONES = {"commander": "command", "companion": "companion", "main": "library", "sideboard": "sideboard"}
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
        for zone_name in ("library", "hand", "battlefield", "graveyard", "exile", "command", "sideboard", "companion", "foretell"):
            zones[zone_key(pid, zone_name)] = []
        for entry in setup.cards:
            zone = SECTION_ZONES.get(entry.section)
            if zone is None:
                continue
            for _ in range(entry.quantity):
                cid = new_id()
                card = CardInstance(
                    id=cid, card_id=entry.printing_id, name=entry.name, owner=pid, controller=pid, zone=zone_key(pid, zone),
                    categories=entry.categories[:10],
                )
                if entry.section == "commander":
                    commander_count += 1
                    card.commander_key = f"cmd-{pid}-{commander_count}"
                    card.known_to = [ALL]
                    card.protected = True
                    state_players[pid].commander_tax[card.commander_key] = 0
                cards[cid] = card
                zones[card.zone].append(cid)
        if shuffle:
            rng.shuffle(zones[zone_key(pid, "library")])

    first = seat_order[first_player % len(seat_order)] if first_player is not None else seat_order[0]
    return GameState(
        id=secrets.token_hex(8),
        name=name,
        format=format,  # type: ignore[arg-type]
        created_at=time.time(),
        settings=settings,
        players=state_players,
        seat_order=seat_order,
        cards=cards,
        zones=zones,
        turn=TurnState(active_player=first),
    )
