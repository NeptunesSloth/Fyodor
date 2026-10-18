"""Shared helpers of the wave 51G scenario tests: the real-Oracle fixture cards (tests/fixtures/wave51g_cards.json, from data/cards.sqlite) in a test card database."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave51g_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w51g", number=f"X{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def open_repo(settings: Any) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def drive(s: Any, pick: set[str]) -> None:
    """Pass priority, decline blocks and answer every question with the cards named in ``pick`` (none of them: nothing) until combat is over and the stack is empty."""
    for _ in range(60):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack") and s.state.turn.phase in ("end_combat", "main2", "end"):
                return
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            names = {o.id: s.state.cards[o.id].name for o in d.options if o.id in s.state.cards}
            ids = [i for i, n in names.items() if n in pick]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[: max(1, d.min_choices)] if ids else [])
    raise AssertionError("never settled")
