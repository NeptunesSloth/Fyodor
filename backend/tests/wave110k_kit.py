"""Wave 110K scenario kit: wave 110J's helpers over tests/fixtures/wave110k_cards.json (real Oracle text copied from the card database)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.wave110j_kit import *  # noqa: F401,F403
from tests.wave110j_kit import act, mana  # noqa: F401

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave110k_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w110k", number=f"K{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def full(name: str) -> bool:
    data = next(c for c in [*EXTRA, *fixture_cards()] if c["name"] == name)
    return coverage.of_card_data({**data, "faces": data.get("card_faces") or []}).level == "FULL"


def cost(name):
    """The card's own mana cost as a pool ({2}{U}{U}: C=2, U=2)."""
    out: dict[str, int] = {}
    for sym in re.findall(r"{([^}]+)}", next(c for c in [*DATA, *fixture_cards()] if c["name"] == name)["mana_cost"] or ""):
        key = "C" if sym.isdigit() else sym.split("/")[0]
        out[key] = out.get(key, 0) + (int(sym) if sym.isdigit() else 1)
    return {k: v for k, v in out.items() if v}


def cast_on(s, name, target=None, pid="p1", **kw):
    """Cast ``name`` from the hand with its own mana cost paid (a card or a player id as target), then resolve."""
    from tests.wave110j_kit import settle, to_hand

    c = to_hand(s, name, pid)
    if cost(name):
        mana(s, pid, **cost(name))
    targets = {} if target is None else {"targets": [target] if isinstance(target, str) else [target.id]}
    act(s, pid, type="cast_spell", card_id=c.id, **targets, **kw)
    settle(s)
    return s.state.cards[c.id]
