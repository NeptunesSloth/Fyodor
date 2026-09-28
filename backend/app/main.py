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
from app.api import assets, cards, decks, games, health, pod
from app.cards.repository import CardDatabaseUnavailable
from app.config import Settings, get_settings
from app.logging_setup import configure_logging
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
        yield
        app.state.services.close()

    app = FastAPI(title="Fyodor MTG Tabletop", version=__version__, lifespan=lifespan)
    app.state.services = Services(settings)

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
    app.include_router(pod.router, prefix="/api")
    app.include_router(assets.router, prefix="/api")
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

    @app.get("/", include_in_schema=False)
    def spa_index() -> FileResponse:
        return FileResponse(index)

