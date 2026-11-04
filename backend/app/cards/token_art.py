"""Token pictures fetched when a table first shows them (the Bag of Extras' tokens, a deck's tokens).

Like all card art they're linked from Scryfall and cached on the host (``images/tokens``), never shipped with Fyodor. Deck art is
kept ahead of time (app/cards/art_keeper.py); a token picture nobody downloaded yet is fetched when a client asks for it
(``GET /api/images/{id}``): only for a token printing of the card database, only from Scryfall's image hosts, never with
FYODOR_ALLOW_NETWORK=0, a few at a time, and a picture that couldn't be fetched isn't asked for again for ``RETRY_SECONDS``.
Offline, the request is a 404 as before and the client draws its own token card.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx

from app.cards.downloader import fetch_into
from app.cards.images import UUID_RE, ImageStore
from app.cards.repository import CardDatabaseUnavailable, CardRepository

if TYPE_CHECKING:
    from app.config import Settings

log = logging.getLogger(__name__)

DOWNLOADS = True  # (the test suite turns this off: no test reaches Scryfall unless it asks to)
RETRY_SECONDS = 600.0
PARALLEL = 4
IMAGE_HOSTS = ("scryfall.io", "scryfall.com")
SIZE = "normal"


def is_jpeg(body: bytes) -> bool:
    return body.startswith(b"\xff\xd8")


def scryfall_image(url: object) -> str | None:
    """``url`` if it's an https picture on Scryfall's image hosts, else None (a shared card database can't send us elsewhere)."""
    if not isinstance(url, str):
        return None
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    ok = parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in IMAGE_HOSTS)
    return url if ok else None


class TokenArt:
    def __init__(self, settings: Settings, images: ImageStore, cards: CardRepository,
                 client_factory: Callable[[], Callable[..., httpx.Client]]) -> None:
        self.settings = settings
        self.images = images
        self.cards = cards
        self.client_factory = client_factory  # (read at each fetch: the tests swap the services' client)
        self._gate = threading.BoundedSemaphore(PARALLEL)
        self._lock = threading.Lock()
        self._failed: dict[tuple[str, int], float] = {}

    def fetch(self, card_id: str, face: int = 0) -> Path | None:
        """Fetch a token printing's picture into the cache now, if this computer may go online. The cached file, or None."""
        if not DOWNLOADS or not self.settings.allow_network or not UUID_RE.match(card_id):
            return None
        key = (card_id, face)
        with self._lock:
            when = self._failed.get(key)
            if when is not None and time.monotonic() - when < RETRY_SECONDS:
                return None
        try:
            url = self._url(card_id, face)
        except CardDatabaseUnavailable:
            return None
        if url is None:
            return None
        path = self.images.path_for(card_id, face=face, size=SIZE, is_token=True)
        with self._gate:
            try:
                with self.client_factory()(self.settings.user_agent, timeout=15.0) as client:
                    ok = fetch_into(client, url, path, is_jpeg, f"Token picture {card_id}")
            except (httpx.HTTPError, OSError) as exc:
                log.info("Token picture %s waits until this computer is online (%s)", card_id, exc)
                ok = False
        if not ok:
            with self._lock:
                self._failed[key] = time.monotonic()
            return None
        return path

    def _url(self, card_id: str, face: int) -> str | None:
        rows = self.cards.image_rows([card_id])
        if not rows or not rows[0]["is_token"]:
            return None  # only tokens: a deck's own cards come with the deck (the art keeper)
        row = rows[0]
        if row["image_uris"]:
            faces = [json.loads(row["image_uris"])] if face == 0 else []
        else:
            faces = [f.get("image_uris") or {} for f in json.loads(row["card_faces"] or "[]")]
        if face >= len(faces):
            return None
        uris = faces[face]
        return scryfall_image(uris.get(SIZE) or uris.get("large") or uris.get("small"))
