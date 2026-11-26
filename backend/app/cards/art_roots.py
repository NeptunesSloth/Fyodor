"""-- art folders -- folders of card pictures Fyodor reads in place, after its own cache (docs/OFFLINE.md). Never written to.

Two layouts:

- ``fyodor``: the image cache's own (``{cards|tokens}/{id[:2]}/{id}-{face}-{size}.jpg``), as in an installer's ``seed/images``
  or another computer's ``Fyodor\\data\\images``. Looked up by computing the path; nothing is scanned.
- ``loose``: pictures named by Scryfall printing id anywhere up to a few folders down (``{id}-{face}-{size}.jpg``,
  ``{id}-{face}.png``, ``{id}.jpg`` …). Indexed once (id -> files), again on a rescan.

Lookups only ever take a validated printing id: no part of a request becomes a path.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

LOOSE_NAME_RE = re.compile(
    r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"(?:-([0-3])(?:-(small|normal|large|art_crop))?)?\.(jpg|jpeg|png|webp)$",
    re.IGNORECASE,
)
MAX_DEPTH = 3  # folders below the chosen one a loose picture may sit in
DESCEND = ("images", "data/images", "seed/images")  # a Fyodor folder, its data folder, an install: the pictures inside
LOOKED_FOR = ("cards/ or tokens/ folders (Fyodor's picture layout)", "an images, data/images or seed/images folder",
              "pictures named by Scryfall id, like 0000579f-7b35-4ed3-b44c-db2a538066fe.jpg")

# (face, size) -> file; size None = a picture named by id alone (any size), face 0 for a name without a face
LooseFiles = dict[tuple[int, str | None], Path]


def _is_fyodor(path: Path) -> bool:
    return (path / "cards").is_dir() or (path / "tokens").is_dir()


def _walk(base: Path, *, first_only: bool = False) -> dict[str, LooseFiles]:
    """Pictures named by printing id under ``base`` (at most MAX_DEPTH folders down)."""
    index: dict[str, LooseFiles] = {}
    stack: list[tuple[Path, int]] = [(base, 0)]
    while stack:
        folder, depth = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth < MAX_DEPTH:
                        stack.append((Path(entry.path), depth + 1))
                    continue
                if not entry.is_file():
                    continue
            except OSError:
                continue
            m = LOOSE_NAME_RE.match(entry.name)
            if m is None:
                continue
            card_id = m.group(1).lower()
            key = (int(m.group(2) or 0), m.group(3).lower() if m.group(3) else None)
            index.setdefault(card_id, {}).setdefault(key, Path(entry.path))
            if first_only:
                return index
    return index


def detect(path: Path) -> tuple[Path, str] | None:
    """Where the pictures in a chosen folder are and how they're laid out: (folder to read, "fyodor" | "loose"), or None."""
    if not path.is_dir():
        return None
    if _is_fyodor(path):
        return path, "fyodor"
    for sub in DESCEND:
        inner = path / sub
        if inner.is_dir():
            if _is_fyodor(inner):
                return inner, "fyodor"
            if _walk(inner, first_only=True):
                return inner, "loose"
    if _walk(path, first_only=True):
        return path, "loose"
    return None


class ArtRoot:
    """One read-only folder of pictures: ``path`` as chosen, ``base`` where its pictures are."""

    def __init__(self, base: Path, source: str, layout: str, path: Path | None = None) -> None:
        self.base = base
        self.path = path or base
        self.source = source  # bundled | auto | env | added
        self.layout = layout  # fyodor | loose
        self._lock = threading.Lock()
        self._index: dict[str, LooseFiles] | None = None
        self._count: int | None = None

    def index(self) -> dict[str, LooseFiles]:
        with self._lock:
            if self._index is None:
                self._index = _walk(self.base)
            return self._index

    def rescan(self) -> None:
        with self._lock:
            self._index = None
            self._count = None

    def count(self) -> int:
        """How many pictures the folder holds (counted once, again after a rescan)."""
        if self._count is None:
            if self.layout == "loose":
                self._count = sum(len(files) for files in self.index().values())
            else:
                total = 0
                for kind in ("cards", "tokens"):
                    try:
                        for sub in os.scandir(self.base / kind):
                            if sub.is_dir():
                                total += sum(1 for f in os.scandir(sub.path) if f.name.lower().endswith(".jpg"))
                    except OSError:
                        continue
                self._count = total
        return self._count

    def find(self, card_id: str, *, face: int, sizes: list[str]) -> Path | None:
        """This printing's picture here; ``card_id`` already validated as a lowercase printing id."""
        if self.layout == "fyodor":
            for size in sizes:
                for kind in ("tokens", "cards"):
                    path = self.base / kind / card_id[:2] / f"{card_id}-{face}-{size}.jpg"
                    if path.is_file():
                        return path
            return None
        files = self.index().get(card_id)
        if not files:
            return None
        keys: list[tuple[int, str | None]] = [(face, size) for size in sizes]
        if sizes[0] != "art_crop":
            keys.append((face, None))  # a picture named by id (and face) alone: any card-sized request
        for key in keys:
            hit = files.get(key)
            if hit is not None and hit.is_file():
                return hit
        return None
