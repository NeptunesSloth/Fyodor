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
    ip = client_address(request)
    guesses = services.join_limiter_addr  # (one budget with joins: it is the same address guessing at something)
    if guesses.blocked(ip):  # (before the secret is compared)
        raise too_many_attempts(guesses.retry_after(ip))
    if not services.host_secret.matches(body.secret):
        guesses.fail(ip)
        raise HTTPException(403, "That is not this server's host secret")
    guesses.succeed(ip)
    response = Response(status_code=204)
    # (no max-age: it ends with the browser session, and the secret itself ends with the server)
    response.set_cookie(HOST_COOKIE, services.host_secret.value, httponly=True, samesite="strict", path="/",
                        secure=request.url.scheme == "https")
    return response


@router.get("/host/session")
def host_session(request: Request) -> dict[str, bool]:
    """Is this browser the host's? (The page shows host tools, or where to get them, by this.)"""
    return {"host": is_host_request(request)}
