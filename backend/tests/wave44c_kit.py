"""Shared helpers of the wave 44C scenario tests: the real-Oracle fixture cards (tests/fixtures/wave44c_cards.json, from data/cards.sqlite) and small table helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import card_named

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave44c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w44c", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def open_cards(settings):
    """The card repository of a scenario (a generator for each module's own ``cards`` fixture): the fixture cards and the real-Oracle ones."""
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def ch(s, c):
    """The characteristics of this card now (what a rules question about it reads)."""
    return Plan.view(s.state, "p1", s.cards).ch(s.state.cards[c.id])


def on_top(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return c


def life(s, pid="p1"):
    return s.state.players[pid].life
