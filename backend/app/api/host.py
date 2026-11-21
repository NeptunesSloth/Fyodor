"""Claiming the host session: the launcher opens the table with the host secret, the page posts it here once."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.deps import client_address, get_services, is_host_request, too_many_attempts
from app.hostauth import HOST_COOKIE
from app.services import Services

router = APIRouter(tags=["host"])
ServicesDep = Annotated[Services, Depends(get_services)]


class SessionBody(BaseModel):
    secret: str


@router.post("/host/session", status_code=204)
def claim_host_session(body: SessionBody, request: Request, services: ServicesDep) -> Response:
    # (the right secret is full authority and is never refused, however many wrong ones came from this address: behind a tunnel
    # every client, the host's browser too, can share one address)
    if not services.host_secret.matches(body.secret):
        ip = client_address(request)
        if services.host_limiter_addr.blocked(ip):
            raise too_many_attempts(services.host_limiter_addr.retry_after(ip))
        services.host_limiter_addr.fail(ip)
        raise HTTPException(403, "That is not this server's host secret")
    response = Response(status_code=204)
    # (no max-age: it ends with the browser session, and the secret itself ends with the server)
    response.set_cookie(HOST_COOKIE, services.host_secret.value, httponly=True, samesite="strict", path="/",
                        secure=request.url.scheme == "https")
    return response


@router.get("/host/session")
def host_session(request: Request) -> dict[str, bool]:
    """Is this browser the host's? (The page shows host tools, or where to get them, by this.)"""
    return {"host": is_host_request(request)}
