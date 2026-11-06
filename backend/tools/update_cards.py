"""Download and import Scryfall card data (and optionally images) for offline play.

Usage (from ``backend/``)::

    python -m tools.update_cards                      # refresh card data if Scryfall has a newer file
    python -m tools.update_cards --images default     # ... then fetch art for each card's default printing
    python -m tools.update_cards --images decks       # only art for cards in saved decks (+ their tokens)
    python -m tools.update_cards --file cards.jsonl.gz  # import a local bulk file (no network)
    python -m tools.update_cards --skip-data --images all  # only images, all printings

Interrupted runs can simply be re-run: partial bulk downloads resume and existing images
are never downloaded twice.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

from app.cards.downloader import (
    DownloadError,
    ImageReport,
    download_file,
    download_images,
    fetch_bulk_info,
    image_jobs_from_rows,
    make_client,
)
from app.cards.images import IMAGE_SIZES, ImageStore
from app.cards.importer import ImportFormatError, import_file
from app.cards.linked import LinkedAssets
from app.config import Settings, load_settings
from app.logging_setup import configure_logging

log = logging.getLogger("update_cards")
BULK_TYPES = ("default_cards", "oracle_cards", "all_cards", "unique_artwork")


def _say(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class _Throttle:
    def __init__(self, every: float = 0.5) -> None:
        self.every, self.last = every, 0.0

    def ready(self) -> bool:
        now = time.monotonic()
        if now - self.last >= self.every:
            self.last = now
            return True
        return False


def _meta(db: Path) -> dict[str, str]:
    if not db.is_file():
        return {}
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        return {k: v for k, v in conn.execute("SELECT key, value FROM meta")}
    except sqlite3.DatabaseError:
        return {}
    finally:
        conn.close()


def update_data(settings: Settings, args: argparse.Namespace) -> None:
    dest = settings.cards_db_path
    if args.file:
        source = Path(args.file).expanduser().resolve()
        if not source.is_file():
            raise SystemExit(f"File not found: {source}")
        meta = {"bulk_type": "local-file", "bulk_updated_at": "", "source": source.name}
    else:
        with make_client(settings.user_agent) as client:
            info = fetch_bulk_info(client, settings.scryfall_api, args.bulk)
            current = _meta(dest)
            if not args.force and current.get("bulk_type") == info.type and current.get("bulk_updated_at") == info.updated_at:
                _say(f"Card data is already current ({info.type}, {info.updated_at}). Use --force to re-import.")
                return
            stamp = "".join(ch for ch in info.updated_at if ch.isdigit())[:14]
            source = settings.downloads_dir / f"{info.type}-{stamp}.jsonl.gz"
            _say(f"Downloading {info.type} ({(info.size or 0) / 1e6:.0f} MB) ...")
            throttle = _Throttle()

            def progress(done: int, total: int | None) -> None:
                if throttle.ready():
                    pct = f"{done * 100 / total:5.1f}%" if total else ""
                    _say(f"  {done / 1e6:7.1f} MB {pct}")

            download_file(client, info.url, source, progress=progress)
            meta = {"bulk_type": info.type, "bulk_updated_at": info.updated_at, "source": source.name}
            for old in settings.downloads_dir.glob(f"{info.type}-*.jsonl.gz"):
                if old != source:
                    old.unlink()

    _say(f"Importing {source.name} ...")
    throttle = _Throttle(1.0)
    started = time.monotonic()

    def import_progress(count: int) -> None:
        if throttle.ready():
            _say(f"  {count:,} printings")

    result = import_file(source, dest, meta=meta, progress=import_progress)
    _say(
        f"Imported {result.printings:,} printings / {result.oracle_cards:,} cards "
        f"({result.tokens:,} tokens) in {time.monotonic() - started:.0f}s -> {dest}"
    )


def update_linked(settings: Settings) -> None:
    """The Magic card back and the mana symbols come with the card data (only what isn't cached; app/cards/linked.py)."""
    got = LinkedAssets(settings, ImageStore(settings.images_dir), lambda: make_client).fetch()
    _say(f"Card back {'cached' if got['card_back'] else 'not available'}; {got['symbols']} mana symbols cached.")


def _image_rows(settings: Settings, scope: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(f"file:{settings.cards_db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cols = "p.id, p.is_token, p.image_uris, p.card_faces, p.all_parts"
    try:
        if scope == "all":
            return conn.execute(f"SELECT {cols} FROM printings p").fetchall()
        if scope == "default":
            return conn.execute(f"SELECT {cols} FROM oracle_defaults d JOIN printings p ON p.id = d.printing_id").fetchall()
        if scope == "commander":  # the default printing of every Commander-legal card (no tokens): the pack for offline play
            return conn.execute(
                f"SELECT {cols} FROM oracle_defaults d JOIN printings p ON p.id = d.printing_id WHERE d.is_token = 0 "
                "AND json_extract(p.legalities, '$.commander') IN ('legal', 'restricted')"
            ).fetchall()
        if scope == "tokens":
            return conn.execute(
                f"SELECT {cols} FROM oracle_defaults d JOIN printings p ON p.id = d.printing_id WHERE d.is_token = 1"
            ).fetchall()
        # decks: printings referenced by saved decks, plus the tokens those cards make
        ids = _deck_printing_ids(settings)
        rows: list[sqlite3.Row] = []
        for start in range(0, len(ids), 500):
            chunk = ids[start : start + 500]
            rows.extend(conn.execute(f"SELECT {cols} FROM printings p WHERE p.id IN ({','.join('?' * len(chunk))})", chunk))
        import json

        token_ids = sorted(
            {part["id"] for r in rows for part in json.loads(r["all_parts"] or "[]") if part.get("component") == "token"}
        )
        for start in range(0, len(token_ids), 500):
            chunk = token_ids[start : start + 500]
            rows.extend(conn.execute(f"SELECT {cols} FROM printings p WHERE p.id IN ({','.join('?' * len(chunk))})", chunk))
        return rows
    finally:
        conn.close()


def _deck_printing_ids(settings: Settings) -> list[str]:
    if not settings.app_db_path.is_file():
        return []
    conn = sqlite3.connect(f"file:{settings.app_db_path.as_posix()}?mode=ro", uri=True)
    try:
        return [r[0] for r in conn.execute("SELECT DISTINCT printing_id FROM deck_cards WHERE printing_id IS NOT NULL")]
    except sqlite3.DatabaseError:
        return []
    finally:
        conn.close()


def update_images(settings: Settings, args: argparse.Namespace) -> ImageReport:
    if not settings.cards_db_path.is_file():
        raise SystemExit("No card database yet; run without --skip-data first.")
    rows = _image_rows(settings, args.images)
    jobs = image_jobs_from_rows(rows)
    store = ImageStore(settings.images_dir)
    _say(f"Checking images for {len(jobs):,} printings (scope: {args.images}, size: {args.size}) ...")
    throttle = _Throttle(1.0)

    def progress(r: ImageReport) -> None:
        if throttle.ready():
            done = r.downloaded + r.skipped + r.failed
            _say(f"  {done:,}/{r.requested:,}  new {r.downloaded:,}  existing {r.skipped:,}  failed {r.failed:,}")

    with make_client(settings.user_agent, timeout=30.0) as client:
        report = download_images(client, store, jobs, size=args.size, workers=args.workers, progress=progress)
    _say(
        f"Images: {report.downloaded:,} downloaded, {report.skipped:,} already present, {report.failed:,} failed "
        f"(of {report.requested:,})."
    )
    for err in report.errors[:5]:
        _say(f"  ! {err}")
    if report.failed:
        _say("Re-run the same command to retry failed images.")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.update_cards", description=__doc__.split("\n\n")[0])
    parser.add_argument("--bulk", choices=BULK_TYPES, default="default_cards", help="Scryfall bulk dataset (default: %(default)s)")
    parser.add_argument("--file", help="import a local Scryfall bulk file instead of downloading")
    parser.add_argument("--force", action="store_true", help="re-import even if the local data is current")
    parser.add_argument("--skip-data", action="store_true", help="do not download/import card data")
    parser.add_argument(
        "--images",
        choices=("none", "decks", "tokens", "commander", "default", "all"),
        default="none",
        help="which card images to cache: none, decks (cards in saved decks), tokens, commander (every Commander-legal card), "
        "default (one printing per card, ~2.5 GB), all (every printing). Default: %(default)s",
    )
    parser.add_argument("--size", choices=IMAGE_SIZES, default="normal", help="image size (default: %(default)s)")
    parser.add_argument("--workers", type=int, default=8, help="parallel image downloads (default: %(default)s)")
    parser.add_argument("--data-dir", help="override FYODOR_DATA_DIR")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = None
    if args.data_dir:
        import os

        env = {**os.environ, "FYODOR_DATA_DIR": args.data_dir}
    settings = load_settings(env)
    configure_logging("WARNING")
    settings.ensure_dirs()
    try:
        if not args.skip_data:
            update_data(settings, args)
            if not args.file:
                update_linked(settings)
        if args.images != "none":
            update_images(settings, args)
        elif not args.skip_data:
            _say("Tip: add `--images decks` or `--images default` to cache card art for offline play.")
    except (DownloadError, ImportFormatError) as exc:
        _say(f"Error: {exc}")
        return 1
    except KeyboardInterrupt:
        _say("Interrupted. Re-run the same command to resume.")
        return 130
    except Exception as exc:  # noqa: BLE001 - top-level CLI reporting; re-raised with context
        if exc.__class__.__module__.startswith("httpx"):
            _say(f"Network error: {exc}. Check your connection and re-run to resume.")
            return 1
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
