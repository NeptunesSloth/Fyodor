"""Read-only access to the local card database."""

from __future__ import annotations

import difflib
import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

from app.cards.art_fallback import ArtFallback, Sibling
from app.cards.images import ImageStore
from app.cards.names import normalize_name
from app.cards.search import compile_query, fts_quote

log = logging.getLogger(__name__)

SUMMARY_COLUMNS = (
    "p.id, p.oracle_id, p.name, p.layout, p.set_code, p.set_name, p.collector_number, p.rarity, "
    "p.mana_cost, p.cmc, p.type_line, p.oracle_text, p.power, p.toughness, p.loyalty, p.defense, "
    "p.colors, p.color_identity, p.keywords, p.card_faces, p.all_parts, p.image_uris, p.is_token, "
    "p.legalities, p.released_at, p.artist, p.edhrec_rank"
)
# Layouts whose faces each have their own image and which can be turned over.
MAX_TOKEN_ART_FALLBACK = 120  # -- engine token art -- token printings of a name token_art looks through
DOUBLE_FACED_LAYOUTS = {"transform", "modal_dfc", "double_faced_token", "reversible_card", "meld", "battle"}


class CardDatabaseUnavailable(RuntimeError):
    """The card database has not been imported yet."""


class CardRepository:
    def __init__(self, db_path: Path, images: ImageStore) -> None:
        self.db_path = db_path
        self.images = images
        self._conn: sqlite3.Connection | None = None
        self._inode: tuple[int, float] | None = None
        self._lock = threading.RLock()
        self._names: dict[str, str] | None = None
        self._names_for: sqlite3.Connection | None = None
        self._word_names: frozenset[str] = frozenset()
        self._word_names_for: sqlite3.Connection | None = None
        # the rules engine's reads (rules_card): one per printing per open database
        self._rules: dict[str, dict[str, Any] | None] = {}
        self._rules_for: sqlite3.Connection | None = None
        # -- engine token art -- token_art's answers, per open database
        self._token_art: dict[tuple[Any, ...], tuple[str, int] | None] = {}
        self._token_art_for: sqlite3.Connection | None = None
        # -- same-card art -- a printing without a picture here shows another printing's of the same card (app/cards/art_fallback.py)
        self.art = ArtFallback(images, self._art_family)

    # -- connection management -------------------------------------------------------
    def _connection(self) -> sqlite3.Connection:
        """Open (or re-open after the importer swapped the file) a read-only connection."""
        try:
            stat = os.stat(self.db_path)
        except FileNotFoundError:
            self._close()
            raise CardDatabaseUnavailable("Card database not found. Run `python -m tools.update_cards`.") from None
        ident = (stat.st_ino, stat.st_mtime)
        if self._conn is None or ident != self._inode:
            self._close()
            conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._conn, self._inode = conn, ident
            self.art.clear()
            log.info("Opened card database %s", self.db_path)
        return self._conn

    def replace_with(self, new_db: Path) -> None:
        """Swap in a freshly built database (UPDATE CARD DATABASE). Our connection closes first: Windows can't replace
        an open file. Readers wait on the lock and reopen the new file on their next query."""
        with self._lock:
            self._close()
            os.replace(new_db, self.db_path)
            for stale in (Path(f"{self.db_path}-wal"), Path(f"{self.db_path}-shm")):
                stale.unlink(missing_ok=True)
            log.info("Card database replaced with %s", new_db.name)

    def _close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def close(self) -> None:
        with self._lock:
            self._close()

    def _query(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._connection().execute(sql, params).fetchall()

    @property
    def available(self) -> bool:
        try:
            with self._lock:
                self._connection()
            return True
        except CardDatabaseUnavailable:
            return False

    # -- stats -----------------------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        base: dict[str, Any] = {
            "available": False,
            "printings": 0,
            "oracle_cards": 0,
            "tokens": 0,
            "images": self.images.count(),
            "bulk_type": None,
            "bulk_updated_at": None,
            "imported_at": None,
        }
        try:
            meta = {r["key"]: r["value"] for r in self._query("SELECT key, value FROM meta")}
        except (CardDatabaseUnavailable, sqlite3.DatabaseError):
            return base
        base.update(
            available=True,
            printings=int(meta.get("printings", 0)),
            oracle_cards=int(meta.get("oracle_cards", 0)),
            tokens=int(meta.get("tokens", 0)),
            bulk_type=meta.get("bulk_type"),
            bulk_updated_at=meta.get("bulk_updated_at"),
            imported_at=meta.get("imported_at"),
        )
        return base

    # -- lookups ---------------------------------------------------------------------
    def get(self, card_id: str) -> dict[str, Any] | None:
        rows = self._query(f"SELECT {SUMMARY_COLUMNS} FROM printings p WHERE p.id = ?", (card_id,))
        return self._to_card(rows[0], detail=True) if rows else None

    def rules_card(self, card_id: str) -> dict[str, Any] | None:
        """What the rules engine reads about a printing: ``get``'s fields without ``has_image``, read once per printing while
        the same database is open. ``get`` checks the image files on every call, and the engine reads card data tens of
        thousands of times in one action on a big board; the rules never look at images. A new database (``replace_with``,
        or a swapped file that the next query reopens) empties the cache. Callers must not change the returned dict."""
        with self._lock:
            conn = self._conn if self._conn is not None and self._conn is self._rules_for else self._connection()
            if conn is not self._rules_for:
                self._rules, self._rules_for = {}, conn
            if card_id not in self._rules:
                rows = conn.execute(f"SELECT {SUMMARY_COLUMNS} FROM printings p WHERE p.id = ?", (card_id,)).fetchall()
                self._rules[card_id] = self._to_card(rows[0], detail=True, images=False) if rows else None
            return self._rules[card_id]

    def get_many(self, card_ids: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        unique = list(dict.fromkeys(card_ids))
        for start in range(0, len(unique), 500):
            chunk = unique[start : start + 500]
            marks = ",".join("?" * len(chunk))
            for row in self._query(f"SELECT {SUMMARY_COLUMNS} FROM printings p WHERE p.id IN ({marks})", chunk):
                out[row["id"]] = self._to_card(row, detail=True)
        return out

    def printings(self, oracle_id: str) -> list[dict[str, Any]]:
        rows = self._query(
            f"SELECT {SUMMARY_COLUMNS} FROM printings p WHERE p.oracle_id = ? "
            "ORDER BY p.released_at DESC, p.set_code, p.collector_number",
            (oracle_id,),
        )
        return [self._to_card(r) for r in rows]

    def default_printing_id(self, oracle_id: str) -> str | None:
        rows = self._query("SELECT printing_id FROM oracle_defaults WHERE oracle_id = ?", (oracle_id,))
        return rows[0]["printing_id"] if rows else None

    # -- search ----------------------------------------------------------------------
    def search(self, query: str, *, tokens: bool | None = False, limit: int = 60, offset: int = 0) -> list[dict[str, Any]]:
        compiled = compile_query(query)
        where = list(compiled.where)
        params: list[Any] = list(compiled.params)
        want_tokens = compiled.tokens if compiled.tokens is not None else tokens
        if want_tokens is not None:
            where.append("d.is_token = ?")
            params.append(1 if want_tokens else 0)
        order_params: list[Any] = []
        if compiled.name_terms:
            expr = " ".join(fts_quote(t) + "*" for t in compiled.name_terms)
            where.append("p.rowid IN (SELECT rowid FROM oracle_fts WHERE oracle_fts MATCH ?)")
            params.append(f"name : ({expr})")
            typed = normalize_name(compiled.exact_name or " ".join(compiled.name_terms))
            order = "(lower(p.name) = ?) DESC, (lower(p.name) LIKE ?) DESC, "
            order_params = [typed, typed + "%"]
        else:
            order = ""
        sql = (
            f"SELECT {SUMMARY_COLUMNS} FROM oracle_defaults d JOIN printings p ON p.id = d.printing_id "
            f"WHERE {' AND '.join(where) or '1'} "
            f"ORDER BY {order}p.edhrec_rank IS NULL, p.edhrec_rank, p.name LIMIT ? OFFSET ?"
        )
        rows = self._query(sql, [*params, *order_params, max(1, min(limit, 200)), max(0, offset)])
        return [self._to_card(r) for r in rows]

    def autocomplete(self, prefix: str, limit: int = 10) -> list[str]:
        norm = normalize_name(prefix)
        if not norm:
            return []
        rows = self._query(
            "SELECT DISTINCT d.name FROM card_names n JOIN oracle_defaults d ON d.oracle_id = n.oracle_id "
            "WHERE n.name_norm >= ? AND n.name_norm < ? AND d.is_token = 0 ORDER BY d.name LIMIT ?",
            (norm, norm + "￿", limit),
        )
        return [r["name"] for r in rows]

    # -- name resolution (deck import) -----------------------------------------------
    def resolve(
        self, name: str, set_code: str | None = None, collector_number: str | None = None, *, prefer_tokens: bool = False
    ) -> dict[str, Any] | None:
        """Resolve a typed card name (optionally with set / collector number) to a printing."""
        norm = normalize_name(name)
        # Prefer (token-ness as requested, then) cards whose full name matches over face-name matches:
        # "Seething Song" is its own card and also a face of an unrelated double-faced card.
        oracle_rows = self._query(
            "SELECT n.oracle_id, n.is_token, d.name FROM card_names n "
            "LEFT JOIN oracle_defaults d ON d.oracle_id = n.oracle_id WHERE n.name_norm = ?",
            (norm,),
        )
        want_token = 1 if prefer_tokens else 0
        oracle_rows = sorted(
            oracle_rows,
            key=lambda r: (r["is_token"] != want_token, normalize_name(r["name"] or "") != norm),
        )
        if not oracle_rows and " // " in norm:
            # "Fire // Ice" typed but only a face name matches, or vice versa
            oracle_rows = self._query("SELECT oracle_id, is_token FROM card_names WHERE name_norm = ?", (norm.split(" // ")[0],))
        if not oracle_rows:
            return None
        oracle_ids = [r["oracle_id"] for r in oracle_rows]
        marks = ",".join("?" * len(oracle_ids))
        if set_code:
            sql = f"SELECT {SUMMARY_COLUMNS} FROM printings p WHERE p.oracle_id IN ({marks}) AND p.set_code = ?"
            args: list[Any] = [*oracle_ids, set_code.lower()]
            if collector_number:
                exact = self._query(sql + " AND p.collector_number = ?", [*args, collector_number])
                if exact:
                    return self._to_card(exact[0])
            in_set = self._query(sql + " ORDER BY p.promo, p.collector_number", args)
            if in_set:
                return self._to_card(in_set[0])
        default_id = self.default_printing_id(oracle_ids[0])
        return self.get(default_id) if default_id else None

    def has_set(self, code: str) -> bool:
        code = (code or "").lower()
        if not code or len(code) > 10:
            return False
        return bool(self._query("SELECT 1 FROM printings WHERE set_code = ? LIMIT 1", (code,)))

    def resolve_detailed(
        self,
        name: str,
        set_code: str | None = None,
        collector_number: str | None = None,
        *,
        printing_id: str | None = None,
        oracle_id: str | None = None,
        prefer_tokens: bool = False,
    ) -> tuple[dict[str, Any] | None, str]:
        """Resolve with a stable-identity-first strategy and report how it was resolved.

        Order: Scryfall printing id → set + collector number → set → oracle id's default
        printing → name. Returns ``(card, resolution)`` where resolution is one of
        ``exact``, ``set``, ``fallback`` (a requested printing is missing), ``name``
        (no printing was requested) or ``unresolved``.
        """
        printing_requested = bool(printing_id or set_code)
        if printing_id:
            exact = self.get(printing_id)
            if exact:
                return exact, "exact"
        oracle_ids: list[str] = []
        if oracle_id and self._query("SELECT 1 FROM oracle_defaults WHERE oracle_id = ?", (oracle_id,)):
            oracle_ids = [oracle_id]
        if not oracle_ids:
            by_name = self.resolve(name, prefer_tokens=prefer_tokens)
            if by_name is None:
                return None, "unresolved"
            oracle_ids = [by_name["oracle_id"]]
        marks = ",".join("?" * len(oracle_ids))
        if set_code:
            sql = f"SELECT {SUMMARY_COLUMNS} FROM printings p WHERE p.oracle_id IN ({marks}) AND p.set_code = ?"
            args: list[Any] = [*oracle_ids, set_code.lower()]
            if collector_number:
                rows = self._query(sql + " AND p.collector_number = ?", [*args, collector_number])
                if rows:
                    return self._to_card(rows[0]), "exact"
            rows = self._query(sql + " ORDER BY p.promo, p.collector_number", args)
            if rows:
                return self._to_card(rows[0]), ("set" if collector_number else "exact")
        default_id = self.default_printing_id(oracle_ids[0])
        card = self.get(default_id) if default_id else None
        if card is None:
            return None, "unresolved"
        return card, ("fallback" if printing_requested else "name")

    def name_at(self, text: str, start: int) -> str | None:
        """The longest exact local catalog name beginning at a text position."""
        with self._lock:
            conn = self._connection()
            if self._word_names_for is not conn:
                rows = conn.execute('SELECT DISTINCT name_norm FROM card_names').fetchall()
                self._word_names = frozenset(str(row['name_norm']) for row in rows)
                self._word_names_for = conn
            names = self._word_names
        tail = text[start:]
        for end in range(min(200, len(tail)), 0, -1):
            part = tail[:end]
            if part[-1].isspace() or (end < len(tail) and tail[end].isalnum()):
                continue
            if normalize_name(part) in names:
                return part
        return None

    def suggest(self, name: str, limit: int = 5) -> list[str]:
        """Closest known card names for an unresolved deck line (typo tolerant)."""
        norm = normalize_name(name)
        if not norm:
            return []
        names = self._name_index()
        matches = difflib.get_close_matches(norm, list(names), n=limit, cutoff=0.72)
        if len(matches) < limit:
            squashed = norm.replace(" ", "")
            for key in names:
                if key.replace(" ", "") == squashed and key not in matches:
                    matches.insert(0, key)
        return [names[m] for m in matches[:limit]]

    def _name_index(self) -> dict[str, str]:
        with self._lock:
            conn = self._connection()
            if self._names is None or self._names_for is not conn:
                rows = conn.execute("SELECT name FROM oracle_defaults WHERE is_token = 0").fetchall()
                self._names = {normalize_name(r["name"]): r["name"] for r in rows}
                self._names_for = conn
            return self._names

    def planar_cards(self) -> list[dict[str, Any]]:
        """-- planechase -- every plane and phenomenon (one printing each, the default): the pool a planar deck is dealt from
        (app/game/handlers/planechase.py)."""
        rows = self._query(
            "SELECT p.id, p.name, p.type_line FROM oracle_defaults d JOIN printings p ON p.id = d.printing_id "
            "WHERE p.type_line LIKE 'Plane %' OR p.type_line = 'Plane' OR p.type_line LIKE 'Phenomenon%' ORDER BY p.name"
        )
        return [{"id": r["id"], "name": r["name"], "type_line": r["type_line"]} for r in rows]

    def related_tokens(self, card_id: str) -> list[dict[str, Any]]:
        card = self.get(card_id)
        if not card:
            return []
        return card["related_tokens"]

    # -- engine token art (app/cards/token_match.py) ------------------------------------
    def token_art(self, source_id: str | None, name: str, type_line: str, power: str | None, toughness: str | None,
                  colors: list[str]) -> tuple[str, int] | None:
        """The token printing (and its picture face) that pictures a token the rules engine described, preferring the source
        printing's related tokens; None when no token printing matches. Remembered per open database."""
        from app.cards import token_match

        want = token_match.wanted(name, type_line, power, toughness, colors)
        key = (source_id, want)
        with self._lock:
            conn = self._connection()
            if conn is not self._token_art_for:
                self._token_art, self._token_art_for = {}, conn
            if key in self._token_art:
                return self._token_art[key]
        source = self.rules_card(source_id) if source_id else None
        related = [t["id"] for t in (source or {}).get("related_tokens") or []]
        found = token_match.choose(related, self.rules_card, want, self._has_art)
        if found is None:
            found = token_match.choose(self._token_ids_named(name), self.rules_card, want, self._has_art)
        with self._lock:
            if len(self._token_art) > 4096:
                self._token_art.clear()
            self._token_art[key] = found
        return found

    def _token_ids_named(self, name: str) -> list[str]:
        """Token printings named ``name`` (or with a face of that name), single-faced first, then newest first: ``token_art``'s
        fallback."""
        n = name.strip()
        if not n:
            return []
        like = n.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self._query(
            "SELECT id FROM printings WHERE is_token = 1 AND (name = ? COLLATE NOCASE OR name LIKE ? ESCAPE '\\' "
            "OR name LIKE ? ESCAPE '\\') ORDER BY instr(name, ' // ') > 0, released_at DESC, set_code, collector_number, id "
            f"LIMIT {int(MAX_TOKEN_ART_FALLBACK)}",
            (n, like + " // %", "% // " + like),
        )
        return [r["id"] for r in rows]

    def _has_art(self, card_id: str, face: int) -> bool:
        """A picture of this printing's face shows here: its own (the cache or an art folder) or another printing's of it."""
        if self.images.has(card_id, face):
            return True
        rows = self._query("SELECT oracle_id, layout, image_uris, card_faces FROM printings WHERE id = ?", (card_id,))
        if not rows or not rows[0]["oracle_id"]:
            return False
        r = rows[0]
        return self.art.find(card_id, r["oracle_id"], r["layout"], _image_face_count(r["image_uris"], r["card_faces"]),
                             face=face) is not None

    # -- same-card art ----------------------------------------------------------------
    def _art_family(self, oracle_id: str) -> list[Sibling]:
        """Every printing of a card as (id, layout, image faces): the default printing first, then the newest."""
        rows = self._query(
            "SELECT p.id, p.layout, p.image_uris, p.card_faces FROM printings p "
            "LEFT JOIN oracle_defaults d ON d.oracle_id = p.oracle_id AND d.printing_id = p.id "
            "WHERE p.oracle_id = ? ORDER BY d.printing_id IS NULL, p.released_at DESC, p.set_code, p.collector_number",
            (oracle_id,),
        )
        return [(r["id"], r["layout"], _image_face_count(r["image_uris"], r["card_faces"])) for r in rows]

    def find_art(self, card_id: str, *, face: int = 0, size: str = "normal") -> Path | None:
        """The picture shown for a printing: its own, or another printing's of the same card (None: a proxy)."""
        own = self.images.find(card_id, face=face, size=size)
        if own is not None:
            return own
        return self.borrowed_art(card_id, face=face, size=size)

    def borrowed_art(self, card_id: str, *, face: int = 0, size: str = "normal") -> Path | None:
        """Another printing's picture of the same card for this printing's face (not its own), or None."""
        rows = self._query("SELECT oracle_id, layout, image_uris, card_faces FROM printings WHERE id = ?", (card_id,))
        if not rows:
            return None
        r = rows[0]
        got = self.art.find(card_id, r["oracle_id"], r["layout"], _image_face_count(r["image_uris"], r["card_faces"]),
                            face=face, size=size)
        return got[0] if got else None

    # -- row mapping -----------------------------------------------------------------
    def _to_card(self, row: sqlite3.Row, *, detail: bool = False, images: bool = True) -> dict[str, Any]:
        faces_raw: list[dict[str, Any]] = json.loads(row["card_faces"]) if row["card_faces"] else []
        is_token = bool(row["is_token"])
        layout = row["layout"]
        image_faces = [i for i, f in enumerate(faces_raw) if f.get("image_uris")] if not row["image_uris"] else [0]
        if not image_faces:
            image_faces = [0]
        faces = [
            {
                "name": f.get("name", ""),
                "mana_cost": f.get("mana_cost"),
                "type_line": f.get("type_line"),
                "oracle_text": f.get("oracle_text"),
                "power": f.get("power"),
                "toughness": f.get("toughness"),
                "loyalty": f.get("loyalty"),
                "defense": f.get("defense"),
                "colors": f.get("colors"),
                "image_face": i if i in image_faces else 0,
            }
            for i, f in enumerate(faces_raw)
        ]
        parts = json.loads(row["all_parts"]) if row["all_parts"] else []
        card: dict[str, Any] = {
            "id": row["id"],
            "oracle_id": row["oracle_id"],
            "name": row["name"],
            "layout": layout,
            "set_code": row["set_code"],
            "set_name": row["set_name"],
            "collector_number": row["collector_number"],
            "rarity": row["rarity"],
            "mana_cost": row["mana_cost"],
            "cmc": row["cmc"],
            "type_line": row["type_line"],
            "oracle_text": row["oracle_text"],
            "power": row["power"],
            "toughness": row["toughness"],
            "loyalty": row["loyalty"],
            "defense": row["defense"],
            "colors": json.loads(row["colors"]),
            "color_identity": json.loads(row["color_identity"]),
            "keywords": json.loads(row["keywords"]),
            "is_token": is_token,
            "faces": faces,
            "double_faced": layout in DOUBLE_FACED_LAYOUTS and len(image_faces) > 1,
            "image_faces": len(image_faces),
        }
        if images:  # (a file check per call: rules_card leaves it out)
            # own_image: this printing's picture is here; has_image: some picture will show (-- same-card art -- another
            # printing's of the same card when this one has none)
            own = self.images.has(row["id"], 0)
            card["own_image"] = own
            borrowed = None if own else self.art.find(row["id"], row["oracle_id"], layout, len(image_faces))
            card["has_image"] = own or borrowed is not None
            if borrowed is not None:
                card["art_from"] = borrowed[1]  # the printing whose picture shows
        if detail:
            legal = json.loads(row["legalities"] or "{}")
            card.update(
                released_at=row["released_at"],
                artist=row["artist"],
                commander_legal=legal.get("commander"),
                related_tokens=[
                    {"id": p["id"], "name": p["name"], "type_line": p.get("type_line")}
                    for p in parts
                    if p.get("component") == "token" and p.get("id") != row["id"]
                ],
                related_cards=[
                    {"id": p["id"], "name": p["name"], "component": p.get("component")}
                    for p in parts
                    if p.get("component") in ("combo_piece", "meld_part", "meld_result") and p.get("id") != row["id"]
                ],
            )
        return card

    def image_rows(self, card_ids: list[str]) -> list[sqlite3.Row]:
        """Rows with remote image URLs for the downloader (``image_jobs_from_rows``)."""
        rows: list[sqlite3.Row] = []
        unique = list(dict.fromkeys(card_ids))
        for start in range(0, len(unique), 500):
            chunk = unique[start : start + 500]
            rows += self._query(
                f"SELECT id, is_token, image_uris, card_faces FROM printings WHERE id IN ({','.join('?' * len(chunk))})", chunk
            )
        return rows

    def image_urls(self, card_id: str) -> tuple[bool, list[dict[str, str]]]:
        """Remote image URLs per face (used only by the downloader)."""
        rows = self._query("SELECT is_token, image_uris, card_faces FROM printings WHERE id = ?", (card_id,))
        if not rows:
            return False, []
        row = rows[0]
        if row["image_uris"]:
            return bool(row["is_token"]), [json.loads(row["image_uris"])]
        faces = json.loads(row["card_faces"] or "[]")
        return bool(row["is_token"]), [f.get("image_uris") or {} for f in faces if f.get("image_uris")]


def _image_face_count(image_uris: str | None, card_faces: str | None) -> int:
    """How many pictures a printing has (as ``_to_card``'s ``image_faces``)."""
    if image_uris:
        return 1
    faces = json.loads(card_faces) if card_faces else []
    return max(1, sum(1 for f in faces if f.get("image_uris")))


class RulesCards:
    """A game session's card source: ``get`` is the repository's cached ``rules_card``; every other method is the repository's."""

    def __init__(self, repo: CardRepository) -> None:
        self.repo = repo

    def get(self, card_id: str) -> dict[str, Any] | None:
        return self.repo.rules_card(card_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.repo, name)
