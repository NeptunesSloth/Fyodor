"""UPDATE CARD DATABASE from inside Fyodor (host computer only), like a Tabletop Simulator workshop "update available".

``check`` asks Scryfall which bulk file is current (one small request) and compares it with the local database.
``update`` downloads it (resuming a partial download), builds the new database next to the live one and swaps it in
with ``CardRepository.replace_with``: tables keep playing and read the new file on their next lookup. Nothing here
runs unless the host asks, and never with FYODOR_ALLOW_NETWORK=0. The command-line ``tools.update_cards`` does the same.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol

from app.cards.downloader import download_file, fetch_bulk_info, make_client
from app.cards.importer import import_file
from app.cards.repository import CardRepository
from app.config import Settings

log = logging.getLogger(__name__)

BULK_TYPES = ("default_cards", "oracle_cards", "all_cards", "unique_artwork")
DEFAULT_BULK = "default_cards"


class Progress(Protocol):
    def __call__(self, done: int, total: int, failed: int, phase: str | None = None) -> None: ...


def bulk_type_for(current: dict[str, Any]) -> str:
    """Keep the kind of data the host already has (all printings, one per card …); a first download gets every printing."""
    kind = current.get("bulk_type")
    return kind if kind in BULK_TYPES else DEFAULT_BULK


def check(settings: Settings, cards: CardRepository, client_factory: Callable[..., Any] = make_client) -> dict[str, Any]:
    current = cards.stats()
    with client_factory(settings.user_agent, timeout=20.0) as client:
        info = fetch_bulk_info(client, settings.scryfall_api, bulk_type_for(current))
    available = not current["available"] or current["bulk_type"] != info.type or current["bulk_updated_at"] != info.updated_at
    return {"available": available, "bulk_type": info.type, "remote_updated_at": info.updated_at, "size": info.size,
            "current": current}


def update(settings: Settings, cards: CardRepository, progress: Progress, *, force: bool = False,
           client_factory: Callable[..., Any] = make_client) -> str:
    before = cards.stats()
    with client_factory(settings.user_agent) as client:
        progress(0, 0, 0, "Asking Scryfall")
        info = fetch_bulk_info(client, settings.scryfall_api, bulk_type_for(before))
        if not force and before["available"] and before["bulk_type"] == info.type and before["bulk_updated_at"] == info.updated_at:
            return "Card data is already current."
        stamp = "".join(ch for ch in info.updated_at if ch.isdigit())[:14]
        source = settings.downloads_dir / f"{info.type}-{stamp}.jsonl.gz"
        download_file(client, info.url, source, progress=lambda done, total: progress(done, total or info.size or 0, 0, "Downloading"))
    staging = settings.cards_db_path.with_name(settings.cards_db_path.name + ".update")
    estimate = int(before.get("printings") or 0)
    result = import_file(source, staging, meta={"bulk_type": info.type, "bulk_updated_at": info.updated_at, "source": source.name},
                         progress=lambda count: progress(count, max(estimate, count), 0, "Importing"))
    progress(result.printings, result.printings, 0, "Switching over")
    cards.replace_with(staging)
    for old in settings.downloads_dir.glob(f"{info.type}-*.jsonl.gz"):
        if old != source:
            old.unlink(missing_ok=True)
    gained = result.oracle_cards - int(before.get("oracle_cards") or 0)
    news = f" ({gained:,} new card{'s' if gained != 1 else ''})" if before["available"] and gained > 0 else ""
    log.info("Card database updated to %s %s: %s", info.type, info.updated_at, result)
    return f"Updated: {result.oracle_cards:,} cards and {result.printings:,} printings{news}."
