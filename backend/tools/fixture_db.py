"""Build a small, deterministic card database from the test fixtures (no network).

Used by the browser end-to-end tests and CI so they never depend on Scryfall:

    python -m tools.fixture_db [path/to/cards.sqlite]
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.cards.importer import build_database
from app.config import get_settings
from tests.fixtures.cards import fixture_cards


def main(argv: list[str]) -> int:
    target = Path(argv[0]) if argv else get_settings().cards_db_path
    target.parent.mkdir(parents=True, exist_ok=True)
    build_database(fixture_cards(), target, meta={"bulk_type": "fixture"})
    print(f"Fixture card database written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
