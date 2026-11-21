from __future__ import annotations

import ipaddress

from fastapi import HTTPException, Request, WebSocket

from app.hostauth import HOST_COOKIE
from app.netguard import host_allowed, origin_allowed
from app.services import Services


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


def _addr(text: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        ip = ipaddress.ip_address((text or "").strip())
    except ValueError:
        return None
    return ip.ipv4_mapped or ip if isinstance(ip, ipaddress.IPv6Address) else ip  # ::ffff:1.2.3.4 is 1.2.3.4


def _resolve(peer: str | None, xff: str | None, trusted: tuple[str, ...]) -> str:
    """The client behind `peer`: X-Forwarded-For is believed only when the peer is a configured proxy, and then the rightmost entry that
    is not itself a proxy is the client (what the nearest proxy saw; anything left of it can be forged). An unparseable entry, or a
    peer that is not an IP, gives the peer back. No peer at all gives "", one shared bucket for limits."""
    if not peer:
        return ""
    ip = _addr(peer)
    if ip is None:
        return peer
    nets = [ipaddress.ip_network(t, strict=False) for t in trusted]
    if not xff or not any(ip in n for n in nets):
        return str(ip)
    for entry in reversed(xff.split(",")):
        hop = _addr(entry)
        if hop is None:
            return str(ip)
        if not any(hop in n for n in nets):
            return str(hop)
    return str(ip)


def client_address(request: Request | WebSocket) -> str:
    """Where this request really came from, for rate limits and logs only (never authority: that is the host secret, is_host_request).
    The peer address, or behind a configured proxy (FYODOR_TRUSTED_PROXIES) the client it reports; "" when the framework gives no peer."""
    peer = request.client.host if request.client else None
    services: Services = request.app.state.services
    return _resolve(peer, request.headers.get("x-forwarded-for"), services.settings.trusted_proxies)


def host_ok(request: Request | WebSocket) -> bool:
    """Does the request name a host this server answers to (DNS rebinding guard, app/netguard.py)?"""
    services: Services = request.app.state.services
    return host_allowed(request.headers.get("host"), services.settings.extra_hosts)


def origin_ok(request: Request | WebSocket) -> bool:
    """Is the request's Origin this server's own, a configured dev origin (settings.cors_origins) or one in services.extra_origins?"""
    services: Services = request.app.state.services
    extra = (*services.settings.cors_origins, *services.extra_origins)
    return origin_allowed(request.headers.get("origin"), request.headers.get("host"), extra)


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
