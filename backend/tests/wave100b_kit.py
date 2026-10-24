"""Shared helpers of the wave 100B scenario tests: the real-Oracle fixture cards (tests/fixtures/wave100b_cards.json, from data/cards.sqlite)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave100b_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w100b", number=f"B{i:03d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def open_repo(settings: Any) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def run(s: Any, pick: Callable[[Any], list[str] | None] | None = None, limit: int = 80) -> None:
    """Resolve the stack. ``pick(decision)``: the option ids to answer (None: "yes" for a yes/no, else the first options)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = pick(d) if pick is not None else None
            if ids is None:
                opts = [o.id for o in d.options]
                ids = ["yes"] if "yes" in opts else opts[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def zone(s: Any, c: Any) -> str:
    return str(s.state.cards[c.id].zone)


def hand_size(s: Any, pid: str) -> int:
    return len(s.state.zones.get(f"{pid}:hand", []))


def tokens(s: Any, pid: str, name: str) -> list[Any]:
    return [c for c in s.state.cards.values() if c.zone == f"{pid}:battlefield" and c.name == name]
