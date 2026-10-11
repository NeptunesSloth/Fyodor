"""Shared helpers of the wave 35C scenario tests: the real-Oracle fixture cards (tests/fixtures/wave35c_cards.json, from data/cards.sqlite) and a table with
Alice and Bob (tests/wave9c_kit.py)."""

from __future__ import annotations

import json
from pathlib import Path

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.wave9c_kit import mana, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave35c_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w35c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def repository(settings):
    """The card repository of a test (each test module wraps it in its own ``cards`` fixture)."""
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def pool(s, pid="p1"):
    return dict(s.state.players[pid].mana)


def bolt(s, target, pid="p1"):
    """``pid`` casts a Lightning Bolt (3 damage) at ``target`` and it resolves."""
    mana(s, pid, R=1)
    act(s, pid, type="cast_spell", card_id=to_hand(s, "Lightning Bolt", pid).id, targets=[target])
    settle(s)


def alive(s, pid="p1"):
    from app.rules.plan import live_players

    return pid in live_players(s.state)


def cast_from_hand(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=to_hand(s, name, pid).id, **kw)
    settle(s)
