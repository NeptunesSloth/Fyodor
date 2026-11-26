"""FastAPI application factory.

Run from ``backend/`` with ``uvicorn --factory app.main:create_app``.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import __version__
from app.api import assets, backups, cards, decks, games, health, macros, night, pod, practice, rules, tools
from app.api import bot as bot_api  # -- test opponent --
from app.api import shortcut as shortcut  # -- desktop shortcut --
from app.api import updates as updates  # -- install update --
from app.api.deps import host_ok, is_https, origin_ok
from app.api.host import router as host_router
from app.api.lan import router as lan_router
from app.api.spectate import router as spectate_router
from app.api.teach import router as teach_router  # -- Teach Fyodor --
from app.assets import validate as asset_validate
from app.cards.repository import CardDatabaseUnavailable
from app.config import Settings, get_settings
from app.decks import archidekt
from app.logging_setup import configure_logging
from app.multiplayer import handoff
from app.multiplayer.discovery import Discovery
from app.multiplayer.hub import GameNotStarted
from app.services import Services
from app.storage import backup, package, taught, update

log = logging.getLogger(__name__)

# Everything is served from this origin; no third-party scripts, fonts or trackers.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self' ws: wss:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# -- request body limit -- no route takes a body larger than this unless it is named below. Pydantic's max_length checks run
# only after the whole body is read and parsed, so without it one request of hundreds of megabytes is a memory spike.
BODY_LIMIT = 256 * 1024
TOO_LARGE = "That request is too large."
# Larger allowances, each for routes that bound their own bodies (path, matched whole -> bytes); every other path gets BODY_LIMIT.
# The route keeps its own check; the allowance is never larger than the route's own bound (plus room for JSON's escaping).
_DECK_TEXT = 200_000  # a pasted deck list: DeckImportRequest.text and LobbyDeckIn.text, in characters
BODY_ALLOWANCES: tuple[tuple[re.Pattern[str], int], ...] = tuple((re.compile(p), n) for p, n in (
    # asset upload and replacement: the route streams the body and stops at the image limit (api/assets.py `_body`)
    (r"/api/assets(/[^/]+/file)?", asset_validate.MAX_BYTES),
    # a player's Fyodor bringing its deck library: the route streams it and stops at handoff.MAX_BYTES (api/lan.py)
    (r"/api/lan/handoff", handoff.MAX_BYTES),
    # which printings the host lacks: up to 20,000 ids (MissingIn), sent with that same library
    (r"/api/lan/handoff/missing", handoff.MAX_BYTES),
    # host only: a backup to restore, streamed to a file and stopped at MAX_BACKUP_BYTES (api/backups.py)
    (r"/api/backups/restore", backup.MAX_BACKUP_BYTES),
    # host only: an update, streamed and stopped at MAX_UPLOAD_BYTES (api/updates.py)
    (r"/api/update/upload", update.MAX_UPLOAD_BYTES),
    # host only: a game package, streamed and stopped at MAX_PACKAGE_BYTES (api/tools.py)
    (r"/api/packages/import", package.MAX_PACKAGE_BYTES),
    # host only: a Teach Fyodor file, at most taught.MAX_FILE_BYTES (api/teach.py checks it after reading; this stops it while reading)
    (r"/api/teach/import", taught.MAX_FILE_BYTES),
    # host only: this browser's "My decks", at most MAX_BROWSER_DECKS_BYTES as JSON (storage/backup.py `browser_decks_blob`)
    (r"/api/(browser-decks|backups)", backup.MAX_BROWSER_DECKS_BYTES + BODY_LIMIT),
    # host only (the decks router): an import may carry saved Archidekt JSON (DeckImportRequest.json, archidekt.MAX_JSON_BYTES
    # characters) or a pasted list; twice the characters for JSON's escapes (\" \\ \n) and accented names
    (r"/api/decks(/.*)?", 2 * (archidekt.MAX_JSON_BYTES + _DECK_TEXT) + BODY_LIMIT),
    # a seat choosing or queueing a deck: LobbyDeckIn.json (2,000,000 characters) or a list, and up to 20,000 collection entries
    # (LobbyDeckIn.collection, CollectionIn: a few hundred bytes each)
    (r"/api/games/[^/]+/(lobby/(deck|import|collection)|load-deck|next-deck)",
     2 * (2_000_000 + _DECK_TEXT) + 20_000 * 512),
))


def body_limit(path: str) -> int:
    """The most bytes a request to ``path`` may send: its allowance, or BODY_LIMIT."""
    return next((n for pattern, n in BODY_ALLOWANCES if pattern.fullmatch(path)), BODY_LIMIT)


class BodyLimit:
    """Refuses (413) a request body over ``body_limit`` of its path, before any route reads it: a declared ``Content-Length`` over it
    at once, and a body without one (chunked), or with one that understates it, counted as it is read. Plain ASGI, so it sees the
    body as it arrives; sockets pass straight through."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = body_limit(scope["path"])
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.strip().isdigit() and int(declared) > limit:
            await JSONResponse({"detail": TOO_LARGE}, status_code=413)(scope, receive, send)
            return
        seen = 0

        async def counted() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    # an HTTPException: FastAPI passes it on from reading the body (anything else becomes a 400), and the
                    # exception middleware inside this one answers it as a 413
                    raise HTTPException(413, TOO_LARGE)
            return message

        await self.app(scope, counted, send)
UNKNOWN_HOST = "This address is not one Fyodor answers to. Use http://<IP>:<port>, or add the name to FYODOR_EXTRA_HOSTS."


def _same_site_request(request: Request) -> bool:
    """May this state-changing request go on? Not when the browser says it is cross-site. No Origin and no Sec-Fetch-Site is not a
    browser (the LAN handoff, scripts): let through. Otherwise a same-origin request or a typed navigation, or an allowed Origin."""
    site = request.headers.get("sec-fetch-site")
    if site == "cross-site":
        return False
    if site is None and "origin" not in request.headers:
        return True
    return site in {"same-origin", "none"} or origin_ok(request)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info("Fyodor %s starting; data dir %s", __version__, settings.data_dir)
        app.state.services.autobackups.start()
        app.state.services.art_keeper.start()  # decks saved while offline get their art once this computer is online
        app.state.services.linked.kick()  # the card back and mana symbols, if they're missing and this computer may go online
        await app.state.discovery.start()  # LAN mode only; never stops the server
        yield
        app.state.discovery.stop()
        app.state.services.close()

    # the API documents itself only for development (FYODOR_DEV_TOOLS=1): the routes do not exist otherwise
    app = FastAPI(
        title="Fyodor MTG Tabletop", version=__version__, lifespan=lifespan,
        docs_url="/docs" if settings.dev_tools else None,
        redoc_url="/redoc" if settings.dev_tools else None,
        openapi_url="/openapi.json" if settings.dev_tools else None,
    )
    app.state.services = Services(settings)
    app.state.discovery = Discovery(settings, lambda: app.state.services.hub.rooms.values())

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # inside the Host/Origin guard (a refused Host is a 400 whatever its body) and the headers (a 413 carries them), outside every route
    app.add_middleware(BodyLimit)
    # added last, so it runs first: the Host (DNS rebinding) before anything else, then the Origin of a state-changing request
    @app.middleware("http")
    async def net_guard(request: Request, call_next: Any) -> Response:
        if not host_ok(request):  # (most often a person who typed a name into the address bar: say what to do, in plain words)
            return PlainTextResponse(UNKNOWN_HOST, status_code=400)
        if request.method in UNSAFE_METHODS and not _same_site_request(request):
            return JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
        response: Response = await call_next(request)
        return response

    # added after net_guard, so it is the outermost: its own refusals carry the headers too
    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Content-Security-Policy", CSP)
        if is_https(request):  # never over plain http (a browser would hold the host to https): no includeSubDomains, no preload
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    app.include_router(health.router, prefix="/api")
    app.include_router(cards.router, prefix="/api")
    app.include_router(decks.router, prefix="/api")
    app.include_router(games.router, prefix="/api")
    app.include_router(bot_api.router, prefix="/api")  # -- test opponent --
    app.include_router(night.router, prefix="/api")
    app.include_router(practice.router, prefix="/api")
    app.include_router(spectate_router, prefix="/api")  # (spectator activities)
    app.include_router(pod.router, prefix="/api")
    app.include_router(assets.router, prefix="/api")
    app.include_router(macros.router, prefix="/api")
    app.include_router(teach_router, prefix="/api")  # -- Teach Fyodor -- (app/api/teach.py)
    app.include_router(tools.router, prefix="/api")
    app.include_router(backups.router, prefix="/api")
    app.include_router(shortcut.router, prefix="/api")  # -- desktop shortcut -- (app/api/shortcut.py)
    app.include_router(updates.router, prefix="/api")  # -- install update -- (app/api/updates.py)
    app.include_router(rules.router, prefix="/api")
    app.include_router(host_router, prefix="/api")  # claiming the host session (app/api/host.py)
    app.include_router(lan_router, prefix="/api")  # finding tables on the network
    app.add_api_websocket_route("/ws/games/{game_id}", games.game_socket)

    @app.exception_handler(GameNotStarted)
    async def _not_started(_: Request, exc: GameNotStarted) -> JSONResponse:
        return JSONResponse({"detail": str(exc), "code": "lobby"}, status_code=409)

    @app.exception_handler(CardDatabaseUnavailable)
    async def _no_card_db(_: Request, exc: CardDatabaseUnavailable) -> JSONResponse:
        return JSONResponse({"detail": str(exc), "code": "card_db_missing"}, status_code=503)

    _mount_frontend(app, settings)
    return app


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    """Serve the built frontend (if present) so LAN clients only need http://HOST:PORT."""
    dist = settings.frontend_dist
    if dist is None:
        return
    index = dist / "index.html"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    # the page itself is asked for again on every load (the hashed assets it names can be kept): a window kept from an older
    # build otherwise opened that build's page against the new server
    @app.get("/", include_in_schema=False)
    def spa_index() -> FileResponse:
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

