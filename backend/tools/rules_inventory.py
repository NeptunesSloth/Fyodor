"""Pod card inventory: which cards our decks play, and how much of each the rules engine automates.

Run on the host computer (from ``backend/``)::

    python -m tools.rules_inventory                       # the deck library + saved games
    python -m tools.rules_inventory --deck-file my.txt    # plus deck lists from files
    python -m tools.rules_inventory --archidekt https://archidekt.com/decks/123456/...  # plus Archidekt decks (online)

It writes ``<data dir>/reports/rules_inventory.json`` and ``.md``. Cards are ordered by how many
pod decks play them, which is the order they get automated. Nothing is uploaded anywhere;
``--archidekt`` only downloads the public deck you name.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

from app.cards.images import ImageStore
from app.cards.repository import CardRepository
from app.config import load_settings
from app.decks import archidekt
from app.decks import service as deck_service
from app.decks.models import DeckImportRequest
from app.decks.repository import DeckRepository
from app.rules import inventory
from app.storage.app_db import open_app_db
from app.storage.saves import SaveRepository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rules_inventory", description=__doc__.split("\n\n")[0])
    parser.add_argument("--data-dir", help="override FYODOR_DATA_DIR")
    parser.add_argument("--deck-file", action="append", default=[], help="a deck list file to include (repeatable)")
    parser.add_argument("--archidekt", action="append", default=[], help="an Archidekt deck URL to include (repeatable)")
    parser.add_argument("--no-library", action="store_true", help="skip the deck library and saved games")
    parser.add_argument("--out", help="output folder (default: <data dir>/reports)")
    args = parser.parse_args(argv)

    env = {"FYODOR_DATA_DIR": args.data_dir} if args.data_dir else None
    settings = load_settings({**__import__("os").environ, **(env or {})})
    cards = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    if not cards.available:
        print("No card database yet: run `python -m tools.update_cards` first.", file=sys.stderr)
        return 1

    decks: list[inventory.DeckLike] = []
    games = []
    if not args.no_library:
        conn = open_app_db(settings.app_db_path)
        lock = threading.RLock()
        decks.extend(DeckRepository(conn, lock).list_all())
        saves = SaveRepository(conn, lock)
        seen: set[str] = set()
        for save in saves.list_all():
            if save["game_id"] in seen:
                continue
            seen.add(save["game_id"])
            try:
                state, _ = saves.load(save["id"], history_limit=1)
            except Exception as exc:  # noqa: BLE001 - report and carry on
                print(f"Skipping unreadable save {save['name']}: {exc}", file=sys.stderr)
                continue
            games.append((save["game_id"], state))
    for path in args.deck_file:
        text = Path(path).read_text(encoding="utf-8")
        result = deck_service.import_any(DeckImportRequest(text=text), cards)
        decks.append(inventory.NamedDeck(name=result.parsed.name or Path(path).stem, entries=result.entries))
    for url in args.archidekt:
        result = deck_service.import_any(
            DeckImportRequest(archidekt=url), cards,
            fetch=lambda deck_id: archidekt.fetch_deck(deck_id, user_agent=settings.user_agent),
        )
        decks.append(inventory.NamedDeck(name=result.parsed.name or url, entries=result.entries))

    report = inventory.build(decks, games, cards).report()
    out = Path(args.out) if args.out else settings.data_dir / "reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / "rules_inventory.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "rules_inventory.md").write_text(inventory.markdown(report), encoding="utf-8")
    s = report["summary"]
    print(f"{len(report['decks'])} decks, {report['games']} saved games, {report['unique_cards']} unique cards: "
          f"FULL {s['FULL']}, PARTIAL {s['PARTIAL']}, MANUAL {s['MANUAL']}")
    print(f"Wrote {out / 'rules_inventory.md'} and .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
