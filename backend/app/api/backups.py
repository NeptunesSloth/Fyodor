"""BACKUP FYODOR / restore (host computer only)."""

from __future__ import annotations

import threading
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import get_services, require_local
from app.services import Services
from app.storage.backup import (
    MAX_BACKUP_BYTES,
    BackupError,
    backup_path,
    list_backups,
    restore_pending,
    stage_restore,
    take_restored_browser_decks,
)

router = APIRouter(tags=["backups"])
ServicesDep = Annotated[Services, Depends(get_services)]


@router.get("/backups")
def get_backups(request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    return {"backups": list_backups(services.settings.data_dir), "recovery": services.health().get("recovery"),
            "auto": services.autobackups.status(), "restore_pending": restore_pending(services.settings.data_dir)}


class BackupBody(BaseModel):
    browser_decks: list[dict[str, Any]] | None = None  # this browser's "My decks" (browser storage), carried along


@router.post("/backups", status_code=201)
def make_backup(request: Request, services: ServicesDep, body: BackupBody | None = None) -> dict[str, Any]:
    require_local(request)
    try:
        return services.backup(browser_decks=body.browser_decks if body else None)
    except BackupError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/restored-decks")
def restored_decks(request: Request, services: ServicesDep) -> dict[str, Any]:
    """The "My decks" a restore brought back, for the host's browser to merge in (then forgotten)."""
    require_local(request)
    return {"decks": take_restored_browser_decks(services.settings.data_dir, consume=False)}


@router.delete("/restored-decks", status_code=204)
def forget_restored_decks(request: Request, services: ServicesDep) -> None:
    require_local(request)
    take_restored_browser_decks(services.settings.data_dir, consume=True)


@router.get("/backups/{name}")
def download_backup(name: str, request: Request, services: ServicesDep) -> FileResponse:
    require_local(request)
    try:
        path = backup_path(services.settings.data_dir, name)
    except BackupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, media_type="application/zip", filename=path.name)


@router.post("/backups/{name}/restore")
def restore_listed(name: str, request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    try:
        path = backup_path(services.settings.data_dir, name)
        return stage_restore(services.settings.data_dir, path.read_bytes())
    except BackupError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/backups/restore")
async def restore_upload(request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BACKUP_BYTES:
            raise HTTPException(413, "Backup is too large")
        chunks.append(chunk)
    try:
        return stage_restore(services.settings.data_dir, b"".join(chunks))
    except BackupError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/restart", status_code=202)
def restart(request: Request) -> dict[str, Any]:
    """Restart Fyodor in place (to finish a restore): the launcher stops the server and starts it again in the same
    program, so nobody has to find and close the window running it. Only when started by the launcher."""
    require_local(request)
    again = getattr(request.app.state, "request_restart", None)
    if again is None:
        raise HTTPException(409, "Restart Fyodor yourself: close the window running it and start it again.")
    threading.Timer(0.4, again).start()  # after this answer has gone out
    return {"restarting": True}
