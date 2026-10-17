"""Shared helpers of the wave 45C scenario tests (real Oracle text of tests/fixtures/wave45c_cards.json, from data/cards.sqlite)."""

from __future__ import annotations

import json
from pathlib import Path

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import sba
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import card_named

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave45c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w45c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def make_repo(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))


def zone(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].zone


def ability(s, c, needle):
    ch = Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id])
    return next(a.index for a in ch.abilities if needle in a.text)


def pt_of(s, name, pid="p1"):
    c = s.state.cards[card_named(s, name, pid).id]
    ch = Plan(s.state, "p1", s.cards, None).ch(c)
    return sba.power(c, ch), sba.toughness(c, ch)


def treasures(s, pid="p1"):
    return sum(1 for c in s.state.cards.values() if c.name == "Treasure" and c.zone == f"{pid}:battlefield")


def hold(s):
    """Both players stop at every object on the stack, and Alice keeps priority after casting (so spells pile up)."""
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"
    act(s, "p1", type="set_prefs", hold_priority=True)
