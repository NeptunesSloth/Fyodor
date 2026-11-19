"""FastAPI application factory.

Run from ``backend/`` with ``uvicorn --factory app.main:create_app``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import assets, backups, cards, decks, games, health, macros, night, pod, practice, rules, tools
from app.api import bot as bot_api  # -- test opponent --
from app.api import updates as updates  # -- install update --
from app.api.lan import router as lan_router
from app.api.spectate import router as spectate_router
from app.api.teach import router as teach_router  # -- Teach Fyodor --
from app.cards.repository import CardDatabaseUnavailable
from app.config import Settings, get_settings
from app.logging_setup import configure_logging
from app.multiplayer.discovery import Discovery
from app.multiplayer.hub import GameNotStarted
from app.services import Services

log = logging.getLogger(__name__)

# Everything is served from this origin; no third-party scripts, fonts or trackers.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self' ws: wss:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


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

    app = FastAPI(title="Fyodor MTG Tabletop", version=__version__, lifespan=lifespan)
    app.state.services = Services(settings)
    app.state.discovery = Discovery(settings, lambda: app.state.services.hub.rooms.values())

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Content-Security-Policy", CSP)
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
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
    app.include_router(updates.router, prefix="/api")  # -- install update -- (app/api/updates.py)
    app.include_router(rules.router, prefix="/api")
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

