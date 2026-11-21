"""Which Host and Origin a request may carry.

Host: a page on another site can point its own name at this computer (DNS rebinding) and then read answers as if they were its
own; only an IP address, localhost, this computer's name or a configured name is served. Origin: a page on another site can make
the browser send a request or open a socket here; only this server's own origin, or a configured one, is let in.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urlsplit

DEFAULT_PORTS = {"http": 80, "https": 443}


def _split_host(host_header: str | None) -> tuple[str, int | None] | None:
    """A Host header as (lower-case host, port); None when it isn't a well-formed host[:port] (IPv6 literals are bracketed)."""
    if not host_header:
        return None
    host_header = host_header.strip().lower()
    if host_header.startswith("["):
        host, _, rest = host_header[1:].partition("]")
        port = rest[1:] if rest.startswith(":") else rest
        if rest and not rest.startswith(":"):
            return None
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            return None
    else:
        host, sep, port = host_header.partition(":")
        if not host or ":" in port or (sep and not port):
            return None
    if port and not (port.isascii() and port.isdigit()):
        return None
    return host, int(port) if port else None


def host_allowed(host_header: str | None, extra_hosts: Iterable[str]) -> bool:
    """An IP literal, ``localhost``, this computer's name (also with ``.local``, how some devices find it) or one of
    ``extra_hosts``; any port. Anything else, including a name that only ends with this computer's name, is refused."""
    parts = _split_host(host_header)
    if parts is None:
        return False
    host = parts[0]
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    me = socket.gethostname().lower()
    return host in {"localhost", me, f"{me}.local", *(h.lower() for h in extra_hosts)}


def _origin_key(origin: str) -> tuple[str, str, int] | None:
    """An Origin (or configured origin) as (scheme, host, port with the default filled in); None when it isn't one."""
    try:
        url = urlsplit(origin)
        port = url.port
    except ValueError:
        return None
    if url.scheme not in DEFAULT_PORTS or not url.hostname or url.path or url.query or url.fragment or url.username is not None:
        return None
    return url.scheme, url.hostname, port or DEFAULT_PORTS[url.scheme]


def origin_allowed(origin: str | None, host_header: str | None, extra: Iterable[str]) -> bool:
    """Is ``origin`` this server's own (the request's ``Host`` under http or https) or one of ``extra``? Compared whole, never
    as a prefix. No Origin, ``null`` and anything malformed are refused."""
    if not origin:
        return False
    key = _origin_key(origin)
    if key is None:
        return False
    scheme, host, port = key
    own = _split_host(host_header)
    if own is not None and own[0] == host and (own[1] or DEFAULT_PORTS[scheme]) == port:
        return True
    return any(key == _origin_key(e) for e in extra)
