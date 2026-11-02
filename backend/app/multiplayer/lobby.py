"""Pregame lobby: seats, self-service deck submission, readiness and table settings.

Each player chooses their own deck. The client submits a deck *definition* (text,
Archidekt URL/JSON, or the id of a deck already stored on the host); the host parses and
resolves it against its own card database. Clients never name files or paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.game.factory import DeckCard
from app.game.mulligan import PRESETS, resolve_policy
from app.game.rules_state import AutomationLevel
from app.game.state import CollectionCard, MulliganPolicy
from app.textutil import clean_text

DeckPrivacy = Literal["private", "commander_only", "public"]
PriorityHelper = Literal["off", "simple"]

MAX_DECK_ENTRIES = 400
MAX_DECK_CARDS = 600
MAX_COMMANDERS = 4


class LobbySettings(BaseModel):
    name: str = Field(default="Game", max_length=80)
    format: Literal["commander"] = "commander"
    seats: int = Field(default=4, ge=1, le=6)
    starting_life: int | None = Field(default=None, ge=1, le=10000)
    deck_privacy: DeckPrivacy = "commander_only"
    mulligan_rule: str = Field(default="commander_london", max_length=40)
    mulligan_policy: MulliganPolicy | None = None  # the host's definition for Boston (Custom Pod) / Custom
    priority_helper: PriorityHelper = "simple"
    auto_untap: bool = True
    automation: AutomationLevel = "off"  # rules automation (docs/AUTOMATION_UX.md); OFF by default
    # "pod": d20 for game 1 and after a draw, then the previous winner goes last (GAME_NIGHT_FLOW.md §2).
    # The app asks for it when it creates a lobby; the API default keeps seats in join order.
    turn_order: Literal["pod", "random"] = "random"

    @field_validator("name")
    @classmethod
    def _clean(cls, v: str) -> str:
        return clean_text(v, 80) or "Game"

    @field_validator("mulligan_rule")
    @classmethod
    def _known_rule(cls, v: str) -> str:
        if v != "none" and v not in PRESETS:
            raise ValueError(f"unknown mulligan rule {v!r}")
        return v

    def policy(self) -> MulliganPolicy | None:
        return resolve_policy(self.mulligan_rule, self.mulligan_policy)


class DeckTooLarge(ValueError):
    pass


@dataclass
class SubmittedDeck:
    """A validated, resolved deck a player brought to the table."""

    name: str
    cards: list[DeckCard]
    commanders: list[str]
    color_identity: list[str]
    card_count: int
    format: str | None = None
    report: dict[str, Any] = field(default_factory=dict)
    source_kind: str = "text"
    warnings: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # table format -> advisory warnings
    # How much of the deck the rules engine automates: card counts per coverage level.
    coverage: dict[str, int] = field(default_factory=dict)
    collection: list[CollectionCard] = field(default_factory=list)
    offline: dict[str, Any] = field(default_factory=dict)
    commander_ids: list[str] = field(default_factory=list)  # printings, for the seat card's art

    def entries_public(self) -> list[dict[str, Any]]:
        return [
            {"section": c.section, "quantity": c.quantity, "name": c.name}
            for c in self.cards
            if c.section != "maybeboard"
        ]


def check_bounds(cards: list[DeckCard]) -> None:
    if len(cards) > MAX_DECK_ENTRIES:
        raise DeckTooLarge(f"Too many different cards ({len(cards)}; max {MAX_DECK_ENTRIES})")
    total = sum(c.quantity for c in cards if c.section != "maybeboard")
    if total > MAX_DECK_CARDS:
        raise DeckTooLarge(f"Too many cards ({total}; max {MAX_DECK_CARDS})")
    commanders = sum(c.quantity for c in cards if c.section == "commander")
    if commanders > MAX_COMMANDERS:
        raise DeckTooLarge(f"Too many commanders ({commanders}; max {MAX_COMMANDERS})")


@dataclass
class LobbySeatInfo:
    name: str = ""
    color: str | None = None
    deck: SubmittedDeck | None = None
    ready: bool = False
    collection: list[CollectionCard] = field(default_factory=list)
    last_fetch: float = -1e9  # monotonic time of the last Archidekt fetch (rate limit)
    queued: SubmittedDeck | None = None  # (spectator activities) the deck queued while out of the last game, as put here


def deck_summary(deck: SubmittedDeck | None, *, privacy: DeckPrivacy, own: bool, table_format: str = "commander") -> dict[str, Any] | None:
    """What a viewer may learn about a seat's deck before the game."""
    if deck is None:
        return None
    summary: dict[str, Any] = {"card_count": deck.card_count}
    if own or privacy in ("commander_only", "public"):
        summary.update(name=deck.name, commanders=deck.commanders, color_identity=deck.color_identity,
                       commander_ids=deck.commander_ids)
        # Automation coverage is counts only (FULL / PARTIAL / REVIEW / MANUAL), never card names.
        if deck.coverage:
            summary["coverage"] = deck.coverage
    if own or privacy == "public":
        summary["list"] = deck.entries_public()
    if own:
        summary["report"] = deck.report
        summary["offline"] = deck.offline
    # Deck checks are advisory ("Play anyway"). Their text names cards, so only the owner (or
    # everyone, with a public list) reads it; with commander-only privacy the others just see how
    # many there are, and with a private deck nothing at all.
    warnings = deck.warnings.get(table_format, [])
    if own or privacy != "private":
        summary["warning_count"] = sum(1 for w in warnings if w["level"] != "info")
    if own or privacy == "public":
        summary["warnings"] = warnings
    return summary
