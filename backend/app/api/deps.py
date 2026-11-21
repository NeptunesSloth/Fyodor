from __future__ import annotations

import ipaddress

from fastapi import HTTPException, Request, WebSocket

from app.hostauth import HOST_COOKIE
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


def is_host_request(request: Request | WebSocket) -> bool:
    """The host's browser, and only it: the one holding the host secret in its cookie (app/hostauth.py). Neither the peer address
    nor X-Forwarded-For is read: behind a tunnel every remote player connects from loopback, and a header can say anything."""
    services: Services = request.app.state.services
    return services.host_secret.matches(request.cookies.get(HOST_COOKIE))


def require_host(request: Request) -> None:
    if not is_host_request(request):
        raise HTTPException(403, "Open Fyodor from its launcher on the host computer to use host tools.")


# the ~100 call sites keep their names
is_local_request = is_host_request
require_local = require_host
