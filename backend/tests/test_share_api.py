"""The host's share tools (app/api/share.py): share a LAN table over the invite link, check it, stop sharing it. A real cloudflared is
never started: ``services.tunnel.start`` and ``stop`` are swapped for fakes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.game.state import zone_key
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

    async def start(self) -> str:
        self.starts += 1
        if self.fail is not None:
            self.tunnel.state, self.tunnel.reason = "failed", self.fail
            raise TunnelUnavailable(self.fail)
        self.tunnel.hostname, self.tunnel.state, self.tunnel.reason = TUNNEL_HOST, "running", None
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
    # already has one: none is needed, and a new one is refused
    assert _share(client, gid, None).status_code == 200
    res = _share(client, gid, "another password")
    assert res.status_code == 409 and res.json()["detail"] == "This table already has a password."


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
    assert not _room(client, gid).shared
    status = client.get(f"/api/games/{gid}/share").json()
    assert status["shared"] is False and status["link"] is None and status["state"] == "failed" and status["reason"] == fake.fail


def _until_closed(ws: Any) -> WebSocketDisconnect:
    with pytest.raises(WebSocketDisconnect) as closed:
        while True:
            ws.receive_json()
    return closed.value


def test_stop_sharing_closes_only_tunnel_sockets(client: TestClient, fake: FakeTunnel, tunnel_client: TestClient) -> None:
    """Review Focus 3: the remote socket closes 4403 with the reason, the LAN socket stays and hears the table is no longer shared,
    and an action sent on the tunnel socket just before the DELETE is applied once or not at all."""
    gid, bob = _started(client)
    assert _share(client, gid).status_code == 200
    room = _room(client, gid)
    alice = room.seats["p1"].token
    hand_before = len(room.session.state.zone(zone_key("p2", "hand")))
    with connect_game(client, gid, alice) as lan:
        assert lan.receive_json()["type"] == "state"
        with connect_game(tunnel_client, gid, bob) as remote:
            assert remote.receive_json()["type"] == "state"
            assert lan.receive_json()["view"]["game"]["shared"] is True  # (the remote player connected)
            remote.send_json({"type": "action", "action": {"type": "draw", "count": 1}, "id": 1, "client_action_id": "late-draw"})
            res = client.delete(f"/api/games/{gid}/share")
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
    hand_after = len(room.session.state.zone(zone_key("p2", "hand")))
    assert hand_after - hand_before in (0, 1)  # at most once
    assert list(room.client_actions.get("p2", {})) in ([], ["late-draw"])


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
