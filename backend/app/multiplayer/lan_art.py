"""Art for a brought deck, from the player's own Fyodor over the LAN (docs/LAN_PLAY.md, "Finding a game").

At game night there may be no internet. A friend who saved their decks on their own Fyodor while online has the art cached
there; once they pick a deck at the host's table, the host fetches the images it lacks for that deck's printings from the
friend's server (the same ``/api/images/{id}`` the host serves its own from), in the background. Until they arrive the cards
show as proxies; then every client at the table is told to look again (``{"type": "art"}``: no card ids, which would tell
the others what is in the deck). Images only: real JPEGs, ``MAX_IMAGE_BYTES`` each, ``MAX_IMAGES`` per deck, never saved
with the game.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any

import httpx
from fastapi.concurrency import run_in_threadpool

from app.cards.images import UUID_RE, ImageStore

if TYPE_CHECKING:
    from app.cards.repository import CardRepository
    from app.multiplayer.hub import Room
    from app.services import Services

log = logging.getLogger(__name__)

MAX_IMAGES = 400  # faces per deck
MAX_IMAGE_BYTES = 3_000_000


def transport() -> httpx.BaseTransport | None:
    """The way to the player's server (the tests swap in their own)."""
    return None


def wanted(repo: CardRepository, store: ImageStore, printing_ids: list[str]) -> list[tuple[str, int, bool]]:
    """(printing, face, is_token) of every image these printings show that isn't here yet, at most ``MAX_IMAGES``."""
    ids = [i for i in dict.fromkeys(printing_ids) if isinstance(i, str) and UUID_RE.match(i)]
    out: list[tuple[str, int, bool]] = []
    cards = repo.get_many(ids) if ids else {}
    for pid in ids:
        card = cards.get(pid)
        if card is None:
            continue
        for face in range(max(1, min(int(card.get("image_faces") or 1), 4))):
            if not store.has(pid, face):
                out.append((pid, face, bool(card.get("is_token"))))
                if len(out) >= MAX_IMAGES:
                    return out
    return out


def fetch_art(origin: str, repo: CardRepository, store: ImageStore, printing_ids: list[str], *,
              transport: httpx.BaseTransport | None = None) -> list[str]:
    """Fetch the missing images of these printings from ``origin`` (a Fyodor on the LAN); returns the printings that got art."""
    jobs = wanted(repo, store, printing_ids)
    if not jobs:
        return []
    got: list[str] = []
    with httpx.Client(transport=transport, trust_env=False, timeout=httpx.Timeout(10.0), follow_redirects=False) as client:
        def one(job: tuple[str, int, bool]) -> str | None:
            pid, face, is_token = job
            try:
                with client.stream("GET", f"{origin}/api/images/{pid}", params={"face": face, "size": "normal", "fallback": 0}) as res:
                    # the printing's own picture only: never another printing's (-- same-card art --) kept as this one's
                    if (res.status_code != 200 or not res.headers.get("content-type", "").startswith("image/jpeg")
                            or res.headers.get("x-fyodor-art")):
                        return None
                    data = bytearray()
                    for chunk in res.iter_bytes():
                        data += chunk
                        if len(data) > MAX_IMAGE_BYTES:
                            return None
            except httpx.HTTPError:
                return None
            if not (data.startswith(b"\xff\xd8") and len(data) > 64):
                return None
            path = store.path_for(pid, face=face, is_token=is_token)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(bytes(data))
            os.replace(tmp, path)
            return pid

        got = [pid for pid in map(one, jobs) if pid]  # one at a time: a LAN is quick, and the player's computer stays responsive
    return list(dict.fromkeys(got))


_running: set[asyncio.Task[Any]] = set()


async def _bring(services: Services, room: Room, origin: str, printing_ids: list[str]) -> None:
    try:
        got = await run_in_threadpool(fetch_art, origin, services.cards, services.images, printing_ids, transport=transport())
    except Exception:  # noqa: BLE001 - art is a nicety: the deck plays with proxies
        log.info("Could not fetch art from the player's computer", exc_info=True)
        return
    if not got:
        return
    log.info("Fetched %d card images from a player's computer over the LAN", len(got))
    for conn in list(room.connections.values()):
        try:
            await conn.send({"type": "art"})
        except Exception:  # noqa: BLE001 - a closed socket: its client looks again on reconnect anyway
            log.debug("could not tell %s about new art", conn.id)


def bring_art(services: Services, room: Room, origin: str | None, printing_ids: list[str]) -> None:
    """Fetch, in the background, the art this table lacks for these printings from the player's own Fyodor at ``origin``."""
    if not origin or not printing_ids:
        return
    task = asyncio.get_running_loop().create_task(_bring(services, room, origin, list(printing_ids)))
    _running.add(task)
    task.add_done_callback(_running.discard)
