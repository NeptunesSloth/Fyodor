"""Which Host and Origin a request may carry.

Host: a page on another site can point its own name at this computer (DNS rebinding) and then read answers as if they were its
own; only an IP address, localhost, this computer's name or a configured name is served. Origin: a page on another site can make
the browser send a request or open a socket here; only this server's own origin, or a configured one, is let in.
"""

from __future__ import annotations

import ipaddress
import math
import re
import socket
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Iterable

DEFAULT_PORTS = {"http": 80, "https": 443}
MAX_KEYS = 10_000  # a limiter never remembers more keys than this; the one longest without a failure is dropped first


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
        if rest == ":":
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


# scheme://host[:port] and nothing else: no path, query, fragment, userinfo or whitespace; a port without a leading zero; a host that is a
# name, an IPv4 address or a bracketed IPv6 address. (Matched case-insensitively: a browser sends lower case, a configured one may not.)
_ORIGIN = re.compile(r"(https?)://(\[[0-9a-f:.]+\]|[a-z0-9._-]+)(?::([1-9][0-9]{0,4}))?", re.ASCII)


def _origin_key(origin: str) -> tuple[str, str, int] | None:
    """An Origin (or configured origin) as (scheme, host, port with the default filled in); None unless it is exactly the serialization
    a browser writes, ``scheme://host[:port]``."""
    match = _ORIGIN.fullmatch(origin.lower())
    if match is None:
        return None
    scheme, host, port = match.groups()
    if host.startswith("["):
        host = host[1:-1]
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            return None
    if port and int(port) > 65535:
        return None
    return scheme, host, int(port) if port else DEFAULT_PORTS[scheme]


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


class AttemptLimiter:
    """Guesses allowed per key (an address, a room code): ``max_failures`` failures within ``window`` seconds block the key until the
    oldest of them is ``window`` old. Only failures count, a success clears the key. In memory, pure; ``clock`` is injected."""

    def __init__(self, max_failures: int, window: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_failures = max_failures
        self.window = window
        self._clock = clock
        self._failures: OrderedDict[str, deque[float]] = OrderedDict()  # key -> failure times, oldest first; keys by last failure

    def _recent(self, key: str) -> deque[float] | None:
        """The failures of ``key`` still inside the window (expired ones dropped; the key too when none is left), None if no key."""
        failures = self._failures.get(key)
        if failures is None:
            return None
        cutoff = self._clock() - self.window
        while failures and failures[0] <= cutoff:
            failures.popleft()
        if not failures:
            del self._failures[key]
            return None
        return failures

    def blocked(self, key: str) -> bool:
        failures = self._recent(key)
        return failures is not None and len(failures) >= self.max_failures

    def fail(self, key: str) -> None:
        failures = self._recent(key)
        if failures is None:
            failures = self._failures[key] = deque()
        failures.append(self._clock())
        while len(failures) > self.max_failures:  # (more are never needed to stay blocked)
            failures.popleft()
        self._failures.move_to_end(key)
        while len(self._failures) > MAX_KEYS:
            self._failures.popitem(last=False)

    def succeed(self, key: str) -> None:
        # (nothing in app calls this: a key may be shared by people behind one address, so failures only expire with the window)
        self._failures.pop(key, None)

    def retry_after(self, key: str) -> int:
        """Whole seconds until the oldest counted failure of ``key`` expires; at least 1."""
        failures = self._recent(key)
        if failures is None:
            return 1
        return max(1, math.ceil(failures[0] + self.window - self._clock()))


class ConnectionCaps:
    """How many connections one key (an address, a seat) may hold open at once: ``acquire`` takes a slot (False when ``per_key`` are
    taken), ``release`` gives one back. The caller releases exactly what it acquired; a stray release never goes below zero. In memory."""

    def __init__(self, per_key: int) -> None:
        self.per_key = per_key
        self._held: dict[str, int] = {}

    def acquire(self, key: str) -> bool:
        held = self._held.get(key, 0)
        if held >= self.per_key:
            return False
        self._held[key] = held + 1
        return True

    def release(self, key: str) -> None:
        held = self._held.get(key, 0)
        if held > 1:
            self._held[key] = held - 1
        else:
            self._held.pop(key, None)

    def count(self, key: str) -> int:
        return self._held.get(key, 0)

    def total(self) -> int:
        return sum(self._held.values())
