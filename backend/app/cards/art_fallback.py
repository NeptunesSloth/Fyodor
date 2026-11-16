"""-- same-card art -- a printing with no picture on this computer shows another printing's picture of the same card.

An art pack (the installer's ``seed/images``) or a cache filled by other decks often holds only one printing of a card, while a
deck asks for another (an Archidekt import keeps its set and collector number). Rather than play that card as a proxy, the server
serves the picture of a sibling printing: same oracle id, same face; the card's default printing first, then the newest with
art. A back face (face > 0) only borrows from a printing with the same layout and the same number of faces.

The exact printing's own picture always wins and is never cached here (``ImageStore.find`` is a few file checks). Only the
sibling scan is cached: per card and face, which printings have art, kept for ``TTL_SECONDS`` and re-checked on use, so art that
arrives later (a download, a friend's art over the LAN) shows within that time.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

from app.cards.images import ImageStore

TTL_SECONDS = 30.0
MAX_FAMILIES = 512  # cards whose scan is remembered
MAX_SCAN = 400  # printings checked per card (a basic land has over a thousand; the default comes first)

# one printing of the card: (printing id, layout, image faces)
Sibling = tuple[str, str, int]
FamilyFn = Callable[[str], list[Sibling]]  # oracle id -> its printings, the default first


class ArtFallback:
    def __init__(self, images: ImageStore, family: FamilyFn) -> None:
        self.images = images
        self.family = family
        self._lock = threading.Lock()
        # (oracle id, face, art crop?) -> (when scanned, the printings with that picture in preference order)
        self._with_art: OrderedDict[tuple[str, int, bool], tuple[float, list[Sibling]]] = OrderedDict()

    def clear(self) -> None:
        with self._lock:
            self._with_art.clear()

    def _scan(self, oracle_id: str, face: int, size: str) -> list[Sibling]:
        crop = size == "art_crop"
        key = (oracle_id, face, crop)
        now = time.monotonic()
        with self._lock:
            hit = self._with_art.get(key)
            if hit is not None and now - hit[0] < TTL_SECONDS:
                self._with_art.move_to_end(key)
                return hit[1]
        found: list[Sibling] = []
        for sib in self.family(oracle_id)[:MAX_SCAN]:
            if face > 0 and sib[2] <= face:
                continue
            if self.images.find(sib[0], face=face, size="art_crop" if crop else "normal") is not None:
                found.append(sib)
        with self._lock:
            self._with_art[key] = (now, found)
            self._with_art.move_to_end(key)
            while len(self._with_art) > MAX_FAMILIES:
                self._with_art.popitem(last=False)
        return found

    def find(self, card_id: str, oracle_id: str, layout: str, image_faces: int, *, face: int = 0,
             size: str = "normal") -> tuple[Path, str] | None:
        """Another printing's picture of this card for ``face``: (its file, its printing id), or None. Doesn't look at the
        printing's own picture: callers try that first."""
        for attempt in range(2):
            stale = False
            for sid, sib_layout, sib_faces in self._scan(oracle_id, face, size):
                if sid == card_id or (face > 0 and (sib_layout != layout or sib_faces != image_faces)):
                    continue
                path = self.images.find(sid, face=face, size=size)
                if path is not None:
                    return path, sid
                stale = True  # deleted since the scan
            if not stale or attempt:
                return None
            with self._lock:
                self._with_art.pop((oracle_id, face, size == "art_crop"), None)
        return None
