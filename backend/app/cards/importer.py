"""Streaming importer for Scryfall bulk card data.

The importer reads a bulk file (gzipped JSONL as currently published by Scryfall, or the
legacy JSON-array format), trims each card object to the fields the tabletop needs, and
writes a brand-new SQLite database next to the live one. When the import succeeds the new
file atomically replaces the old one, so a failed or interrupted import never leaves a
half-written card database behind.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from app.cards.names import normalize_name
from app.cards.schema import CARD_DB_VERSION, SCHEMA

log = logging.getLogger(__name__)

SKIPPED_LAYOUTS = {"art_series", "front_card"}
IMAGE_SIZES = ("small", "normal", "large", "art_crop")
FACE_FIELDS = ("name", "mana_cost", "type_line", "oracle_text", "power", "toughness", "loyalty", "defense", "colors")
# Set types that make a poor *default* printing (still importable and selectable).
UNPREFERRED_SET_TYPES = {"funny", "memorabilia", "promo", "alchemy", "vanguard", "minigame", "treasure_chest", "box"}
UNPREFERRED_SETS = {"plst", "sld", "pw21", "mb2"}
BATCH_SIZE = 2000

ProgressFn = Callable[[int], None]


class ImportFormatError(ValueError):
    """The bulk file could not be parsed."""


@dataclass
class ImportResult:
    printings: int
    oracle_cards: int
    tokens: int
    skipped: int


def _open_text(path: Path) -> TextIO:
    with path.open("rb") as probe:
        magic = probe.read(2)
    if magic == b"\x1f\x8b":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def iter_bulk_file(path: Path) -> Iterator[dict[str, Any]]:
    """Yield card objects from a Scryfall bulk file without loading the whole file."""
    with _open_text(path) as fh:
        first = ""
        while not first:
            chunk = fh.read(1)
            if not chunk:
                return
            if not chunk.isspace():
                first = chunk
        if first == "[":
            yield from _iter_json_array(fh)
        elif first == "{":
            yield from _iter_jsonl(fh, first)
        else:
            raise ImportFormatError(f"{path.name}: expected JSON array or JSONL, found {first!r}")


def _iter_jsonl(fh: TextIO, prefix: str) -> Iterator[dict[str, Any]]:
    for lineno, line in enumerate(_prefixed_lines(fh, prefix), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ImportFormatError(f"line {lineno}: {exc}") from exc
        if isinstance(obj, dict):
            yield obj


def _prefixed_lines(fh: TextIO, prefix: str) -> Iterator[str]:
    first = fh.readline()
    yield prefix + first
    yield from fh


def _iter_json_array(fh: TextIO) -> Iterator[dict[str, Any]]:
    """Scryfall's legacy array files put one object per line; fall back to a full parse otherwise."""
    buffered: list[str] = []
    for raw in fh:
        line = raw.strip().rstrip(",")
        if line in ("", "]"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            buffered.append(raw)
            buffered.extend(fh)
            break
        if isinstance(obj, dict):
            yield obj
    if buffered:
        try:
            data = json.loads("[" + "".join(buffered))
        except json.JSONDecodeError as exc:
            raise ImportFormatError(f"invalid JSON array: {exc}") from exc
        yield from (o for o in data if isinstance(o, dict))


def _pick_images(uris: dict[str, str] | None) -> dict[str, str] | None:
    if not uris:
        return None
    picked = {size: uris[size] for size in IMAGE_SIZES if size in uris}
    return picked or None


def _trim_faces(card: dict[str, Any]) -> list[dict[str, Any]] | None:
    faces = card.get("card_faces")
    if not faces:
        return None
    trimmed = []
    for face in faces:
        entry = {k: face[k] for k in FACE_FIELDS if k in face}
        images = _pick_images(face.get("image_uris"))
        if images:
            entry["image_uris"] = images
        trimmed.append(entry)
    return trimmed


def _trim_parts(card: dict[str, Any]) -> list[dict[str, Any]] | None:
    parts = card.get("all_parts")
    if not parts:
        return None
    return [
        {"id": p.get("id"), "component": p.get("component"), "name": p.get("name"), "type_line": p.get("type_line")}
        for p in parts
    ]


def oracle_id_of(card: dict[str, Any]) -> str:
    oid = card.get("oracle_id")
    if not oid:
        faces = card.get("card_faces") or []
        oid = next((f.get("oracle_id") for f in faces if f.get("oracle_id")), None)
    return str(oid or card["id"])


def is_token_card(card: dict[str, Any]) -> bool:
    return card.get("layout") in {"token", "double_faced_token", "emblem"} or card.get("set_type") == "token"


def default_score(card: dict[str, Any], today: str | None = None) -> tuple[int, ...] | tuple[Any, ...]:
    """Sort key for choosing an oracle card's default printing; higher is better.

    Prefers released, paper, English, regular-frame, in-universe printings from normal sets; the newest
    such printing wins ties.
    """
    today = today or datetime.now(UTC).date().isoformat()
    released = str(card.get("released_at") or "")
    promo_types = set(card.get("promo_types") or ())
    return (
        0 if card.get("digital") else 1,
        0 if released > today else 1,
        0 if card.get("lang", "en") != "en" else 1,
        0 if card.get("set_type") in UNPREFERRED_SET_TYPES or card.get("set") in UNPREFERRED_SETS else 1,
        0 if card.get("promo") or card.get("variation") else 1,
        0 if "universesbeyond" in promo_types or card.get("security_stamp") == "triangle" else 1,
        0 if promo_types & {"boosterfun", "showcase", "extendedart"} or card.get("frame_effects") else 1,
        1 if card.get("border_color") in ("black", "white") and not card.get("full_art") else 0,
        1 if card.get("image_uris") or card.get("card_faces") else 0,
        released,
    )


def card_to_row(card: dict[str, Any]) -> tuple[Any, ...] | None:
    if card.get("object") != "card" or card.get("layout") in SKIPPED_LAYOUTS:
        return None
    faces = card.get("card_faces") or []
    first_face = faces[0] if faces else {}

    def field(name: str) -> Any:
        return card.get(name, first_face.get(name))

    oracle_text = card.get("oracle_text")
    if oracle_text is None and faces:
        oracle_text = "\n//\n".join(f.get("oracle_text", "") for f in faces)
    colors = card.get("colors")
    if colors is None and faces:
        colors = sorted({c for f in faces for c in f.get("colors", [])})
    return (
        card["id"],
        oracle_id_of(card),
        card["name"],
        card.get("lang", "en"),
        card.get("layout", "normal"),
        card.get("set", ""),
        card.get("set_name", ""),
        card.get("set_type", ""),
        card.get("collector_number", ""),
        card.get("released_at"),
        card.get("rarity"),
        card.get("mana_cost") if "mana_cost" in card else " // ".join(f.get("mana_cost", "") for f in faces) or None,
        card.get("cmc"),
        card.get("type_line") or " // ".join(f.get("type_line", "") for f in faces) or None,
        oracle_text,
        field("power"),
        field("toughness"),
        field("loyalty"),
        field("defense"),
        json.dumps(colors or []),
        json.dumps(card.get("color_identity") or []),
        json.dumps(card.get("keywords") or []),
        json.dumps(card["produced_mana"]) if card.get("produced_mana") else None,
        json.dumps(_trim_faces(card)) if faces else None,
        json.dumps(_trim_parts(card)) if card.get("all_parts") else None,
        json.dumps(_pick_images(card.get("image_uris"))) if card.get("image_uris") else None,
        json.dumps(card.get("legalities") or {}),
        1 if is_token_card(card) else 0,
        1 if card.get("digital") else 0,
        1 if card.get("promo") else 0,
        card.get("artist"),
        card.get("edhrec_rank"),
    )


_INSERT_PRINTING = f"INSERT OR REPLACE INTO printings VALUES ({', '.join('?' * 32)})"


def _names_for(card: dict[str, Any]) -> set[str]:
    names = {card["name"]}
    for face in card.get("card_faces") or []:
        if face.get("name"):
            names.add(face["name"])
    for extra in ("flavor_name", "printed_name"):
        if card.get(extra) and card.get("lang", "en") == "en":
            names.add(card[extra])
    return {normalize_name(n) for n in names if n}


def build_database(
    cards: Iterable[dict[str, Any]],
    dest: Path,
    *,
    meta: dict[str, str] | None = None,
    progress: ProgressFn | None = None,
) -> ImportResult:
    """Import ``cards`` into a new database at ``dest`` (replaced atomically on success)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".building")
    for leftover in (tmp, Path(f"{tmp}-wal"), Path(f"{tmp}-shm")):
        leftover.unlink(missing_ok=True)

    conn = sqlite3.connect(tmp)
    try:
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.executescript(SCHEMA)
        result = _load(conn, cards, progress)
        _finalize(conn, meta or {}, result)
        conn.commit()
    except BaseException:
        conn.close()
        tmp.unlink(missing_ok=True)
        raise
    conn.close()
    os.replace(tmp, dest)
    for stale in (Path(f"{dest}-wal"), Path(f"{dest}-shm")):
        stale.unlink(missing_ok=True)
    log.info("Card database ready: %s", result)
    return result


def _load(conn: sqlite3.Connection, cards: Iterable[dict[str, Any]], progress: ProgressFn | None) -> ImportResult:
    best: dict[str, tuple[tuple[Any, ...], str, str, int]] = {}
    today = datetime.now(UTC).date().isoformat()
    batch: list[tuple[Any, ...]] = []
    names: list[tuple[str, str, int]] = []
    count = skipped = 0
    conn.execute("BEGIN")
    for card in cards:
        try:
            row = card_to_row(card)
        except (KeyError, TypeError) as exc:
            log.warning("Skipping malformed card %s: %s", card.get("id"), exc)
            row = None
        if row is None:
            skipped += 1
            continue
        batch.append(row)
        oracle_id, is_token = row[1], row[27]
        names.extend((n, oracle_id, is_token) for n in _names_for(card))
        score = default_score(card, today)
        current = best.get(oracle_id)
        if current is None or score > current[0]:
            best[oracle_id] = (score, card["id"], card["name"], is_token)
        count += 1
        if len(batch) >= BATCH_SIZE:
            _flush(conn, batch, names)
            if progress:
                progress(count)
    _flush(conn, batch, names)
    if progress:
        progress(count)
    conn.executemany(
        "INSERT INTO oracle_defaults VALUES (?, ?, ?, ?)",
        ((oid, pid, name, tok) for oid, (_, pid, name, tok) in best.items()),
    )
    tokens = sum(1 for v in best.values() if v[3])
    return ImportResult(printings=count, oracle_cards=len(best), tokens=tokens, skipped=skipped)


def _flush(conn: sqlite3.Connection, batch: list[tuple[Any, ...]], names: list[tuple[str, str, int]]) -> None:
    if batch:
        conn.executemany(_INSERT_PRINTING, batch)
        batch.clear()
    if names:
        conn.executemany("INSERT OR IGNORE INTO card_names VALUES (?, ?, ?)", names)
        names.clear()


def _finalize(conn: sqlite3.Connection, meta: dict[str, str], result: ImportResult) -> None:
    conn.execute(
        """
        INSERT INTO oracle_fts (rowid, name, type_line, oracle_text)
        SELECT p.rowid, p.name, coalesce(p.type_line, ''), coalesce(p.oracle_text, '')
        FROM oracle_defaults d JOIN printings p ON p.id = d.printing_id
        """
    )
    values = {
        **meta,
        "schema_version": str(CARD_DB_VERSION),
        "imported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "printings": str(result.printings),
        "oracle_cards": str(result.oracle_cards),
        "tokens": str(result.tokens),
    }
    conn.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)", values.items())


def import_file(path: Path, dest: Path, *, meta: dict[str, str] | None = None, progress: ProgressFn | None = None) -> ImportResult:
    return build_database(iter_bulk_file(path), dest, meta=meta, progress=progress)


def write_jsonl_gz(cards: Iterable[dict[str, Any]], path: Path) -> None:
    """Helper for tests and fixtures: write card objects as gzipped JSONL."""
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for card in cards:
            fh.write(json.dumps(card) + "\n")
