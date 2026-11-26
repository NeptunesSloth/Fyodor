"""The host's share tools (app/api/share.py): share a LAN table over the invite link, check it, stop sharing it. A real cloudflared is
never started: ``services.tunnel.start`` and ``stop`` are swapped for fakes."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.game.state import zone_key
from app.game.visibility import SPECTATOR
from app.tunnel.binary import TunnelUnavailable
from app.tunnel.manager import WENT_DOWN
from tests.conftest import TUNNEL_HOST, TUNNEL_PORT, connect_game, guest
from tests.test_games_api import ATRAXA, KRENKO
from tests.test_lobby import create_lobby

PASSWORD = "correct horse"


class FakeTunnel:
    def __init__(self, tunnel: Any) -> None:
        self.tunnel, self.starts, self.stops = tunnel, 0, 0
        self.fail: str | None = None
        self.during: Callable[[], Awaitable[None]] | None = None  # (runs inside start, before it returns)

    async def start(self) -> str:
        self.starts += 1
        if self.fail is not None:
            self.tunnel.state, self.tunnel.reason = "failed", self.fail
            raise TunnelUnavailable(self.fail)
        self.tunnel.hostname, self.tunnel.state, self.tunnel.reason = TUNNEL_HOST, "running", None
        if self.during is not None:  # (the link is up; the caller hasn't heard yet)
            await self.during()
        return TUNNEL_HOST

    def stop(self) -> None:
        self.stops += 1
        self.tunnel.hostname, self.tunnel.state, self.tunnel.reason = None, "stopped", None


@pytest.fixture()
def fake(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> FakeTunnel:
    tunnel = client.app.state.services.tunnel  # type: ignore[attr-defined]
    tunnel.port = TUNNEL_PORT
    f = FakeTunnel(tunnel)
    monkeypatch.setattr(tunnel, "start", f.start)
    monkeypatch.setattr(tunnel, "stop", f.stop)
    return f


def _room(client: TestClient, gid: str) -> Any:
    return client.app.state.services.hub.get(gid)  # type: ignore[attr-defined]


def _started(client: TestClient) -> tuple[str, str]:
    """A started LAN table; (game id, a token for the second seat)."""
    a = client.post("/api/decks", json={"text": KRENKO}).json()["id"]
    b = client.post("/api/decks", json={"text": ATRAXA}).json()["id"]
    game = client.post("/api/games", json={"name": "Remote", "mode": "lan", "players": [{"name": "Alice", "deck_id": a},
                                                                                        {"name": "Bob", "deck_id": b}]}).json()
    gid = game["game"]["id"]
    _, token = client.app.state.services.hub.claim_seat(_room(client, gid), name="Bob", seat=None)  # type: ignore[attr-defined]
    return gid, token


def _share(client: TestClient, gid: str, password: str | None = PASSWORD) -> Any:
    return client.post(f"/api/games/{gid}/share", json={"password": password} if password else {})


def test_only_the_host_cookie_shares(client: TestClient, fake: FakeTunnel, tunnel_client: TestClient) -> None:
    gid, _, alice = create_lobby(client)
    for method in ("GET", "POST", "DELETE"):
        res = client.request(method, f"/api/games/{gid}/share", headers={**guest(), "X-Seat-Token": alice},
                             json={"password": PASSWORD} if method == "POST" else None)
        assert res.status_code == 403, method
        res = tunnel_client.request(method, f"/api/games/{gid}/share", headers={"X-Seat-Token": alice},
                                    json={"password": PASSWORD} if method == "POST" else None)
        assert res.status_code == 404, method
    assert fake.starts == 0 and not _room(client, gid).shared


def test_sharing_needs_a_password(client: TestClient, fake: FakeTunnel) -> None:
    gid, code, _ = create_lobby(client)
    res = _share(client, gid, None)
    assert res.status_code == 422 and res.json()["detail"] == "A table shared over the internet needs a password."
    assert fake.starts == 0 and not _room(client, gid).shared
    res = _share(client, gid)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["shared"] is True and body["has_password"] is True and body["state"] == "running"
    assert client.get(f"/api/games/{gid}/share").json()["has_password"] is True
    # the LAN join needs it too
    assert client.post("/api/join", json={"code": code, "name": "Eve"}, headers=guest()).status_code == 403
    assert client.post("/api/join", json={"code": code, "name": "Eve", "password": PASSWORD}, headers=guest()).status_code == 200
    # already has one: sharing with it keeps it ("Share with it")
    assert _share(client, gid, None).status_code == 200
    assert client.post("/api/join", json={"code": code, "name": "Fay", "password": PASSWORD}, headers=guest()).status_code == 200


def test_sharing_with_a_new_password_replaces_the_tables(client: TestClient, fake: FakeTunnel, tunnel_client: TestClient) -> None:
    """Final review I3 / security F1: a LAN password (any length) is replaced by the 8-100 character one the host types when sharing,
    for new joiners on the LAN too; seated players keep their tokens."""
    gid, code, alice = create_lobby(client, password="1")
    res = _share(client, gid, "a new password")
    assert res.status_code == 200 and res.json()["has_password"] is True, res.text
    invite = _room(client, gid).invite_code
    for password in ("1", None):
        assert client.post("/api/join", json={"code": code, "name": "Eve", "password": password}, headers=guest()).status_code == 403
        assert tunnel_client.post("/api/join", json={"code": invite, "name": "Eve", "password": password}).status_code == 403
    assert client.post("/api/join", json={"code": code, "name": "Eve", "password": "a new password"}, headers=guest()).status_code == 200
    assert tunnel_client.post("/api/join", json={"code": invite, "name": "Bob", "password": "a new password"}).status_code == 200
    assert client.get(f"/api/games/{gid}/lobby", headers={**guest(), "X-Seat-Token": alice}).status_code == 200  # (still seated)
    # sharing again with another one replaces it again (rotation), and the rule still holds for what is typed
    assert _share(client, gid, "a third password").status_code == 200
    assert tunnel_client.post("/api/join", json={"code": invite, "name": "Cy", "password": "a new password"}).status_code == 403
    assert _share(client, gid, "short").status_code == 422


def test_a_short_password_is_422(client: TestClient, fake: FakeTunnel) -> None:
    gid, _, _ = create_lobby(client)
    for password in ("", "seven77", "x" * 101):
        assert client.post(f"/api/games/{gid}/share", json={"password": password}).status_code == 422, password
    assert fake.starts == 0 and _room(client, gid).password_state()[1] is None and not _room(client, gid).shared


def test_share_returns_the_link_with_the_invite_code(client: TestClient, fake: FakeTunnel) -> None:
    gid, _ = _started(client)
    body = _share(client, gid).json()
    room = _room(client, gid)
    assert room.shared and room.invite_code is not None
    assert body == {"shared": True, "state": "running", "reason": None,
                    "link": f"https://{TUNNEL_HOST}/#/play?code={room.invite_code}&join=1", "has_password": True, "available": True}
    assert client.get(f"/api/games/{gid}/share").json() == body
    assert client.get(f"/api/games/{gid}").json()["shared"] is True
    # another table, not shared, has no link even while the tunnel runs
    other, _, _ = create_lobby(client)
    status = client.get(f"/api/games/{other}/share").json()
    assert status["shared"] is False and status["link"] is None and status["state"] == "running"


def test_allow_network_off_is_409_and_never_starts(client: TestClient, fake: FakeTunnel) -> None:
    services = client.app.state.services  # type: ignore[attr-defined]
    gid, _, _ = create_lobby(client)
    object.__setattr__(services.settings, "allow_network", False)
    try:
        assert client.get(f"/api/games/{gid}/share").json()["available"] is False
        res = _share(client, gid)
        assert res.status_code == 409
        assert res.json()["detail"] == "Internet features are turned off on this computer (FYODOR_ALLOW_NETWORK=0)."
    finally:
        object.__setattr__(services.settings, "allow_network", True)
    assert fake.starts == 0 and not _room(client, gid).shared and _room(client, gid).password_state()[1] is None


def test_no_tunnel_port_is_409(client: TestClient, fake: FakeTunnel) -> None:
    client.app.state.services.tunnel.port = None  # type: ignore[attr-defined]
    gid, _, _ = create_lobby(client)
    assert client.get(f"/api/games/{gid}/share").json()["available"] is False
    res = _share(client, gid)
    assert res.status_code == 409 and res.json()["detail"] == "Start Fyodor from its launcher to share over the internet."
    assert fake.starts == 0 and not _room(client, gid).shared


def test_tunnel_unavailable_is_502_and_the_room_stays_unshared(client: TestClient, fake: FakeTunnel) -> None:
    fake.fail = "The internet link couldn't be started on this computer."
    gid, _, _ = create_lobby(client)
    res = _share(client, gid)
    assert res.status_code == 502 and res.json()["detail"] == fake.fail
    room = _room(client, gid)
    assert not room.shared and room.password_state()[1] is None and room.invite_code is None  # (nothing kept that nobody needed)
    assert client.get(f"/api/games/{gid}/share").json()["has_password"] is False
    status = client.get(f"/api/games/{gid}/share").json()
    assert status["shared"] is False and status["link"] is None and status["state"] == "failed" and status["reason"] == fake.fail


def _until_closed(ws: Any) -> WebSocketDisconnect:
    with pytest.raises(WebSocketDisconnect) as closed:
        while True:
            ws.receive_json()
    return closed.value


def _waiting(lock: asyncio.Lock, count: int) -> None:
    """Wait (a few seconds at most) until ``count`` tasks wait for ``lock``."""
    deadline = time.monotonic() + 5
    while len(lock._waiters or ()) < count:
        assert time.monotonic() < deadline, "nothing queued on the room lock"
        time.sleep(0.01)


def _queued_behind_delete(client: TestClient, room: Any, act: Callable[[], Any]) -> tuple[Any, Any]:
    """Hold the room lock, queue the DELETE on it, then ``act`` (an action that queues behind it), then let go: the DELETE runs
    first. Returns (the DELETE's response, what ``act`` returned)."""
    out: dict[str, Any] = {}
    client.portal.call(room.lock.acquire)  # type: ignore[union-attr]
    try:
        deleting = threading.Thread(target=lambda: out.setdefault("delete", client.delete(f"/api/games/{room.id}/share")))
        deleting.start()
        _waiting(room.lock, 1)
        acting = threading.Thread(target=lambda: out.setdefault("act", act()))
        acting.start()
        try:
            _waiting(room.lock, 2)
        except AssertionError:
            acting.join(1)
            raise AssertionError(f"the action did not queue: {out.get('act')!r} {getattr(out.get('act'), 'text', '')}") from None
    finally:
        client.portal.call(room.lock.release)  # type: ignore[union-attr]
    deleting.join(10)
    acting.join(10)
    return out["delete"], out.get("act")


def test_stop_sharing_closes_only_tunnel_sockets(client: TestClient, fake: FakeTunnel, tunnel_client: TestClient) -> None:
    """Review Focus 3: the remote socket closes 4403 with the reason, the LAN socket stays and hears the table is no longer shared,
    and an action sent on the tunnel socket that is still waiting for the room lock when the DELETE takes it is not applied."""
    gid, bob = _started(client)
    assert _share(client, gid).status_code == 200
    room = _room(client, gid)
    alice = room.seats["p1"].token
    hand_before = len(room.session.state.zone(zone_key("p2", "hand")))
    tunnel_client.portal = client.portal  # (one event loop for both: the room lock is waited on from each)
    with connect_game(client, gid, alice) as lan:
        assert lan.receive_json()["type"] == "state"
        with connect_game(tunnel_client, gid, bob) as remote:
            assert remote.receive_json()["type"] == "state"
            assert lan.receive_json()["view"]["game"]["shared"] is True  # (the remote player connected)
            res, _ = _queued_behind_delete(client, room, lambda: remote.send_json(
                {"type": "action", "action": {"type": "draw", "count": 1}, "id": 1, "client_action_id": "late-draw"}))
            assert res.status_code == 200 and res.json()["shared"] is False and res.json()["link"] is None
            closed = _until_closed(remote)
            assert closed.code == 4403 and closed.reason == "The host stopped sharing this table."
            seen = lan.receive_json()
            while seen.get("type") != "state" or seen["view"]["game"]["shared"] is not False:
                seen = lan.receive_json()
            assert seen["view"]["game"]["shared"] is False
            lan.send_json({"type": "ping", "id": 9})  # the LAN socket still works
            while lan.receive_json().get("type") != "pong":
                pass
    assert not room.shared and room.connections == {}
    assert len(room.session.state.zone(zone_key("p2", "hand"))) == hand_before  # not applied
    assert "late-draw" not in room.client_actions.get("p2", {})


def test_a_rest_action_queued_behind_the_unshare_is_refused(client: TestClient, fake: FakeTunnel, tunnel_client: TestClient) -> None:
    gid, bob = _started(client)
    assert _share(client, gid).status_code == 200
    room = _room(client, gid)
    hand_before = len(room.session.state.zone(zone_key("p2", "hand")))
    tunnel_client.portal = client.portal
    res, acted = _queued_behind_delete(client, room, lambda: tunnel_client.post(
        f"/api/games/{gid}/actions", json={"action": {"type": "draw", "count": 1}, "client_action_id": "late-rest-draw"},
        headers={"X-Seat-Token": bob}))
    assert res.status_code == 200
    assert acted.status_code == 409 and acted.json()["detail"] == "The host stopped sharing this table."
    assert len(room.session.state.zone(zone_key("p2", "hand"))) == hand_before


def test_closing_a_shared_table_ends_its_link(client: TestClient, fake: FakeTunnel, tunnel_client: TestClient) -> None:
    """Closing the last shared table stops the tunnel, and its remote sockets close 4403 first."""
    gid, bob = _started(client)
    assert _share(client, gid).status_code == 200
    with connect_game(tunnel_client, gid, bob) as remote:
        assert remote.receive_json()["type"] == "state"
        assert client.delete(f"/api/games/{gid}").status_code == 204
        closed = _until_closed(remote)
        assert closed.code == 4403 and closed.reason == "The host closed this table."
    assert fake.stops == 1 and client.app.state.services.tunnel.state == "stopped"  # type: ignore[attr-defined]


def test_closing_one_of_two_shared_tables_keeps_the_link(client: TestClient, fake: FakeTunnel) -> None:
    one, _, _ = create_lobby(client)
    two, _, _ = create_lobby(client)
    assert _share(client, one).status_code == 200 and _share(client, two).status_code == 200
    assert client.delete(f"/api/games/{one}").status_code == 204
    assert fake.stops == 0 and client.get(f"/api/games/{two}/share").json()["link"] is not None


def test_loading_a_save_over_a_shared_table_ends_its_link(client: TestClient, fake: FakeTunnel) -> None:
    gid, _ = _started(client)
    assert _share(client, gid).status_code == 200
    alice = _room(client, gid).seats["p1"].token
    saved = client.post(f"/api/games/{gid}/save", json={"name": "Before"}, headers={"X-Seat-Token": alice})
    assert saved.status_code in (200, 201), saved.text
    loaded = client.post(f"/api/saves/{saved.json()['id']}/load", json={"mode": "lan"})
    assert loaded.status_code == 201, loaded.text
    assert fake.stops == 1 and not _room(client, gid).shared


def test_last_unshare_stops_the_tunnel_and_not_before(client: TestClient, fake: FakeTunnel) -> None:
    one, _, _ = create_lobby(client)
    two, _ = _started(client)
    assert _share(client, one).status_code == 200 and _share(client, two).status_code == 200
    assert fake.starts == 2
    assert client.delete(f"/api/games/{one}/share").json()["shared"] is False
    assert fake.stops == 0 and client.get(f"/api/games/{two}/share").json()["state"] == "running"
    assert client.delete(f"/api/games/{two}/share").json()["state"] == "stopped"
    assert fake.stops == 1
    assert client.delete(f"/api/games/{two}/share").status_code == 200  # (again: nothing is shared, stop is harmless)


def test_link_down_unshares_and_says_so(client: TestClient, fake: FakeTunnel, tunnel_client: TestClient) -> None:
    """Review Focus 4: the tunnel manager marks itself failed and calls on_down: every shared table is unshared and its remote players
    are told."""
    services = client.app.state.services  # type: ignore[attr-defined]
    gid, bob = _started(client)
    lobby, _, _ = create_lobby(client)
    assert _share(client, gid).status_code == 200 and _share(client, lobby).status_code == 200
    room = _room(client, gid)
    with connect_game(tunnel_client, gid, bob) as remote:
        assert remote.receive_json()["type"] == "state"
        tunnel = services.tunnel
        tunnel.state, tunnel.reason, tunnel.hostname = "failed", WENT_DOWN, None  # (what the manager does before on_down)
        assert tunnel.on_down is not None
        client.portal.call(tunnel.on_down)  # type: ignore[union-attr]
        closed = _until_closed(remote)
        assert closed.code == 4403 and closed.reason == WENT_DOWN
    assert not room.shared and not _room(client, lobby).shared
    assert services.hub.view(room, "p1")["game"]["shared"] is False
    assert client.get(f"/api/games/{lobby}").json()["shared"] is False
    status = client.get(f"/api/games/{gid}/share").json()
    assert status["state"] == "failed" and status["reason"] == WENT_DOWN and status["shared"] is False and status["link"] is None


def test_resharing_reuses_the_invite_code(client: TestClient, fake: FakeTunnel) -> None:
    gid, _, _ = create_lobby(client)
    first = _share(client, gid).json()["link"]
    code = _room(client, gid).invite_code
    client.delete(f"/api/games/{gid}/share")
    second = _share(client, gid, None).json()["link"]
    assert first == second and _room(client, gid).invite_code == code and fake.starts == 2


def test_the_invite_link_brings_a_player_back_to_their_seat(client: TestClient, fake: FakeTunnel, tunnel_client: TestClient) -> None:
    """Final review I2: opening the link again (holding the seat's token) returns that seat, not a new one; only after the password."""
    gid, _, _ = create_lobby(client)
    assert _share(client, gid).status_code == 200
    room = _room(client, gid)
    body = {"code": room.invite_code, "password": PASSWORD, "name": "Bob"}
    first = tunnel_client.post("/api/join", json=body).json()
    again = tunnel_client.post("/api/join", json=body, headers={"X-Seat-Token": first["token"]})
    assert again.status_code == 200, again.text
    assert (first["viewer"], again.json()["viewer"]) == ("p2", "p2") and again.json()["token"] == first["token"]
    assert room.seats["p3"].token is None  # no second seat
    # the token alone opens nothing: a wrong password is the same refusal as ever
    wrong = tunnel_client.post("/api/join", json={**body, "password": "not the password"}, headers={"X-Seat-Token": first["token"]})
    assert wrong.status_code == 403
    # a token that holds no seat here: a new seat, as before
    other = tunnel_client.post("/api/join", json={**body, "name": "Cara"}, headers={"X-Seat-Token": "not-a-token"}).json()
    assert other["viewer"] == "p3" and other["token"] != first["token"]
    # a spectator watching again keeps their spectator token
    watch = tunnel_client.post("/api/join", json={**body, "spectate": True}).json()
    again = tunnel_client.post("/api/join", json={**body, "spectate": True}, headers={"X-Seat-Token": watch["token"]}).json()
    assert again["viewer"] == watch["viewer"] == SPECTATOR and again["token"] == watch["token"] and len(room.spectator_tokens) == 1


def test_the_invite_link_brings_a_player_back_to_their_seat_mid_game(client: TestClient, fake: FakeTunnel,
                                                                     tunnel_client: TestClient) -> None:
    gid, bob = _started(client)  # (two seats, both taken: a new joiner would be told the table is full)
    assert _share(client, gid).status_code == 200
    body = {"code": _room(client, gid).invite_code, "password": PASSWORD}
    res = tunnel_client.post("/api/join", json=body, headers={"X-Seat-Token": bob})
    assert res.status_code == 200, res.text
    assert res.json()["viewer"] == "p2" and res.json()["token"] == bob


def test_a_room_blocked_on_the_tunnel_refuses_before_hashing(client: TestClient, fake: FakeTunnel, tunnel_client: TestClient,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """Security F2 / final review M1: guesses from many addresses (one /64 each) block the room; from then on a join through the tunnel
    is refused before its password is hashed, even the right one, with the room's Retry-After. The LAN and seated players are untouched."""
    from app.multiplayer import hub

    calls: list[int] = []
    real = hub._hash_password
    monkeypatch.setattr(hub, "_hash_password", lambda password, salt, rounds: calls.append(rounds) or real(password, salt, 1))
    gid, code, alice = create_lobby(client)
    assert _share(client, gid).status_code == 200
    room = _room(client, gid)
    body = {"code": room.invite_code, "name": "Mallory", "password": "not the password"}
    bob = tunnel_client.post("/api/join", json={**body, "name": "Bob", "password": PASSWORD}).json()["token"]
    services = client.app.state.services  # type: ignore[attr-defined]
    for i in range(40):
        if services.join_limiter_room.blocked(room.code):
            break
        res = tunnel_client.post("/api/join", json=body, headers={"CF-Connecting-IP": f"2001:db8:{i:x}::1"})
        assert res.status_code in (403, 429), res.text
    assert services.join_limiter_room.blocked(room.code)
    before = len(calls)
    res = tunnel_client.post("/api/join", json={**body, "password": PASSWORD}, headers={"CF-Connecting-IP": "2001:db8:ffff::1"})
    assert res.status_code == 429 and res.json() == {"detail": "Too many attempts. Try again in a few minutes."}, res.text
    assert int(res.headers["Retry-After"]) > 0
    assert len(calls) == before  # nothing hashed
    # a remote player opening the link again with their seat's token still gets back to it
    back = tunnel_client.post("/api/join", json={**body, "password": PASSWORD}, headers={"X-Seat-Token": bob})
    assert back.status_code == 200 and back.json()["token"] == bob, back.text
    # the LAN still joins with the right password (hashed as ever), and a seated player is not asked
    lan = client.post("/api/join", json={"code": code, "name": "Eve", "password": PASSWORD}, headers=guest())
    assert lan.status_code == 200, lan.text
    assert client.get(f"/api/games/{gid}/lobby", headers={**guest(), "X-Seat-Token": alice}).status_code == 200


def test_practice_and_hot_seat_tables_cannot_be_shared(client: TestClient, fake: FakeTunnel) -> None:
    a = client.post("/api/decks", json={"text": KRENKO}).json()["id"]
    b = client.post("/api/decks", json={"text": ATRAXA}).json()["id"]
    hot = client.post("/api/games", json={"name": "Couch", "mode": "local", "players": [{"name": "Alice", "deck_id": a},
                                                                                        {"name": "Bob", "deck_id": b}]})
    hot_id = hot.json()["game"]["id"]
    practice, _, _ = create_lobby(client)
    live, _, _ = create_lobby(client)
    _room(client, practice).practice = SimpleNamespace(live=live)
    for gid in (hot_id, practice):
        for method in ("GET", "POST", "DELETE"):
            res = client.request(method, f"/api/games/{gid}/share", json={"password": PASSWORD} if method == "POST" else None)
            assert res.status_code == 409 and res.json()["detail"] == "Only a LAN table can be shared", (gid, method)
        assert not _room(client, gid).shared
    assert client.get("/api/games/nope/share").status_code == 404
    assert fake.starts == 0


def test_a_stop_while_another_table_starts_sharing_wins(client: TestClient, fake: FakeTunnel) -> None:
    """Minor 3: table A's DELETE stops the unused tunnel while table B's POST is between its start and its share: B is not left
    shared with a stopped tunnel (and keeps no password)."""
    services = client.app.state.services  # type: ignore[attr-defined]
    one, _, _ = create_lobby(client)
    two, _, _ = create_lobby(client)
    assert _share(client, one).status_code == 200

    async def delete_one() -> None:
        await services.stop_sharing(_room(client, one), "The host stopped sharing this table.")

    fake.during = delete_one
    res = _share(client, two)
    assert res.status_code == 502 and res.json()["detail"] == "The internet link was turned off."
    room = _room(client, two)
    assert not room.shared and room.password_state()[1] is None and services.tunnel.state == "stopped"
    fake.during = None
    assert _share(client, two).json()["link"] is not None  # (again: it starts afresh)


def test_link_down_unshares_every_table_even_when_one_fails(client: TestClient, fake: FakeTunnel,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """Minor 4: every shared table stops being shared before any socket work, so one failing leaves none shared."""
    services = client.app.state.services  # type: ignore[attr-defined]
    rooms = [create_lobby(client)[0] for _ in range(3)]
    for gid in rooms:
        assert _share(client, gid).status_code == 200

    async def broken(room: Any, reason: str) -> int:
        raise RuntimeError("socket trouble")

    monkeypatch.setattr(services.hub, "close_tunnel_connections", broken)
    with pytest.raises(RuntimeError):
        client.portal.call(services.tunnel.on_down)  # type: ignore[union-attr]
    assert not any(_room(client, gid).shared for gid in rooms)


def test_stopping_an_unshared_table_changes_nothing(client: TestClient, fake: FakeTunnel, monkeypatch: pytest.MonkeyPatch) -> None:
    """Minor 5: no persist, no broadcast for a table that isn't shared."""
    hub = client.app.state.services.hub  # type: ignore[attr-defined]
    gid, _ = _started(client)
    calls: list[str] = []
    monkeypatch.setattr(hub, "persist", lambda room: calls.append("persist"))

    async def broadcast(room: Any, **kwargs: Any) -> None:
        calls.append("broadcast")

    monkeypatch.setattr(hub, "broadcast", broadcast)
    res = client.delete(f"/api/games/{gid}/share")
    assert res.status_code == 200 and res.json()["shared"] is False and calls == [] and fake.stops == 0
