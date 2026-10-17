"""Shared helpers of the wave 47B scenario tests: the real-Oracle fixture cards (tests/fixtures/wave47b_cards.json, from data/cards.sqlite), a three-player table
and a pinned "random" source."""

from __future__ import annotations

import json
from pathlib import Path

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.wave43b_kit import cast, life, names_in  # noqa: F401  (re-exported for the 47B tests)

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave47b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w47b", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
SUPPORT = ("Jace Beleren", "Lightning Bolt", "Counterspell", "Ugin, the Spirit Dragon", "Hill Giant", "Grizzly Bears", "Shock", "Sol Ring")  # (cards the scenarios need, not under test)
FULL = [c["name"] for c in DATA if c["name"] not in SUPPORT]


def open_cards(settings):
    """The card repository of a scenario (a generator for each module's own ``cards`` fixture): the fixture cards and the real-Oracle ones."""
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build3(cards, mine=(), bobs=(), carols=(), forests=9):
    """Alice (p1, in her main phase), Bob (p2) and Carol (p3): the turn order is p1, p2, p3."""
    def deck_of(commander, spells, lands):
        return deck(cards, commander, [*((1, n) for n in spells), *lands])

    s = GameSession(enable(new_game([
        PlayerSetup("Alice", cards=deck_of("Krenko, Mob Boss", mine, [(forests, "Forest")])),
        PlayerSetup("Bob", cards=deck_of("Atraxa, Praetors' Voice", bobs, [(12, "Island")])),
        PlayerSetup("Carol", cards=deck_of("Atraxa, Praetors' Voice", carols, [(12, "Island")]))], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def pin_random(monkeypatch, index=-1):
    """Every "at random" pick of the table takes the item at ``index`` of what it picks among (a fixed source for the scenario; the engine's own is a
    system source)."""
    from app.game import resolve

    monkeypatch.setattr(resolve._rng, "choice", lambda seq: list(seq)[index])
    monkeypatch.setattr(resolve._rng, "sample", lambda seq, k: list(seq)[index:][:k] if index >= 0 else list(seq)[len(seq) + index:][:k])
