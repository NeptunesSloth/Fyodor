"""Guesses at a room code or password are limited per address and per room (AttemptLimiter in app/netguard.py, used by /api/join and
/api/host/session); a seat token reconnecting is never a guess."""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.netguard import AttemptLimiter
from tests.conftest import claim_host, connect_game
from tests.test_games_api import ATRAXA, KRENKO

TOO_MANY = {"detail": "Too many attempts. Try again in a few minutes."}
UNIFORM = {"detail": "Unknown room code or wrong password"}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# -- the limiter itself --

def test_limiter_blocks_after_max_failures_and_forgets_by_failure_time() -> None:
    clock = Clock()
    lim = AttemptLimiter(3, 100.0, clock)
    lim.fail("a")
    clock.now += 60
    lim.fail("a")
    lim.fail("a")
    assert lim.blocked("a") and not lim.blocked("b")
    clock.now += 41  # the first failure is 101 s old and no longer counts; the other two do
    assert not lim.blocked("a")
    lim.fail("a")
    assert lim.blocked("a")
    clock.now += 100
    assert not lim.blocked("a")


def test_limiter_succeed_clears_and_blocked_creates_nothing() -> None:
    lim = AttemptLimiter(2, 100.0, Clock())
    assert not lim.blocked("ghost")
    assert len(lim._failures) == 0
    lim.fail("a")
    lim.fail("a")
    lim.succeed("a")
    assert not lim.blocked("a")


def test_limiter_keeps_at_most_10000_keys_dropping_the_oldest() -> None:
    lim = AttemptLimiter(1, 100.0, Clock())
    for i in range(10_001):
        lim.fail(str(i))
    assert len(lim._failures) == 10_000
    assert not lim.blocked("0") and lim.blocked("1") and lim.blocked("10000")


def test_limiter_retry_after_is_whole_seconds_until_the_oldest_failure_expires() -> None:
    clock = Clock()
    lim = AttemptLimiter(1, 100.0, clock)
    lim.fail("a")
    clock.now += 30.2
    assert lim.retry_after("a") == 70
    clock.now += 69.5
    assert lim.retry_after("a") == 1


# -- the routes --

@pytest.fixture()
def clock() -> Clock:
    return Clock()


@pytest.fixture()
def app(settings: Settings, card_db: Path, clock: Clock):  # type: ignore[no-untyped-def]
    app = create_app(settings)
    with TestClient(app) as c:
        services = app.state.services
        services.join_limiter_addr = AttemptLimiter(5, 900.0, clock)
        services.join_limiter_room = AttemptLimiter(30, 900.0, clock)
        claim_host(c)
        yield app


@pytest.fixture()
def table(app):  # type: ignore[no-untyped-def]
    with peer(app, ("127.0.0.1", 1)) as host:
        claim_host(host)
        a = host.post("/api/decks", json={"text": KRENKO}).json()["id"]
        b = host.post("/api/decks", json={"text": ATRAXA}).json()["id"]
        body = {"name": "T", "mode": "lan", "password": "pw",
                "players": [{"name": "Alice", "deck_id": a}, {"name": "Bob", "deck_id": b}]}
        return host.post("/api/games", json=body).json()


def peer(app, address):  # type: ignore[no-untyped-def]
    """A client at ``address`` (None: the framework gives no peer) on the running app; no lifespan of its own, so leaving a ``with``
    does not shut the app down."""
    return contextlib.nullcontext(TestClient(app, client=address))


def join(c: TestClient, code: str, password: str | None = None, **extra):  # type: ignore[no-untyped-def]
    return c.post("/api/join", json={"code": code, "password": password, **extra}, headers={"Cookie": ""})


def test_sixth_attempt_from_one_address_is_429_even_with_the_right_password(app, table) -> None:
    code = table["game"]["code"]
    with peer(app, ("203.0.113.1", 1)) as c:
        for _ in range(5):
            assert join(c, code, "bad").status_code == 403
        r = join(c, code, "pw")
        assert r.status_code == 429 and r.json() == TOO_MANY
        assert 1 <= int(r.headers["retry-after"]) <= 900
    with peer(app, ("203.0.113.2", 1)) as other:
        assert join(other, code, "pw").status_code == 200


def test_address_joins_again_after_the_window(app, table, clock) -> None:
    code = table["game"]["code"]
    with peer(app, ("203.0.113.1", 1)) as c:
        for _ in range(5):
            join(c, code, "bad")
        assert join(c, code, "pw").status_code == 429
        clock.now += 901
        assert join(c, code, "pw").status_code == 200


def test_unknown_code_and_wrong_password_are_identical(app, table) -> None:
    code = table["game"]["code"]
    with peer(app, ("203.0.113.1", 1)) as a, peer(app, ("203.0.113.2", 1)) as b:
        unknown = join(a, "ZZZZZZ", "pw")
        wrong = join(b, code, "bad")
    assert (unknown.status_code, unknown.json()) == (wrong.status_code, wrong.json()) == (403, UNIFORM)
    keep = lambda r: {k: v for k, v in r.headers.items() if k != "date"}  # noqa: E731
    assert keep(unknown) == keep(wrong)


def test_unknown_codes_count_against_the_address_but_create_no_room_key(app, table) -> None:
    with peer(app, ("203.0.113.1", 1)) as c:
        for i in range(5):
            assert join(c, f"ZZZZZ{i}").status_code == 403
        assert join(c, "ZZZZZ9").status_code == 429
    assert len(app.state.services.join_limiter_room._failures) == 0


def test_room_blocked_by_many_addresses_still_admits_the_right_password(app, table) -> None:
    code = table["game"]["code"]
    for i in range(30):  # the 30th wrong guess is the one that fills the room's budget, and is already told so
        with peer(app, (f"198.51.100.{i}", 1)) as c:
            assert join(c, code, "bad").status_code == (429 if i == 29 else 403)
    with peer(app, ("203.0.113.50", 1)) as late:
        r = join(late, code, "bad")  # the 31st wrong guess on the room
        assert r.status_code == 429 and r.json() == TOO_MANY
    with peer(app, ("203.0.113.51", 1)) as friend:
        assert join(friend, code, "pw").status_code == 200  # the real pod is not locked out


def test_a_right_join_does_not_clear_failures_other_people_may_share(app, table) -> None:
    code = table["game"]["code"]
    services = app.state.services
    with peer(app, ("203.0.113.1", 1)) as c:
        for _ in range(4):
            assert join(c, code, "bad").status_code == 403
        assert join(c, code, "pw", spectate=True).status_code == 200  # not blocked yet: a right join still works
        assert join(c, code, "bad").status_code == 403  # the 5th failure: the right join did not wipe the four
        assert join(c, code, "pw", spectate=True).status_code == 429
        assert join(c, code, "bad").status_code == 429
    assert services.join_limiter_room._failures[code]


def test_no_peer_is_one_shared_bucket_not_exempt(app, table) -> None:
    code = table["game"]["code"]
    services = app.state.services
    for _ in range(5):
        services.join_limiter_addr.fail("")
    with peer(app, None) as c:
        assert join(c, code, "pw").status_code == 429


def test_reconnecting_with_a_seat_token_never_touches_the_limiter(app, table) -> None:
    gid, token = table["game"]["id"], table["seat"]["token"]
    services = app.state.services
    with peer(app, ("203.0.113.1", 1)) as c:
        for _ in range(5):
            join(c, table["game"]["code"], "bad")
        assert join(c, table["game"]["code"], "pw").status_code == 429  # this address is blocked
        for _ in range(8):  # a phone that sleeps and wakes, over and over
            with connect_game(c, gid, token) as ws:
                assert ws.receive_json()["type"] == "state"
    assert len(services.join_limiter_addr._failures) == 1


def test_blocked_host_session_address_still_takes_the_right_secret(app) -> None:
    secret = app.state.services.host_secret.value
    with peer(app, ("203.0.113.1", 1)) as c:
        for _ in range(5):
            assert c.post("/api/host/session", json={"secret": "x" * 43}).status_code == 403
        r = c.post("/api/host/session", json={"secret": "y" * 43})
        assert r.status_code == 429 and r.json() == TOO_MANY and "set-cookie" not in r.headers
        assert c.post("/api/host/session", json={"secret": secret}).status_code == 204  # the host is never locked out
    with peer(app, ("203.0.113.2", 1)) as other:
        assert other.post("/api/host/session", json={"secret": "z" * 43}).status_code == 403  # other addresses are not blocked


def test_joins_and_host_session_have_separate_budgets(app, table) -> None:
    code, secret = table["game"]["code"], app.state.services.host_secret.value
    with peer(app, ("203.0.113.1", 1)) as c:
        for _ in range(5):
            join(c, code, "bad")
        assert join(c, code, "pw").status_code == 429
        assert c.post("/api/host/session", json={"secret": secret}).status_code == 204
    with peer(app, ("203.0.113.2", 1)) as d:
        for _ in range(5):
            d.post("/api/host/session", json={"secret": "x" * 43})
        assert join(d, code, "pw").status_code == 200


def test_blocked_room_key_still_admits_the_right_password_from_a_fresh_address(app, table) -> None:
    code = table["game"]["code"]
    for _ in range(30):
        app.state.services.join_limiter_room.fail(code)
    assert app.state.services.join_limiter_room.blocked(code)
    with peer(app, ("203.0.113.77", 1)) as c:
        assert join(c, code, "pw").status_code == 200


def test_host_opening_the_launcher_many_times_is_never_locked_out(app) -> None:
    secret = app.state.services.host_secret.value
    with peer(app, ("203.0.113.1", 1)) as c:
        for _ in range(20):
            assert c.post("/api/host/session", json={"secret": secret}).status_code == 204


def test_unknown_code_costs_one_password_hash_like_a_real_room(app, table, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.multiplayer import hub

    calls: list[tuple[bytes, int]] = []
    real = hub._hash_password
    monkeypatch.setattr(hub, "_hash_password", lambda password, salt, rounds: calls.append((salt, rounds)) or real(password, salt, 1))
    with peer(app, ("203.0.113.1", 1)) as c:
        assert join(c, "ZZZZZZ", "pw").status_code == 403
        assert len(calls) == 1
        assert join(c, table["game"]["code"], "bad").status_code == 403
        assert len(calls) == 2


# -- a guess is counted before it is hashed, and hashed off the shared threadpool --

def test_undo_last_removes_only_the_newest_failure() -> None:
    clock = Clock()
    lim = AttemptLimiter(2, 100.0, clock)
    lim.undo_last("ghost")  # (no failure: nothing to undo, no key created)
    assert len(lim._failures) == 0
    lim.fail("a")
    clock.now += 60
    lim.fail("a")
    assert lim.blocked("a")
    lim.undo_last("a")
    assert not lim.blocked("a")
    assert lim.retry_after("a") == 40  # the older failure is the one left
    lim.undo_last("a")
    assert len(lim._failures) == 0


def _wrong_joins(app: FastAPI, code: str, password: str, addresses: list[str],
                 during: Callable[[httpx.AsyncClient], Awaitable[Any]] | None = None) -> tuple[list[int], Any]:
    """One join from each of ``addresses``, started together on the running app (one event loop, the real ASGI app); ``during`` (an
    async function taking a client) runs once they are under way. The status codes, and what ``during`` returned."""
    def client(address: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(address, 1)), base_url="http://testserver")

    async def scenario() -> tuple[list[int], Any]:
        clients = [client(a) for a in addresses]
        try:
            joins = [asyncio.ensure_future(c.post("/api/join", json={"code": code, "password": password})) for c in clients]
            seen = None
            if during is not None:
                async with client("203.0.113.250") as other:
                    seen = await during(other)
            return [r.status_code for r in await asyncio.gather(*joins)], seen
        finally:
            for c in clients:
                await c.aclose()

    return asyncio.run(scenario())


def test_concurrent_wrong_joins_stop_at_five(app: FastAPI, table: dict[str, Any]) -> None:
    codes, _ = _wrong_joins(app, table["game"]["code"], "bad", ["203.0.113.1"] * 40)
    assert sorted(codes) == [403] * 5 + [429] * 35


def test_other_routes_answer_while_joins_hash(app: FastAPI, table: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    from app.multiplayer import hub

    hashing = threading.Event()

    def slow(password: str, salt: bytes, rounds: int) -> bytes:
        hashing.set()
        time.sleep(0.5)
        return b"x" * 32

    monkeypatch.setattr(hub, "_pbkdf2", slow)

    async def health(c: httpx.AsyncClient) -> tuple[int, float]:
        while not hashing.is_set():  # (the joins are under way: the first hash has begun)
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        start = time.monotonic()
        r = await c.get("/api/health")
        return r.status_code, time.monotonic() - start

    # (40 addresses: none is refused by its own limiter, so all 40 joins are hashed — only a pool of their own keeps health fast)
    codes, (status, took) = _wrong_joins(app, table["game"]["code"], "bad", [f"198.51.100.{i}" for i in range(40)], during=health)
    assert status == 200 and took < 0.3, took
    assert codes.count(403) + codes.count(429) == 40 and codes.count(429) == 11  # (every join hashed; the room's 30 failures block it)


def test_a_right_join_costs_the_address_nothing(app: FastAPI, table: dict[str, Any]) -> None:
    code = table["game"]["code"]
    with peer(app, ("203.0.113.1", 1)) as c:
        for _ in range(4):
            assert join(c, code, "bad").status_code == 403
        assert join(c, code, "pw", spectate=True).status_code == 200
        assert join(c, code, "bad").status_code == 403  # the right join's reservation was given back: this is the 5th failure
        assert join(c, code, "bad").status_code == 429
