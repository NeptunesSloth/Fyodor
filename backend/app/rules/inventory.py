"""The pod card inventory: which cards our decks actually play, and how automated each one is.

Sources are the host's deck library (Archidekt imports, pasted lists, files) and saved games
(which also cover decks players brought to a LAN lobby without saving them in the library).
Cards are counted by Oracle id, so every printing is one card. The list is ordered by how many
pod decks play a card; that is the order in which cards get scripted (milestone 17).
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.decks.models import DeckEntry
from app.game.state import GameState
from app.rules import coverage

COUNTED_SECTIONS = frozenset({"commander", "companion", "main", "sideboard"})
BASIC_NAMES = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"})


class DeckLike(Protocol):
    name: str
    entries: list[DeckEntry]


@dataclass
class NamedDeck:
    """A deck that isn't in the library (a file or an Archidekt URL given to the inventory tool)."""

    name: str
    entries: list[DeckEntry]


class CardLookup(Protocol):
    def get(self, card_id: str) -> dict[str, Any] | None: ...
    def default_printing_id(self, oracle_id: str) -> str | None: ...
    def resolve(self, name: str) -> dict[str, Any] | None: ...


@dataclass
class InventoryCard:
    oracle_id: str
    name: str
    decks: set[str] = field(default_factory=set)
    copies: int = 0
    games: set[str] = field(default_factory=set)
    coverage: coverage.Coverage | None = None

    def as_dict(self) -> dict[str, Any]:
        cov = self.coverage
        return {
            "oracle_id": self.oracle_id,
            "name": self.name,
            "decks": sorted(self.decks),
            "deck_count": len(self.decks),
            "copies": self.copies,
            "games": len(self.games),
            "basic_land": self.name in BASIC_NAMES,
            "coverage": cov.level if cov else "MANUAL",
            "manual_parts": cov.manual_parts if cov else [],
        }


@dataclass
class Inventory:
    cards: dict[str, InventoryCard] = field(default_factory=dict)
    deck_names: list[str] = field(default_factory=list)
    games: int = 0
    unresolved: dict[str, int] = field(default_factory=dict)  # names not in the card database

    def ordered(self) -> list[InventoryCard]:
        return sorted(self.cards.values(), key=lambda c: (-len(c.decks), -len(c.games), -c.copies, c.name))

    def report(self) -> dict[str, Any]:
        rows = [c.as_dict() for c in self.ordered()]
        summary = {level: sum(1 for r in rows if r["coverage"] == level) for level in ("FULL", "PARTIAL", "MANUAL")}
        # How much of what we actually play is automated, weighted by copies across decks.
        weight = sum(r["copies"] for r in rows) or 1
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "decks": self.deck_names,
            "games": self.games,
            "unique_cards": len(rows),
            "summary": summary,
            "weighted_full": round(sum(r["copies"] for r in rows if r["coverage"] == "FULL") / weight, 3),
            "unresolved": [{"name": n, "copies": q} for n, q in sorted(self.unresolved.items())],
            "supported": {"features": sorted(coverage.SUPPORTED), "keywords": sorted(coverage.SUPPORTED_KEYWORDS)},
            "cards": rows,
        }


def _card_data(lookup: CardLookup, *, oracle_id: str | None, printing_id: str | None, name: str) -> dict[str, Any] | None:
    if printing_id:
        data = lookup.get(printing_id)
        if data:
            return data
    if oracle_id:
        pid = lookup.default_printing_id(oracle_id)
        data = lookup.get(pid) if pid else None
        if data:
            return data
    return lookup.resolve(name)


def build(decks: Iterable[DeckLike], games: Iterable[tuple[str, GameState]], lookup: CardLookup) -> Inventory:
    inv = Inventory()
    data_cache: dict[str, dict[str, Any]] = {}

    def add(data: dict[str, Any]) -> InventoryCard:
        oid = str(data.get("oracle_id") or data["id"])
        entry = inv.cards.get(oid)
        if entry is None:
            entry = inv.cards[oid] = InventoryCard(oracle_id=oid, name=str(data.get("name") or ""))
            entry.coverage = coverage.of_card_data(data)
            data_cache[oid] = data
        return entry

    for deck in decks:
        label = deck.name
        inv.deck_names.append(label)
        for e in deck.entries:
            if e.section not in COUNTED_SECTIONS:
                continue
            data = _card_data(lookup, oracle_id=e.oracle_id, printing_id=e.printing_id, name=e.name)
            if data is None:
                inv.unresolved[e.name] = inv.unresolved.get(e.name, 0) + e.quantity
                continue
            card = add(data)
            card.decks.add(label)
            card.copies += e.quantity
    for game_id, state in games:
        inv.games += 1
        for c in state.cards.values():
            if not c.card_id or c.is_token or c.test_object:
                continue
            data = lookup.get(c.card_id)
            if data is not None:
                add(data).games.add(game_id)
    return inv


def markdown(report: dict[str, Any], *, limit: int = 400) -> str:
    s = report["summary"]
    lines = [
        "# Rules coverage — pod card inventory",
        "",
        f"Generated {report['generated_at']} from {len(report['decks'])} deck(s) and {report['games']} saved game(s).",
        "",
        f"- Unique cards: **{report['unique_cards']}** — FULL {s['FULL']}, PARTIAL {s['PARTIAL']}, MANUAL {s['MANUAL']}",
        f"- Automated share of all copies played (FULL only): **{report['weighted_full'] * 100:.1f}%**",
        f"- Engine features today: {', '.join(report['supported']['features']) or '—'}; "
        f"keywords: {', '.join(report['supported']['keywords']) or '—'}",
        "",
        "Cards are ordered by how many pod decks play them, which is the order they get automated.",
        "",
        "| # | Card | Decks | Copies | Games | Coverage | Manual parts |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(report["cards"][:limit], start=1):
        manual = "; ".join(p.replace("|", "\\|").replace("\n", " ") for p in c["manual_parts"])
        if len(manual) > 160:
            manual = manual[:157] + "…"
        lines.append(f"| {i} | {c['name']} | {c['deck_count']} | {c['copies']} | {c['games']} | {c['coverage']} | {manual} |")
    if len(report["cards"]) > limit:
        lines.append(f"\n…and {len(report['cards']) - limit} more (see the JSON report).")
    if report["unresolved"]:
        lines += ["", "## Not in the card database", ""] + [f"- {u['name']} ×{u['copies']}" for u in report["unresolved"]]
    return "\n".join(lines) + "\n"
