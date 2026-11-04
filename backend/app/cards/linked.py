"""Linked Scryfall images: the Magic card back and the mana symbols ({W}, {2/U}, {T} …).

Like the card art, they're linked from Scryfall and cached on the host, never shipped with Fyodor: the back is one JPEG in
``images/backs``, the symbols one SVG each in ``images/symbols`` with the list they came in (``symbology.json``). The host
serves them (``/api/images/card-back``, ``/api/symbols``) and every client falls back to drawing its own while they're missing
(offline before the first download).

When they're fetched (never with FYODOR_ALLOW_NETWORK=0):
- with the card database: each download or update also asks for the symbol list (new sets bring new symbols) and fetches what
  isn't cached yet;
- at start-up, when something is missing;
- on demand, when a client asks for one that's missing: in the background, at most every ``RETRY_SECONDS``.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx

from app.cards.downloader import download_card_back, fetch_into
from app.cards.images import SYMBOL_CODE_RE, ImageStore

if TYPE_CHECKING:
    from app.config import Settings

log = logging.getLogger(__name__)

DOWNLOADS = True  # (the test suite turns this off: no test reaches Scryfall unless it asks to)
RETRY_SECONDS = 600.0
MAX_SVG_BYTES = 64_000
SVG_HOSTS = ("scryfall.io", "scryfall.com")
# Shown with <img>, an SVG runs nothing; opened on its own it could. Scryfall's are plain shapes: anything active is refused.
_ACTIVE_SVG = re.compile(rb"<script|<foreignobject|<iframe|<embed|<object|javascript:|\son[a-z]+\s*=|href\s*=\s*[\"'](?!#)", re.I)


def is_plain_svg(body: bytes) -> bool:
    head = body.lstrip()[:200].lower()
    return (len(body) <= MAX_SVG_BYTES and (head.startswith(b"<svg") or head.startswith(b"<?xml")) and b"<svg" in body[:400].lower()
            and not _ACTIVE_SVG.search(body))


def symbol_code(svg_uri: object) -> str | None:
    """The cache name for a symbol's ``svg_uri`` (``…/card-symbols/WU.svg`` -> ``WU``); None for anything unexpected."""
    if not isinstance(svg_uri, str):
        return None
    url = urlsplit(svg_uri)
    host = (url.hostname or "").lower()
    path = PurePosixPath(url.path)
    if url.scheme != "https" or not any(host == h or host.endswith("." + h) for h in SVG_HOSTS) or ".." in url.path:
        return None
    return path.stem if path.suffix == ".svg" and SYMBOL_CODE_RE.match(path.stem) else None


def download_symbols(client: httpx.Client, store: ImageStore, api_base: str) -> int:
    """Ask Scryfall for its symbol list and fetch each SVG not cached yet. Returns how many symbols are cached afterwards."""
    res = client.get(f"{api_base.rstrip('/')}/symbology")
    res.raise_for_status()
    data = res.json().get("data")
    index = store.symbol_index()
    for entry in data if isinstance(data, list) else []:
        if not isinstance(entry, dict):
            continue
        symbol = entry.get("symbol")
        code = symbol_code(entry.get("svg_uri"))
        if not (isinstance(symbol, str) and 2 < len(symbol) <= 18 and symbol[0] == "{" and symbol[-1] == "}") or code is None:
            continue
        if fetch_into(client, entry["svg_uri"], store.symbol_path(code), is_plain_svg, f"Symbol {symbol}"):
            index[symbol[1:-1]] = {"svg": code, "english": str(entry.get("english") or "")[:120]}
    store.write_symbol_index(index)
    return len(index)


class LinkedAssets:
    """The host's card back and mana symbols: fetched with the card data, at start-up and on demand (see the module)."""

    def __init__(self, settings: Settings, images: ImageStore, client_factory: Callable[[], Callable[..., httpx.Client]]) -> None:
        self.settings = settings
        self.images = images
        self.client_factory = client_factory  # (read at each fetch: the tests swap the services' client)
        self.synchronous = False  # tests: do the work inline
        self.last_try: float | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def missing(self) -> bool:
        return self.images.card_back() is None or not self.images.symbol_index()

    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def fetch(self) -> dict[str, Any]:
        """Fetch now: the card back if it's missing, the symbol list and any symbol not cached yet. Failures are logged only."""
        with self.client_factory()(self.settings.user_agent, timeout=30.0) as client:
            back = download_card_back(client, self.images)
            try:
                symbols = download_symbols(client, self.images, self.settings.scryfall_api)
            except (httpx.HTTPError, ValueError, OSError) as exc:
                log.warning("Mana symbols download failed: %s", exc)
                symbols = len(self.images.symbol_index())
        return {"card_back": back, "symbols": symbols}

    def kick(self) -> None:
        """Fetch what's missing in the background, if this computer may go online and it wasn't tried a moment ago."""
        if not DOWNLOADS or not self.settings.allow_network or not self.missing():
            return
        with self._lock:
            now = time.monotonic()
            if self.busy() or (self.last_try is not None and now - self.last_try < RETRY_SECONDS):
                return
            self.last_try = now
            if not self.synchronous:
                self._thread = threading.Thread(target=self._work, name="linked-assets", daemon=True)
                self._thread.start()
                return
        self._work()

    def _work(self) -> None:
        try:
            got = self.fetch()
            log.info("Card back %s; %d mana symbols cached", "cached" if got["card_back"] else "not available yet", got["symbols"])
        except Exception:  # noqa: BLE001 - a background download must never take anything else down
            log.exception("Fetching the card back and mana symbols failed")
