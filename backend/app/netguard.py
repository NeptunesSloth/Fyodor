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
        if rest == ":" or "%" in host:  # (a zone id never belongs in a Host, and ipaddress takes any text after the '%')
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


def own_names() -> frozenset[str]:
    """``localhost`` and this computer's names, lower case: its bare name, that name with ``.local`` (how some devices find it) and
    its full name on the network (``socket.getfqdn()``: ``desktop-42.lan``, ``.home``, ``.localdomain``, the name a home router hands
    out, which a pod may have bookmarked)."""
    me = socket.gethostname().lower()
    return frozenset({"localhost", me, f"{me}.local", socket.getfqdn().lower()})


OWN_NAMES = own_names()  # worked out once at start (getfqdn may ask the network's name service)


def host_allowed(host_header: str | None, extra_hosts: Iterable[str]) -> bool:
    """An IP literal, one of ``OWN_NAMES`` or one of ``extra_hosts``; any port. Anything else, including a name that only ends with
    this computer's name, is refused."""
    parts = _split_host(host_header)
    if parts is None:
        return False
    host = parts[0]
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    return host in OWN_NAMES or host in {h.lower() for h in extra_hosts}


# scheme://host[:port] and nothing else: no path, query, fragment, userinfo or whitespace; a port without a leading zero; a host that is a
# name, an IPv4 address or a bracketed IPv6 address. (Matched on the raw string, ASCII only and case-insensitively: a browser sends lower case, a configured one may not, and a look-alike such as the Kelvin sign is not an ASCII letter.)
_ORIGIN = re.compile(r"(https?)://(\[[0-9a-f:.]+\]|[a-z0-9._-]+)(?::([1-9][0-9]{0,4}))?", re.ASCII | re.IGNORECASE)


def _origin_key(origin: str) -> tuple[str, str, int] | None:
    """An Origin (or configured origin) as (scheme, host, port with the default filled in); None unless it is exactly the serialization
    a browser writes, ``scheme://host[:port]``."""
    match = _ORIGIN.fullmatch(origin)
    if match is None:
        return None
    scheme, host, port = match.group(1).lower(), match.group(2).lower(), match.group(3)
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


# -- invite over the internet -- what the tunnel port serves (app/main.py net_guard): the page, and what a remote player at a shared
# table needs; anything else there is a 404. (methods, the path matched whole). A route added later is outside this list until it
# is named here, and one it would let through fails tests/test_tunnel_routes.py until it is added to the frozen set there.
_GAME = r"/api/games/(?P<game_id>[^/]+)"
TUNNEL_ROUTES: tuple[tuple[frozenset[str], re.Pattern[str]], ...] = tuple(
    (frozenset(methods.split()), re.compile(pattern)) for methods, pattern in (
        ("GET", r"/"),  # the built page (_mount_frontend serves only these two)
        ("GET", r"/assets/.+"),
        ("GET", r"/api/health"),
        ("GET", r"/api/host/session"),  # (always {"host": false} here; the page asks)
        ("POST", r"/api/join"),
        ("GET", r"/api/games"),  # (always [] here)
        ("GET", r"/api/cards/(search|autocomplete|glossary|(?!stats\Z)[^/]+|[^/]+/printings)"),  # (not the database's stats)
        ("POST", r"/api/cards/batch"),
        ("GET", r"/api/images/.+"),
        ("GET", r"/api/symbols(/[^/]+\.svg)?"),
        ("GET", r"/api/assets/[^/]+/file"),
        ("GET", r"/api/rules/(support|coverage)"),
        # the pod's card macros (read-only definitions): the game screen loads them for every seat (app/api/macros.py). Accepted: a
        # stranger can read them, as can anyone on the LAN.
        ("GET", r"/api/macros"),
        # a table and everything under it, but its host's tools (and the turn clock's), saving, the assistant, the rules lab, sharing and the test opponent
        # (a trailing '/' too, so those are a 404 rather than redirect_slashes' 307). Only the methods those routes use: HEAD and
        # OPTIONS are a 404. Accepted: for a shared table, a stranger without a seat can read its summary (no code), GET /result and
        # what the routes themselves answer without a seat. tests/test_tunnel_routes.py freezes the whole set of allowed routes.
        ("GET POST DELETE", _GAME + r"(/(?!(save|assistant|rules/scenario|host/.*|share|clock|lobby/bot|bot(/.*)?)/?\Z).+)?"),
    ))


def tunnel_route(method: str, path: str) -> tuple[bool, str | None]:
    """May ``method`` ``path`` be asked for on the tunnel port, and which table does it name (None: none)? (The game socket is
    checked in game_socket: middleware never sees it.)"""
    for methods, pattern in TUNNEL_ROUTES:
        match = pattern.fullmatch(path)
        if match is not None and method.upper() in methods:
            return True, match.groupdict().get("game_id")
    return False, None


UNKNOWN_TUNNEL_CLIENT = "tunnel:unknown"


def cf_client_key(value: str | None) -> str:
    """The limiter key of a visitor through the tunnel, from Cloudflare's ``CF-Connecting-IP`` (one address; Cloudflare refuses a
    client's own copy of the header, so what reaches us is Cloudflare's). An IPv4 address as text (an IPv4-mapped IPv6 as its IPv4);
    an IPv6 address as its /64, the block one home or phone is given, so walking its own addresses buys no fresh budget. Missing
    or unparseable: one shared bucket, ``tunnel:unknown`` (fails closed: it never escapes the limits)."""
    try:
        ip = ipaddress.ip_address((value or "").strip())
    except ValueError:
        return UNKNOWN_TUNNEL_CLIENT
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.IPv6Network((ip, 64), strict=False))
    return str(ip)


class AttemptLimiter:
    """Guesses allowed per key (an address, a room code): ``max_failures`` failures within ``window`` seconds block the key until the
    oldest of them is ``window`` old. Only failures count, and they leave only by expiring: the app never calls ``succeed`` (a key may
    be shared by people behind one address, and a guesser's success must not buy a fresh budget); ``undo_last`` only takes back a
    failure recorded ahead of a check that then succeeded. In memory, pure; ``clock`` is injected."""

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

    def undo_last(self, key: str) -> None:
        """Drop the newest failure of ``key`` (none: nothing happens). /api/join records a failure before it checks the password (so
        concurrent guesses are counted before any is hashed) and gives it back here when the password was right. Failures of one key
        are interchangeable times: with others recorded meanwhile, the count drops by exactly one and the one left is the older."""
        failures = self._recent(key)
        if failures is None:
            return
        failures.pop()
        if not failures:
            del self._failures[key]

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
