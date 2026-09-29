from __future__ import annotations

from fastapi import APIRouter, Request

from app import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    services = request.app.state.services
    return {"status": "ok", "version": __version__, **services.health()}
