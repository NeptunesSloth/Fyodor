"""Local image cache layout: ``images/{cards|tokens}/{id[:2]}/{id}-{face}-{size}.jpg``.

Files are addressed by Scryfall printing UUID (never by card name), so paths are always
safe to compute and cannot be influenced by user input beyond a validated UUID.
"""

from __future__ import annotations

import re
from pathlib import Path

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
IMAGE_SIZES = ("small", "normal", "large", "art_crop")
DEFAULT_SIZE = "normal"
MAX_FACES = 4


# The standard Magic card back (Scryfall's ``card_back_id`` for every normal card). Fetched from Scryfall into the
# local cache with the art, like card images; never shipped with Fyodor.
CARD_BACK_ID = "0aeebaf5-8c7d-4636-9e82-8c27447861f7"
CARD_BACK_URL = f"https://backs.scryfall.io/normal/{CARD_BACK_ID[0]}/{CARD_BACK_ID[1]}/{CARD_BACK_ID}.jpg"


class InvalidImageRequest(ValueError):
    pass


class ImageStore:
    def __init__(self, root: Path) -> None:
        self.root = root

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
        return None

    def card_back_path(self) -> Path:
        return self.root / "backs" / f"{CARD_BACK_ID}-normal.jpg"

    def card_back(self) -> Path | None:
        path = self.card_back_path()
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
