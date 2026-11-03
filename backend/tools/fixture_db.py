"""Build a small, deterministic card database from the test fixtures (no network).

Used by the browser end-to-end tests and CI so they never depend on Scryfall:

    python -m tools.fixture_db [path/to/cards.sqlite] [--newer]

``--newer`` adds a card from a set newer than the fixtures (a friend's newer card database, docs/LAN_PLAY.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.cards.importer import build_database
from app.config import get_settings
from tests.fixtures.cards import fixture_cards, newer_set_card


def main(argv: list[str]) -> int:
    newer = "--newer" in argv
    paths = [a for a in argv if a != "--newer"]
    target = Path(paths[0]) if paths else get_settings().cards_db_path
    target.parent.mkdir(parents=True, exist_ok=True)
    build_database([*fixture_cards(), *([newer_set_card()] if newer else [])], target, meta={"bulk_type": "fixture"})
    print(f"Fixture card database written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
