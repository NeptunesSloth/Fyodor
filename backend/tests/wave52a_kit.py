"""Shared helpers of the wave 52A scenario tests: the real-Oracle fixture cards (tests/fixtures/wave52a_cards.json, from data/cards.sqlite) in a test card database."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from tests.fixtures.cards import card, fixture_cards

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave52a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w52a", number=f"X{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


def open_repo(settings: Any) -> Iterator[CardRepository]:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def build_n(cards: Any, mine: Any = (), theirs: Any = (), forests: int = 9, islands: int = 10) -> Any:
    """Like ``wave9c_kit.build`` but an entry may be ``(copies, name)``."""
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import act, deck, enable

    def entries(names: Any) -> list[tuple[int, str]]:
        return [n if isinstance(n, tuple) else (1, n) for n in names]

    alice = deck(cards, "Krenko, Mob Boss", [*entries(mine), (forests, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [*entries(theirs), (islands, "Island")])
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def put_all(s: Any, name: str, pid: str = "p1") -> list[Any]:
    """Every copy of ``name`` of ``pid`` still in the library or hand, put onto the battlefield."""
    from tests.game_helpers import act

    out = [c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith("battlefield")]
    for c in out:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return out
