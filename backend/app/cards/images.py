"""Local image cache layout: ``images/{cards|tokens}/{id[:2]}/{id}-{face}-{size}.jpg``.

Files are addressed by Scryfall printing UUID (never by card name), so paths are always
safe to compute and cannot be influenced by user input beyond a validated UUID.
"""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.cards.art_roots import ArtRoot

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
IMAGE_SIZES = ("small", "normal", "large", "art_crop")
DEFAULT_SIZE = "normal"
MAX_FACES = 4


# The standard Magic card back (Scryfall's ``card_back_id`` for every normal card). Fetched from Scryfall into the
# local cache with the art, like card images; never shipped with Fyodor.
CARD_BACK_ID = "0aeebaf5-8c7d-4636-9e82-8c27447861f7"
CARD_BACK_URL = f"https://backs.scryfall.io/normal/{CARD_BACK_ID[0]}/{CARD_BACK_ID[1]}/{CARD_BACK_ID}.jpg"


# The mana and card symbols ({W}, {2/U}, {T} …), one SVG each, named as Scryfall names them (``WU.svg`` for {W/U}). Fetched
# from Scryfall into the cache with the card data (app/cards/linked.py), never shipped. Only names from the cached list are
# ever served, and every name is plain capitals and digits.
SYMBOL_CODE_RE = re.compile(r"^[A-Z0-9]{1,16}$")
SYMBOL_INDEX = "symbology.json"


def media_type(path: Path) -> str:
    """A picture's type from its first bytes (an art folder may hold PNG or WebP); JPEG, the cache's, otherwise."""
    try:
        with path.open("rb") as fh:
            head = fh.read(12)
    except OSError:
        return "image/jpeg"
    if head[1:4] == b"PNG" and head[:1] == bytes((0x89,)):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


class InvalidImageRequest(ValueError):
    pass


class ImageStore:
    def __init__(self, root: Path, bundled: Path | None = None, roots: Sequence[ArtRoot] = ()) -> None:
        self.root = root
        # -- art folders -- read-only folders of pictures searched after the cache, in order, never written to (docs/OFFLINE.md):
        # the installer's seed/images (-- offline token art --), folders found beside Fyodor's data, and the ones the host added
        self.roots: tuple[ArtRoot, ...] = (*((ArtRoot(bundled, "bundled", "fyodor"),) if bundled is not None else ()), *roots)
        self._symbols: tuple[tuple[str, int], dict[str, dict[str, str]]] | None = None  # the symbol list, by its file and mtime

    @property
    def bundled(self) -> Path | None:
        return next((r.base for r in self.roots if r.source == "bundled"), None)

    def path_for(self, card_id: str, *, face: int = 0, size: str = DEFAULT_SIZE, is_token: bool = False) -> Path:
        if not UUID_RE.match(card_id):
            raise InvalidImageRequest("card id must be a lowercase UUID")
        if size not in IMAGE_SIZES:
            raise InvalidImageRequest(f"size must be one of {', '.join(IMAGE_SIZES)}")
        if not 0 <= face < MAX_FACES:
            raise InvalidImageRequest("face out of range")
        kind = "tokens" if is_token else "cards"
        return self.root / kind / card_id[:2] / f"{card_id}-{face}-{size}.jpg"

    def find(self, card_id: str, *, face: int = 0, size: str = DEFAULT_SIZE) -> Path | None:
        """Return the cached file for either kind, falling back to other sizes."""
        sizes = [size, *(s for s in ("normal", "large", "small") if s != size)] if size != "art_crop" else [size]
        for candidate_size in sizes:
            for is_token in (False, True):
                path = self.path_for(card_id, face=face, size=candidate_size, is_token=is_token)
                if path.is_file():
                    return path
        for art_root in self.roots:
            found = art_root.find(card_id, face=face, sizes=sizes)
            if found is not None:
                return found
        return None

    def card_back_path(self) -> Path:
        return self.root / "backs" / f"{CARD_BACK_ID}-normal.jpg"

    def card_back(self) -> Path | None:
        """The cached card back, else one an art folder carries (a portable build's seed/images: offline from the start)."""
        rel = self.card_back_path().relative_to(self.root)
        for base in (self.root, *(r.base for r in self.roots if r.layout == "fyodor")):
            if (base / rel).is_file():
                return base / rel
        return None

    # -- mana symbols --------------------------------------------------------------------
    def symbols_dir(self) -> Path:
        return self.root / "symbols"

    def _symbols_read_dir(self) -> Path:
        """Where symbols are read from: the cache once it has them, else the first art folder that carries a set
        (a portable build's seed/images/symbols), so an offline computer draws the real symbols from the start."""
        for base in (self.root, *(r.base for r in self.roots if r.layout == "fyodor")):
            if (base / "symbols" / SYMBOL_INDEX).is_file():
                return base / "symbols"
        return self.symbols_dir()

    def symbol_path(self, code: str) -> Path:
        if not SYMBOL_CODE_RE.match(code):
            raise InvalidImageRequest("symbol codes are capitals and digits")
        return self.symbols_dir() / f"{code}.svg"

    def symbol_index(self) -> dict[str, dict[str, str]]:
        """The cached symbols: their text without braces ("W/U") -> ``{"svg": "WU", "english": …}``. Empty until fetched."""
        path = self._symbols_read_dir() / SYMBOL_INDEX
        try:
            stamp = (str(path), path.stat().st_mtime_ns)
        except OSError:
            return {}
        if self._symbols and self._symbols[0] == stamp:
            return dict(self._symbols[1])
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        index: dict[str, dict[str, str]] = {}
        for text, entry in (raw.items() if isinstance(raw, dict) else ()):
            code = entry.get("svg") if isinstance(entry, dict) else None
            if isinstance(code, str) and SYMBOL_CODE_RE.match(code):
                index[str(text)] = {"svg": code, "english": str(entry.get("english", ""))}
        self._symbols = (stamp, index)
        return dict(index)

    def write_symbol_index(self, index: dict[str, dict[str, str]]) -> None:
        path = self.symbols_dir() / SYMBOL_INDEX
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{threading.get_ident()}.part")  # (an update and a start-up fetch may overlap)
        tmp.write_text(json.dumps(index, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)

    def symbol(self, code: str) -> Path | None:
        """The cached SVG for a code from the cached list; None for anything else (never a path from the request)."""
        known = {entry["svg"] for entry in self.symbol_index().values()}
        if code not in known or not SYMBOL_CODE_RE.match(code):
            return None
        path = self._symbols_read_dir() / self.symbol_path(code).name
        return path if path.is_file() else None

    def has(self, card_id: str, face: int = 0) -> bool:
        return self.find(card_id, face=face) is not None

    def count(self) -> int:
        total = 0
        for kind in ("cards", "tokens"):
            base = self.root / kind
            if base.is_dir():
                total += sum(1 for _ in base.glob("*/*.jpg"))
        return total
