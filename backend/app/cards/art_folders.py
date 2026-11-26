"""-- art folders -- which read-only picture folders the image store searches after its cache, in order (docs/OFFLINE.md):

1. the installer's ``seed/images`` beside Fyodor.exe (-- offline token art --, art packs);
2. found on their own: ``%USERPROFILE%\\Fyodor\\images``, ``%USERPROFILE%\\Fyodor\\seed\\images``, ``<data folder>\\..\\images``;
3. ``FYODOR_ART_DIRS`` (folders separated by ``os.pathsep``);
4. the ones the host added in Settings → Card database, kept in ``<data folder>/art-folders.json``.

Fyodor's own cache is never one of them, and nothing is ever written into them.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.cards.art_roots import LOOKED_FOR, ArtRoot, detect
from app.cards.images import ImageStore
from app.config import Settings, bundled_images

FILE_NAME = "art-folders.json"


class ArtFolderError(ValueError):
    pass


def home_dir() -> Path:
    return Path.home()


def auto_candidates(settings: Settings) -> list[Path]:
    home = home_dir()
    return [home / "Fyodor" / "images", home / "Fyodor" / "seed" / "images", settings.data_dir.parent / "images"]


def _key(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve()))
    except OSError:
        return os.path.normcase(str(path))


def clean_path(raw: str) -> Path:
    """A folder path as pasted: quotes and spaces around it dropped, ``~`` expanded."""
    text = raw.strip().strip('"').strip("'").strip()
    if not text:
        raise ArtFolderError("Paste a folder path first.")
    if "\x00" in text:
        raise ArtFolderError("That isn't a folder path.")
    return Path(os.path.expanduser(text))


class ArtFolders:
    def __init__(self, settings: Settings, images: ImageStore, on_change: Callable[[], None] | None = None) -> None:
        self.settings = settings
        self.images = images
        self.on_change = on_change
        self._lock = threading.Lock()
        self._missing: list[tuple[Path, str]] = []  # added/env folders that aren't there now (shown, not searched)
        self._fresh: ArtRoot | None = None  # a folder just added and counted
        self.refresh()

    # -- the list ---------------------------------------------------------------------------------
    @property
    def file(self) -> Path:
        return self.settings.data_dir / FILE_NAME

    def added(self) -> list[str]:
        try:
            raw: Any = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        folders = raw.get("folders") if isinstance(raw, dict) else None
        return [f for f in folders if isinstance(f, str) and f] if isinstance(folders, list) else []

    def _save(self, folders: list[str]) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_name(f"{FILE_NAME}.part")
        tmp.write_text(json.dumps({"folders": folders}, indent=2), encoding="utf-8")
        os.replace(tmp, self.file)

    def _wanted(self) -> list[tuple[Path, str]]:
        wanted: list[tuple[Path, str]] = []
        bundled = bundled_images()
        if bundled is not None:
            wanted.append((bundled, "bundled"))
        wanted += [(p, "auto") for p in auto_candidates(self.settings) if p.is_dir()]
        wanted += [(p, "env") for p in self.settings.art_dirs]
        wanted += [(Path(p), "added") for p in self.added()]
        return wanted

    def refresh(self) -> None:
        """Rebuild the store's folder list (pictures are looked up again; loose folders are indexed again when next needed)."""
        cache = _key(self.settings.images_dir)
        seen = {cache}
        roots: list[ArtRoot] = []
        missing: list[tuple[Path, str]] = []
        with self._lock:
            old = {(_key(r.path), r.source): r for r in (*self.images.roots, *((self._fresh,) if self._fresh else ()))}
            for path, source in self._wanted():
                found = detect(path)
                if found is None:
                    if not path.is_dir():
                        missing.append((path, source))
                        continue
                    found = (path, "fyodor")  # (no pictures yet: looked in as the cache's layout, so ones copied in later show)
                base, layout = found
                if _key(base) in seen or _key(path) in seen:
                    continue
                seen |= {_key(base), _key(path)}
                previous = old.get((_key(path), source))
                if previous is not None and _key(previous.base) == _key(base) and previous.layout == layout:
                    roots.append(previous)  # (keeps its index and count; a rescan clears them)
                else:
                    roots.append(ArtRoot(base, source, layout, path=path))
            self.images.roots = tuple(roots)
            self._missing = missing
        if self.on_change is not None:
            self.on_change()

    def rescan(self) -> list[dict[str, Any]]:
        for root in self.images.roots:
            root.rescan()
        self.refresh()
        return self.listing()

    def listing(self) -> list[dict[str, Any]]:
        rows = [{"path": str(r.path), "folder": str(r.base), "source": r.source, "exists": r.base.is_dir(), "layout": r.layout,
                 "count": r.count()} for r in self.images.roots]
        rows += [{"path": str(p), "folder": str(p), "source": s, "exists": p.is_dir(), "layout": None, "count": 0}
                 for p, s in self._missing]
        return rows

    # -- changes --------------------------------------------------------------------------------------
    def add(self, raw: str) -> dict[str, Any]:
        path = clean_path(raw)
        if not path.is_absolute():
            raise ArtFolderError("Use the folder's full path, like C:\\Users\\you\\Fyodor\\images.")
        if not path.is_dir():
            raise ArtFolderError(f"There's no folder at {path}.")
        path = path.resolve()
        found = detect(path)
        if found is None:
            raise ArtFolderError(f"No card pictures in {path}. Looked for " + "; ".join(LOOKED_FOR) + ".")
        base, layout = found
        if _key(base) == _key(self.settings.images_dir) or _key(path) == _key(self.settings.images_dir):
            raise ArtFolderError("That's Fyodor's own picture cache: it's always used.")
        for root in self.images.roots:
            if _key(root.base) == _key(base):
                raise ArtFolderError(f"Already reading pictures from {root.base}.")
        root = ArtRoot(base, "added", layout, path=path)
        count = root.count()
        if not count:
            raise ArtFolderError(f"No card pictures in {path}. Looked for " + "; ".join(LOOKED_FOR) + ".")
        folders = self.added()
        folders.append(str(path))
        self._save(folders)
        self._fresh = root
        try:
            self.refresh()
        finally:
            self._fresh = None
        return {"path": str(path), "folder": str(root.base), "source": "added", "exists": True, "layout": root.layout,
                "count": count}

    def remove(self, raw: str) -> None:
        key = _key(clean_path(raw))
        folders = self.added()
        keep = [f for f in folders if _key(Path(f)) != key]
        if len(keep) == len(folders):
            raise ArtFolderError("Only folders added here can be removed.")
        self._save(keep)
        self.refresh()
