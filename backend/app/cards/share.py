"""Card records one Fyodor hands another over the LAN (docs/LAN_PLAY.md, "Finding a game").

A friend's card database can be newer than the host's (a set released since the host last updated). When they bring their
decks, their server sends the cards the host lacks as **Scryfall-shaped** card objects (``records``), never raw database rows,
so a difference between the two versions' databases can't corrupt either. The host checks each one field by field
(``clean_card``) and only **adds** cards it doesn't have (``add_cards``): a printing it already knows is never touched, and a
new printing of a card it knows must carry that card's name. The next card-database update replaces them anyway.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.cards.images import UUID_RE
from app.cards.importer import _INSERT_PRINTING, _names_for, card_to_row
from app.cards.names import normalize_name

if TYPE_CHECKING:
    from app.cards.repository import CardRepository

MAX_RECORD = 16_000  # bytes of one card object
COLORS = {"W", "U", "B", "R", "G", "C"}
_IMAGE_HOST = re.compile(r"^https://(cards|backs)\.scryfall\.io/[A-Za-z0-9_./-]{1,200}(\?[0-9]{1,12})?$")
_TEXT = {  # field: longest text accepted
    "name": 200, "lang": 8, "layout": 32, "set": 10, "set_name": 120, "set_type": 32, "collector_number": 12, "released_at": 10,
    "rarity": 16, "mana_cost": 120, "type_line": 200, "oracle_text": 5000, "power": 8, "toughness": 8, "loyalty": 8, "defense": 8,
    "artist": 200,
}
_REQUIRED = ("name", "set", "collector_number", "layout")
_FACE_TEXT = {"name": 200, "mana_cost": 120, "type_line": 200, "oracle_text": 5000, "power": 8, "toughness": 8, "loyalty": 8, "defense": 8}


def _images(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    kept = {k: v for k, v in raw.items() if k in ("small", "normal", "large", "art_crop") and isinstance(v, str) and _IMAGE_HOST.match(v)}
    return kept or None


def _str_list(raw: Any, allowed: set[str] | None = None, *, size: int = 40, most: int = 40) -> list[str] | None:
    if not isinstance(raw, list) or len(raw) > most or not all(isinstance(x, str) and len(x) <= size for x in raw):
        return None
    if allowed is not None and not set(raw) <= allowed:
        return None
    return list(raw)


def clean_card(raw: Any) -> dict[str, Any] | None:
    """The card object with only the fields Fyodor reads, each of the right type and size; None when it can't be used."""
    if not isinstance(raw, dict) or raw.get("object") != "card":
        return None
    try:
        if len(json.dumps(raw)) > MAX_RECORD:
            return None
    except (TypeError, ValueError):
        return None
    cid, oid = raw.get("id"), raw.get("oracle_id")
    if not (isinstance(cid, str) and UUID_RE.match(cid) and isinstance(oid, str) and UUID_RE.match(oid)):
        return None
    card: dict[str, Any] = {"object": "card", "id": cid, "oracle_id": oid}
    for key, size in _TEXT.items():
        value = raw.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or len(value) > size:
            return None
        card[key] = value
    if any(not card.get(k) for k in _REQUIRED):
        return None
    cmc = raw.get("cmc")
    if cmc is not None:
        if isinstance(cmc, bool) or not isinstance(cmc, (int, float)) or not 0 <= cmc <= 1_000_000:
            return None
        card["cmc"] = float(cmc)
    for key, allowed in (("colors", COLORS), ("color_identity", COLORS), ("produced_mana", COLORS), ("keywords", None)):
        if raw.get(key) is None:
            continue
        values = _str_list(raw[key], allowed)
        if values is None:
            return None
        card[key] = values
    legal = raw.get("legalities")
    if legal is not None:
        if not isinstance(legal, dict) or not all(isinstance(k, str) and isinstance(v, str) and len(k) < 32 and len(v) < 32 for k, v in legal.items()):
            return None
        card["legalities"] = dict(legal)
    for key in ("digital", "promo"):
        if isinstance(raw.get(key), bool):
            card[key] = raw[key]
    if isinstance(raw.get("edhrec_rank"), int) and not isinstance(raw["edhrec_rank"], bool):
        card["edhrec_rank"] = raw["edhrec_rank"]
    if (images := _images(raw.get("image_uris"))) is not None:
        card["image_uris"] = images
    faces = raw.get("card_faces")
    if faces is not None:
        if not isinstance(faces, list) or not 1 <= len(faces) <= 4:
            return None
        clean_faces = []
        for face in faces:
            if not isinstance(face, dict):
                return None
            f: dict[str, Any] = {}
            for key, size in _FACE_TEXT.items():
                value = face.get(key)
                if value is None:
                    continue
                if not isinstance(value, str) or len(value) > size:
                    return None
                f[key] = value
            if face.get("colors") is not None:
                if (colors := _str_list(face["colors"], COLORS)) is None:
                    return None
                f["colors"] = colors
            if (images := _images(face.get("image_uris"))) is not None:
                f["image_uris"] = images
            clean_faces.append(f)
        card["card_faces"] = clean_faces
    parts = raw.get("all_parts")
    if parts is not None:
        if not isinstance(parts, list) or len(parts) > 40:
            return None
        card["all_parts"] = [
            {"id": p["id"], "component": str(p.get("component") or "")[:32], "name": str(p.get("name") or "")[:200],
             "type_line": str(p.get("type_line") or "")[:200]}
            for p in parts if isinstance(p, dict) and isinstance(p.get("id"), str) and UUID_RE.match(p["id"])
        ]
    return card


def _shape(row: sqlite3.Row) -> dict[str, Any]:
    """A printings row as the Scryfall card object it was imported from (the fields Fyodor keeps)."""
    card: dict[str, Any] = {
        "object": "card", "id": row["id"], "oracle_id": row["oracle_id"], "name": row["name"], "lang": row["lang"],
        "layout": row["layout"], "set": row["set_code"], "set_name": row["set_name"], "set_type": row["set_type"],
        "collector_number": row["collector_number"], "released_at": row["released_at"], "rarity": row["rarity"],
        "mana_cost": row["mana_cost"], "cmc": row["cmc"], "type_line": row["type_line"], "oracle_text": row["oracle_text"],
        "power": row["power"], "toughness": row["toughness"], "loyalty": row["loyalty"], "defense": row["defense"],
        "colors": json.loads(row["colors"] or "[]"), "color_identity": json.loads(row["color_identity"] or "[]"),
        "keywords": json.loads(row["keywords"] or "[]"), "legalities": json.loads(row["legalities"] or "{}"),
        "digital": bool(row["digital"]), "promo": bool(row["promo"]), "artist": row["artist"], "edhrec_rank": row["edhrec_rank"],
    }
    for key, column in (("produced_mana", "produced_mana"), ("card_faces", "card_faces"), ("all_parts", "all_parts"),
                        ("image_uris", "image_uris")):
        if row[column]:
            card[key] = json.loads(row[column])
    return {k: v for k, v in card.items() if v is not None}


def records(repo: CardRepository, printing_ids: list[str]) -> list[dict[str, Any]]:
    """These printings as Scryfall card objects (the ones this database has)."""
    out: list[dict[str, Any]] = []
    unique = [i for i in dict.fromkeys(printing_ids) if isinstance(i, str) and UUID_RE.match(i)]
    for start in range(0, len(unique), 500):
        chunk = unique[start : start + 500]
        rows = repo._query(f"SELECT * FROM printings WHERE id IN ({','.join('?' * len(chunk))})", chunk)
        out += [_shape(r) for r in rows]
    return out


def unknown_ids(repo: CardRepository, printing_ids: list[str]) -> list[str]:
    """The printings this database doesn't have."""
    unique = [i for i in dict.fromkeys(printing_ids) if isinstance(i, str) and UUID_RE.match(i)]
    known: set[str] = set()
    for start in range(0, len(unique), 500):
        chunk = unique[start : start + 500]
        known |= {r["id"] for r in repo._query(f"SELECT id FROM printings WHERE id IN ({','.join('?' * len(chunk))})", chunk)}
    return [i for i in unique if i not in known]


@dataclass
class AddResult:
    added: list[str] = field(default_factory=list)  # names
    rejected: list[dict[str, str]] = field(default_factory=list)  # {name, why}


def add_cards(repo: CardRepository, cards: list[Any], *, source: str | None = None) -> AddResult:
    """Add the cards this database lacks. Never changes a printing it has; a new printing of a known card must carry its name."""
    result = AddResult()
    unreadable = f"its card data from {source} couldn't be read" if source else "its card data couldn't be read"
    with repo._lock:
        try:
            repo._connection()  # the database must exist
        except Exception:  # noqa: BLE001 - no card database at all: nothing can be added
            for raw in cards:
                name = raw.get("name") if isinstance(raw, dict) else None
                result.rejected.append({"name": str(name or "a card")[:200], "why": "this computer has no card database yet"})
            return result
        conn = sqlite3.connect(repo.db_path)
        try:
            conn.execute("BEGIN")
            for raw in cards:
                name = str(raw.get("name") or "a card")[:200] if isinstance(raw, dict) else "a card"
                card = clean_card(raw)
                row = None
                if card is not None:
                    try:
                        row = card_to_row(card)
                    except (KeyError, TypeError, ValueError):
                        row = None
                if card is None or row is None:
                    result.rejected.append({"name": name, "why": unreadable})
                    continue
                if conn.execute("SELECT 1 FROM printings WHERE id = ?", (card["id"],)).fetchone():
                    continue  # already here: never overwritten
                known = conn.execute("SELECT name FROM oracle_defaults WHERE oracle_id = ?", (card["oracle_id"],)).fetchone()
                if known and normalize_name(known[0]) != normalize_name(card["name"]):
                    result.rejected.append({"name": name, "why": f"it doesn't match the card this computer knows as {known[0]}"})
                    continue
                conn.execute(_INSERT_PRINTING.replace("INSERT OR REPLACE", "INSERT OR IGNORE"), row)
                is_token = row[27]
                conn.executemany("INSERT OR IGNORE INTO card_names VALUES (?, ?, ?)",
                                 [(n, card["oracle_id"], is_token) for n in _names_for(card)])
                if not known:
                    conn.execute("INSERT OR IGNORE INTO oracle_defaults VALUES (?, ?, ?, ?)", (card["oracle_id"], card["id"], card["name"], is_token))
                    conn.execute("INSERT INTO oracle_fts (rowid, name, type_line, oracle_text) SELECT rowid, name, coalesce(type_line, ''), "
                                 "coalesce(oracle_text, '') FROM printings WHERE id = ?", (card["id"],))
                result.added.append(card["name"])
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()
        repo._close()  # the next read reopens the file and sees the new cards (and rebuilds its name index)
    return result
