"""Managed custom assets over HTTP.

* Anyone at the table may *view* assets (they are table visuals) and upload a card back or a
  playmat for themselves (a seat token or the host computer is required).
* Renaming, replacing, duplicating and deleting happen on the host computer (Asset manager).
* Uploads are raw request bodies validated by content (PNG / JPEG / WEBP, 20 MB, 8192²).
  Files are served only by asset id — never by a client-supplied path.
"""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import get_services, is_local_request, require_local
from app.assets.store import KINDS, AssetNotFound
from app.assets.validate import MAX_BYTES, InvalidImage
from app.services import Services
from app.textutil import clean_text

router = APIRouter(tags=["assets"])
ServicesDep = Annotated[Services, Depends(get_services)]
PLAYER_KINDS = {"card_back", "playmat"}
_uploads: dict[str, list[float]] = {}


def _may_upload(request: Request, services: Services, token: str | None, kind: str) -> None:
    if is_local_request(request):
        return
    if kind not in PLAYER_KINDS:
        raise HTTPException(403, "Only card backs and playmats can be added from another device")
    if not token or not any(r.seat_for_token(token) not in (None, "__spectator__") for r in services.hub.rooms.values()):
        raise HTTPException(403, "Join a table first")
    ip = request.client.host if request.client else "?"
    now = time.monotonic()
    recent = [t for t in _uploads.get(ip, []) if now - t < 600]
    if len(recent) >= 30:
        raise HTTPException(429, "Too many uploads; wait a few minutes")
    _uploads[ip] = [*recent, now]


async def _body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise HTTPException(413, f"Images are limited to {MAX_BYTES // 1024 // 1024} MB")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BYTES:
            raise HTTPException(413, f"Images are limited to {MAX_BYTES // 1024 // 1024} MB")
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("/assets")
def list_assets(request: Request, services: ServicesDep,
                kind: Annotated[str | None, Query(max_length=20)] = None) -> list[dict[str, Any]]:
    items = services.assets.list(kind)
    if is_local_request(request):
        used = services.assets_in_use()
        for a in items:
            a["used_by"] = used.get(a["id"], [])
    return items


@router.post("/assets", status_code=201)
async def upload_asset(request: Request, services: ServicesDep, kind: Annotated[str, Query(max_length=20)],
                       name: Annotated[str, Query(max_length=80)] = "Untitled",
                       x_seat_token: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    if kind not in KINDS:
        raise HTTPException(422, f"Unknown asset type {kind!r}")
    _may_upload(request, services, x_seat_token, kind)
    data = await _body(request)
    try:
        return services.assets.add(data, kind=kind, name=clean_text(name, 80) or "Untitled")
    except InvalidImage as exc:
        raise HTTPException(415, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/assets/{asset_id}/file")
def asset_file(asset_id: str, services: ServicesDep) -> FileResponse:
    try:
        path, mime, sha = services.assets.path(asset_id)
    except AssetNotFound:
        raise HTTPException(404, "No such asset") from None
    if not path.is_file():
        raise HTTPException(404, "Asset file is missing")
    # URLs carry ?v=<sha>, so a cached copy is always the right one (LAN clients keep it offline).
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "public, max-age=31536000, immutable",
                                                       "ETag": f'"{sha}"', "X-Content-Type-Options": "nosniff"})


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str, services: ServicesDep) -> dict[str, Any]:
    try:
        return services.assets.get(asset_id)
    except AssetNotFound:
        raise HTTPException(404, "No such asset") from None


class AssetPatch(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.patch("/assets/{asset_id}")
def rename_asset(asset_id: str, body: AssetPatch, request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    try:
        return services.assets.rename(asset_id, clean_text(body.name, 80) or "Untitled")
    except AssetNotFound:
        raise HTTPException(404, "No such asset") from None


@router.put("/assets/{asset_id}/file")
async def replace_asset(asset_id: str, request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    data = await _body(request)
    try:
        result = services.assets.replace(asset_id, data)
    except AssetNotFound:
        raise HTTPException(404, "No such asset") from None
    except InvalidImage as exc:
        raise HTTPException(415, str(exc)) from exc
    for room in services.hub.rooms.values():  # tables using it pick up the new image
        if room.started:
            await services.hub.broadcast(room)
    return result


@router.post("/assets/{asset_id}/duplicate", status_code=201)
def duplicate_asset(asset_id: str, request: Request, services: ServicesDep) -> dict[str, Any]:
    require_local(request)
    try:
        return services.assets.duplicate(asset_id)
    except AssetNotFound:
        raise HTTPException(404, "No such asset") from None


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: str, request: Request, services: ServicesDep,
                 force: Annotated[bool, Query()] = False) -> Response:
    require_local(request)
    used = services.assets_in_use().get(asset_id, [])
    if used and not force:
        raise HTTPException(409, "In use: " + "; ".join(used))
    try:
        services.assets.delete(asset_id)
    except AssetNotFound:
        raise HTTPException(404, "No such asset") from None
    return Response(status_code=204)
