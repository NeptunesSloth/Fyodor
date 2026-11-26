from __future__ import annotations

from fastapi import APIRouter, Request

from app import __version__
from app.api.deps import is_host_request, is_tunnel_request

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict[str, object]:
    """Is the server up, and which version. The card database, open tables and recovery notices are the host's matters: only the
    host's browser sees them. Through the invite link the answer also says so (``tunnel``)."""
    out: dict[str, object] = {"status": "ok", "version": __version__}
    if is_host_request(request):
        return {**out, **request.app.state.services.health()}
    if is_tunnel_request(request):
        out["tunnel"] = True
    return out
