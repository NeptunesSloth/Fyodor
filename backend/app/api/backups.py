"""BACKUP FYODOR / restore (host computer only)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.deps import get_services, require_local
from app.services import Services
from app.storage.backup import (
    MAX_BACKUP_BYTES,
    BackupError,
    backup_path,
    create_backup,
    list_backups,
    stage_restore,
)

router = APIRouter(tags=["backups"])
ServicesDep = Annotated[Services, Depends(get_services)]


@router.get("/backups")
def get_backups(request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    return {"backups": list_backups(services.settings.data_dir), "recovery": services.health().get("recovery")}


@router.post("/backups", status_code=201)
def make_backup(request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    return create_backup(services.settings.data_dir, services.app_db, services.app_db_lock, services.settings.assets_dir)


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
