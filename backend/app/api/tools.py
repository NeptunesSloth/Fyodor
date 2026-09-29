"""Host-computer tools: portable game packages and the local diagnostics export.

Everything here is local-only (the machine running Fyodor); nothing is ever uploaded anywhere.
"""

from __future__ import annotations

import platform
import sys
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from app import __version__
from app.api.deps import get_services, require_local
from app.logging_setup import RECENT_PROBLEMS
from app.services import Services
from app.storage.package import MAX_PACKAGE_BYTES, PackageError, export_package, import_package
from app.storage.save_format import SAVE_VERSION, SaveFormatError
from app.storage.saves import SaveNotFound

router = APIRouter(tags=["tools"], dependencies=[Depends(require_local)])
ServicesDep = Annotated[Services, Depends(get_services)]


@router.get("/saves/{save_id}/package")
def download_package(save_id: str, services: ServicesDep) -> Response:
    try:
        data, filename = export_package(
            services.saves, services.assets, services.macros, save_id,
            oracle_ids_of=lambda ids: {c["oracle_id"] for c in services.cards.get_many(ids).values() if c.get("oracle_id")})
    except SaveNotFound:
        raise HTTPException(404, "Save not found") from None
    except SaveFormatError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@router.post("/packages/import", status_code=201)
async def upload_package(request: Request, services: ServicesDep) -> dict[str, Any]:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_PACKAGE_BYTES:
            raise HTTPException(413, "Package is too large")
        chunks.append(chunk)
    try:
        return import_package(b"".join(chunks), services.saves, services.assets, services.macros,
                              history_limit=services.settings.history_limit)
    except PackageError as exc:
        raise HTTPException(422, str(exc)) from exc


def _count(services: Services, table: str) -> int:
    with services.app_db_lock:
        return int(services.app_db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608 - fixed names


@router.get("/diagnostics")
def diagnostics(services: ServicesDep, include_private: Annotated[bool, Query()] = False) -> JSONResponse:
    """A snapshot for troubleshooting. By default it contains no hands, libraries, decklists,
    card names in hidden zones or notes: only counts, versions, connection state and consistency
    checks. ``include_private=true`` (an explicit opt-in) adds full table states."""
    with services.app_db_lock:
        schema = services.app_db.execute("SELECT version FROM schema_version").fetchone()["version"]
    rooms = []
    for room in services.hub.rooms.values():
        item: dict[str, Any] = {
            "id": room.id, "mode": room.mode, "phase": room.phase, "revision": room.revision,
            "seats": {pid: s.presence() for pid, s in room.seats.items()},
        }
        if room.game is not None:
            st = room.game.state
            placed = [cid for ids in st.zones.values() for cid in ids]
            item.update({
                "seq": st.seq, "turn": st.turn.number, "players": len(st.players), "cards": len(st.cards),
                "history": {"entries": len(room.game.history.actions), "cursor": room.game.history.cursor},
                "problems": [
                    *(f"card {cid} is in {n} zones" for cid in set(placed) if (n := placed.count(cid)) > 1),
                    *(f"card {cid} is in no zone list" for cid in set(st.cards) - set(placed)),
                    *(f"zone lists unknown card {cid}" for cid in set(placed) - set(st.cards)),
                ][:50],
            })
            if include_private:
                item["state"] = st.model_dump(mode="json")
        rooms.append(item)
    body = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "includes_private_information": include_private,
        "app": {"version": __version__, "save_version": SAVE_VERSION, "app_db_schema": schema},
        "system": {"python": sys.version.split()[0], "platform": platform.platform(terse=True)},
        "settings": {"allow_network": services.settings.allow_network, "assistant_enabled": services.assistant is not None,
                     "frontend_bundled": services.settings.frontend_dist is not None,
                     "autosave_every": services.settings.autosave_every, "history_limit": services.settings.history_limit},
        "card_database": services.cards.stats(),
        "library": {t: _count(services, t) for t in ("decks", "saves", "assets", "macros", "game_results")},
        "rooms": rooms,
        "recent_problems": list(RECENT_PROBLEMS),
    }
    if include_private:
        body["decks"] = [d.model_dump(mode="json") for d in services.decks.list_all()]
    name = f"fyodor-diagnostics-{time.strftime('%Y%m%d-%H%M%S')}{'-PRIVATE' if include_private else ''}.json"
    return JSONResponse(body, headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})
