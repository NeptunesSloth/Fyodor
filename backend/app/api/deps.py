from __future__ import annotations

import ipaddress

from fastapi import HTTPException, Request, WebSocket

from app.services import Services


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


def _peer_is_loopback(host: str | None, forwarded_for: str | None) -> bool:
    if host == "testclient":  # starlette TestClient
        host = "127.0.0.1"
    try:
        loopback = host is not None and ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if loopback and forwarded_for:
        # Requests relayed by the local dev proxy carry the real client address.
        first = forwarded_for.split(",")[0].strip()
        try:
            return ipaddress.ip_address(first).is_loopback
        except ValueError:
            return False
    return loopback


def is_local_request(request: Request | WebSocket) -> bool:
    client = request.client
    return _peer_is_loopback(client.host if client else None, request.headers.get("x-forwarded-for"))


def require_local(request: Request) -> None:
    if not is_local_request(request):
        raise HTTPException(403, "Only available on the host computer")
