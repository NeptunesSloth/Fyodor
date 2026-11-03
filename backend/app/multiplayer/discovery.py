"""Finding Fyodor tables on the local network (docs/LAN_PLAY.md, "Finding a game"). Standard library only.

A server that listens on the LAN runs a small UDP **beacon**: a device asks with one datagram,

    {"fyodor": "find", "v": 1, "nonce": "…", "id": "<asking server, optional>"}

and the beacon answers that device alone (unicast) with

    {"fyodor": "here", "v": 1, "nonce": "…", "id": "<instance>", "name": "<computer>", "port": <http>, "version": "…",
     "tables": [{id, name, format, phase, code, has_password, seats, taken, open, players, turn}, …], "more": <left out>}

``tables`` hold no more than ``GET /api/games`` already shows any device on the LAN (``lan_tables``): never a hot-seat or
practice table, a deck, a hand, a token or a password. A reply stays under ``MAX_REPLY`` bytes; malformed, oversized and
foreign datagrams, other protocol versions, our own server's queries and senders outside the local network get no answer,
and each sender gets at most ``RATE_PER_SECOND`` answers a second, so the beacon can't be used to flood anyone.

The host computer's Play page asks through ``GET /api/lan/nearby`` (``Discovery.nearby``): one query to 255.255.255.255
and each LAN address's /24 broadcast, replies collected for ``TIMEOUT`` seconds, one entry per server, its URL taken from
the address the reply came from.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import re
import secrets
import socket
import sys
import time
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from app import __version__
from app.config import Settings
from app.textutil import clean_text

if TYPE_CHECKING:
    from app.multiplayer.hub import Room

log = logging.getLogger(__name__)

MAGIC = "fyodor"
VERSION = 1
DEFAULT_PORT = 47474
MAX_QUERY = 512  # bytes; a query is a few dozen
MAX_REPLY = 8 * 1024
RATE_PER_SECOND = 5  # answers per sender per second
TIMEOUT = 0.7  # seconds a query waits for answers
CACHE_SECONDS = 2.0  # polling Play pages share one scan
MAX_TABLES = 40  # tables read from one reply
_NONCE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CODE = re.compile(r"^[A-Za-z0-9]{4,12}$")

Target = tuple[str, int]


def is_loopback(host: str) -> bool:
    name = host.strip().strip("[]").lower()
    if name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def on_local_network(address: str) -> bool:
    """A sender on this network (private, link-local or this computer): the beacon never answers the Internet."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return (ip.is_private or ip.is_link_local or ip.is_loopback) and not ip.is_multicast


def enabled(settings: Settings) -> bool:
    """The beacon answers only when the server listens on the LAN (not ``--local``) and discovery isn't turned off."""
    return settings.discovery and not is_loopback(settings.host)


def computer_name() -> str:
    """This computer's name as the network already knows it (``DESKTOP-42``, ``alice-laptop``)."""
    try:
        raw = socket.gethostname()
    except OSError:
        raw = ""
    return clean_text(raw.split(".")[0], 40) or "Fyodor"


# --------------------------------------------------------------------------- what a reply says


def lan_tables(rooms: Iterable[Room]) -> list[dict[str, Any]]:
    """The LAN tables as any device on the network sees them on its Play page (``GET /api/games`` for a non-host device)."""
    tables = []
    for room in rooms:
        if room.mode != "lan" or room.practice is not None:
            continue
        s = room.summary()
        seats = s["players"]
        taken = sum(1 for p in seats if p["claimed"])
        tables.append({
            "id": s["id"], "name": s["name"], "format": s["format"], "phase": s["phase"], "code": s["code"],
            "has_password": s["has_password"], "seats": len(seats), "taken": taken, "open": len(seats) - taken,
            # a lobby's open seats have no player yet ("Seat 3"); a game's players all have names
            "players": [p["name"] for p in seats if p["claimed"] or s["phase"] != "lobby"],
            "turn": s["turn"],
        })
    return order_tables(tables)


def order_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lobbies with an open seat first, then full lobbies, then games in progress (each group in its own order)."""
    def rank(t: dict[str, Any]) -> int:
        if t.get("phase") == "lobby":
            return 0 if t.get("open", 0) > 0 else 1
        return 2
    return sorted(tables, key=rank)


def _dump(body: dict[str, Any]) -> bytes:
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()


def encode_reply(nonce: str, *, instance: str, name: str, port: int, version: str, tables: list[dict[str, Any]],
                 limit: int = MAX_REPLY) -> bytes:
    body: dict[str, Any] = {"fyodor": "here", "v": VERSION, "nonce": nonce, "id": instance, "name": name, "port": port,
                            "version": version, "tables": tables}
    data = _dump(body)
    keep = len(tables)
    while len(data) > limit and keep > 0:  # drop tables from the end (games in progress go first) until it fits
        keep -= 1
        body["tables"], body["more"] = tables[:keep], len(tables) - keep
        data = _dump(body)
    return data


def encode_query(nonce: str, instance: str | None = None) -> bytes:
    return _dump({"fyodor": "find", "v": VERSION, "nonce": nonce, **({"id": instance} if instance else {})})


def parse_query(data: bytes) -> tuple[str, str | None] | None:
    """(nonce, asking instance) of a well-formed query of our protocol version, else None."""
    if len(data) > MAX_QUERY:
        return None
    try:
        msg = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(msg, dict) or msg.get("fyodor") != "find" or msg.get("v") != VERSION:
        return None
    nonce, asker = msg.get("nonce"), msg.get("id")
    if not isinstance(nonce, str) or not _NONCE.match(nonce):
        return None
    return nonce, asker if isinstance(asker, str) else None


def _int(value: Any, lo: int, hi: int) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and lo <= value <= hi else None


def _text(value: Any, size: int) -> str | None:
    return clean_text(value, size) or None if isinstance(value, str) else None


def _table(raw: Any) -> dict[str, Any] | None:
    """A table from another server's reply, checked field by field (it comes from the network)."""
    if not isinstance(raw, dict):
        return None
    code = raw.get("code")
    seats, turn = _int(raw.get("seats"), 0, 12), _int(raw.get("turn"), 0, 100_000)
    tid, name, fmt = _text(raw.get("id"), 64), _text(raw.get("name"), 80), _text(raw.get("format"), 24)
    if not (isinstance(code, str) and _CODE.match(code)) or seats is None or turn is None or not (tid and name and fmt):
        return None
    taken = _int(raw.get("taken"), 0, seats)
    phase = raw.get("phase")
    players = raw.get("players")
    if taken is None or phase not in ("lobby", "playing") or not isinstance(players, list):
        return None
    return {
        "id": tid, "name": name, "format": fmt, "phase": phase, "code": code.upper(), "has_password": raw.get("has_password") is True,
        "seats": seats, "taken": taken, "open": seats - taken, "turn": turn,
        "players": [n for n in (_text(p, 40) for p in players[:12]) if n],
    }


def parse_reply(data: bytes, nonce: str, source_ip: str) -> dict[str, Any] | None:
    """A beacon's answer to our query ``nonce``, with the URL its tables are played at, else None."""
    if len(data) > MAX_REPLY:
        return None
    try:
        msg = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(msg, dict) or msg.get("fyodor") != "here" or msg.get("v") != VERSION or msg.get("nonce") != nonce:
        return None
    instance, name, version = _text(msg.get("id"), 64), _text(msg.get("name"), 40), _text(msg.get("version"), 24)
    port, tables = _int(msg.get("port"), 1, 65535), msg.get("tables")
    if not (instance and name and version) or port is None or not isinstance(tables, list):
        return None
    try:
        ip = ipaddress.ip_address(source_ip)
    except ValueError:
        return None
    host = f"[{ip}]" if ip.version == 6 else str(ip)
    return {"id": instance, "name": name, "version": version, "url": f"http://{host}:{port}",
            "tables": [t for t in (_table(x) for x in tables[:MAX_TABLES]) if t]}


# --------------------------------------------------------------------------- the beacon


class RateLimit:
    """At most ``per_second`` answers to one sender in any second; remembers ``max_senders`` senders at most."""

    def __init__(self, per_second: int = RATE_PER_SECOND, max_senders: int = 256) -> None:
        self.per_second, self.max_senders = per_second, max_senders
        self.seen: dict[str, list[float]] = {}

    def allow(self, sender: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        recent = [t for t in self.seen.get(sender, ()) if now - t < 1.0]
        if len(recent) >= self.per_second:
            self.seen[sender] = recent
            return False
        recent.append(now)
        self.seen[sender] = recent
        if len(self.seen) > self.max_senders:  # forget the quiet ones, then the oldest
            self.seen = {k: v for k, v in self.seen.items() if v and now - v[-1] < 1.0}
            while len(self.seen) > self.max_senders:
                self.seen.pop(next(iter(self.seen)))
        return True


def _udp_socket(host: str = "", port: int = 0, *, share: bool = False) -> socket.socket:
    """A non-blocking UDP socket that may send broadcasts. ``share``: several Fyodor servers on one computer may answer on
    the same port (SO_REUSEADDR/SO_REUSEPORT, Linux and macOS; Windows lets only the first one bind it)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if share and sys.platform != "win32":  # on Windows SO_REUSEADDR would let another program take the port over
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                with contextlib.suppress(OSError):
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind((host, port))
        sock.setblocking(False)
    except OSError:
        sock.close()
        raise
    return sock


class _Responder(asyncio.DatagramProtocol):
    def __init__(self, discovery: Discovery) -> None:
        self.discovery = discovery
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        try:
            reply = self.discovery.answer(data, str(addr[0]))
        except Exception:  # noqa: BLE001 - a bad datagram never takes the beacon down
            log.debug("discovery: could not answer %s", addr[0], exc_info=True)
            return
        if reply is not None and self.transport is not None:
            self.transport.sendto(reply, addr)

    def error_received(self, exc: Exception) -> None:
        log.debug("discovery: %s", exc)


class _Collector(asyncio.DatagramProtocol):
    def __init__(self, nonce: str, exclude: str | None) -> None:
        self.nonce, self.exclude = nonce, exclude
        self.found: dict[str, dict[str, Any]] = {}

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        server = parse_reply(data, self.nonce, str(addr[0]))
        if server is not None and server["id"] != self.exclude:
            self.found.setdefault(server["id"], server)

    def error_received(self, exc: Exception) -> None:  # an unreachable target (no network): nothing found there
        log.debug("discovery query: %s", exc)


def broadcast_targets(port: int, addresses: Iterable[str]) -> list[Target]:
    """255.255.255.255 and each LAN address's /24 broadcast (most home networks)."""
    targets = [("255.255.255.255", port)]
    for addr in addresses:
        parts = addr.split(".")
        if len(parts) == 4:
            target = (".".join([*parts[:3], "255"]), port)
            if target not in targets:
                targets.append(target)
    return targets


async def query(targets: list[Target], *, timeout: float = TIMEOUT, exclude: str | None = None) -> list[dict[str, Any]]:
    """Ask ``targets`` for Fyodor tables; one entry per server that answered within ``timeout`` (never ``exclude``)."""
    if not targets:
        return []
    nonce = secrets.token_hex(8)
    collector = _Collector(nonce, exclude)
    try:
        sock = _udp_socket()
    except OSError as exc:  # no network at all
        log.debug("discovery query: %s", exc)
        return []
    try:
        transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(lambda: collector, sock=sock)
    except OSError as exc:
        sock.close()
        log.debug("discovery query: %s", exc)
        return []
    try:
        message = encode_query(nonce, exclude)
        for target in targets:
            transport.sendto(message, target)  # failures (unreachable network) go to error_received
        await asyncio.sleep(timeout)
    finally:
        transport.close()
    return list(collector.found.values())


class Discovery:
    """This server's beacon (while it listens on the LAN) and its searches for other servers' tables."""

    def __init__(self, settings: Settings, rooms: Callable[[], Iterable[Room]], *, version: str = __version__) -> None:
        self.settings, self.rooms, self.version = settings, rooms, version
        self.instance_id = secrets.token_hex(8)
        self.port: int | None = None  # the UDP port the beacon answers on, while it runs
        self.timeout = TIMEOUT
        self.targets: Callable[[], list[Target]] = self._broadcast_targets
        self.limit = RateLimit()
        self._transport: asyncio.DatagramTransport | None = None
        self._cache: tuple[float, list[dict[str, Any]]] | None = None
        self._scan: asyncio.Future[list[dict[str, Any]]] | None = None

    def _broadcast_targets(self) -> list[Target]:
        from app.launcher import lan_addresses

        return broadcast_targets(self.settings.discovery_port or DEFAULT_PORT, lan_addresses())

    # -- the beacon ---------------------------------------------------------------------
    async def start(self) -> bool:
        """Answer queries on the discovery port when the server is on the LAN. Never raises: a port that is taken or a
        computer with no network only means friends type the address instead."""
        if not enabled(self.settings):
            return False
        wanted = self.settings.discovery_port
        sock: socket.socket | None = None
        try:
            sock = _udp_socket("", wanted, share=True)
            transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(lambda: _Responder(self), sock=sock)
        except OSError as exc:
            if sock is not None:
                sock.close()
            log.warning("Network discovery is off: could not listen on UDP port %s (%s). Friends can still join with this "
                        "computer's address.", wanted, exc.strerror or exc)
            return False
        self._transport = transport
        self.port = int(transport.get_extra_info("sockname")[1])
        log.info("Network discovery: answering on UDP port %s", self.port)
        return True

    def stop(self) -> None:
        if self._transport is not None:
            self._transport.close()
        self._transport, self.port = None, None

    def answer(self, data: bytes, sender: str) -> bytes | None:
        """The reply to one datagram, or None when it gets no answer."""
        query_ = parse_query(data)
        if query_ is None:
            return None
        nonce, asker = query_
        if asker == self.instance_id or not on_local_network(sender) or not self.limit.allow(sender):
            return None
        return encode_reply(nonce, instance=self.instance_id, name=computer_name(), port=self.settings.port,
                            version=self.version, tables=lan_tables(self.rooms()))

    # -- searching ---------------------------------------------------------------------
    async def nearby(self) -> list[dict[str, Any]]:
        """Other Fyodor servers on the network and their tables (never this one). Requests within ``CACHE_SECONDS`` share
        one scan; with discovery turned off nothing is sent."""
        if not self.settings.discovery:
            return []
        if self._cache is not None and time.monotonic() - self._cache[0] < CACHE_SECONDS:
            return self._cache[1]
        if self._scan is None or self._scan.done():
            self._scan = asyncio.ensure_future(self._run_scan())
        return await asyncio.shield(self._scan)

    async def _run_scan(self) -> list[dict[str, Any]]:
        try:
            found = await query(self.targets(), timeout=self.timeout, exclude=self.instance_id)
        except OSError:
            found = []
        servers = sorted(({k: s[k] for k in ("name", "url", "version", "tables")} for s in found), key=lambda s: (s["name"], s["url"]))
        self._cache = (time.monotonic(), servers)
        return servers
