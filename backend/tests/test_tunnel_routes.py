"""What the tunnel port serves (app/netguard.py TUNNEL_ROUTES, app/main.py net_guard): the routes a remote player needs, for shared
tables only, under the invite hostname and its https Origin. Everything else there is a 404 that says nothing about the server."""

from __future__ import annotations

import re
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import deps
from app.netguard import tunnel_route
from tests.conftest import TUNNEL_HOST, TUNNEL_PORT, connect_game, guest
from tests.test_games_api import ATRAXA, KRENKO
from tests.test_lobby import create_lobby

NOT_FOUND = {"detail": "Not Found"}
NO_GAME = {"detail": "Game not found (it may have been closed; load it from Saves)"}


def _routes(routes: list[Any], prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Every route of the app as (full path, route), through FastAPI's included routers (kept unflattened since 0.16x)."""
    for route in routes:
        if hasattr(route, "original_router"):
            yield from _routes(route.original_router.routes, prefix + route.include_context.prefix)
        else:
            yield prefix + route.path, route


def _room(client: TestClient, gid: str) -> Any:
    return client.app.state.services.hub.get(gid)  # type: ignore[attr-defined]


def _shared_game(client: TestClient) -> tuple[str, str]:
    """A started LAN table, shared over the invite link; (game id, a free seat's token)."""
    a = client.post("/api/decks", json={"text": KRENKO}).json()["id"]
    b = client.post("/api/decks", json={"text": ATRAXA}).json()["id"]
    game = client.post("/api/games", json={"name": "Remote", "mode": "lan", "players": [{"name": "Alice", "deck_id": a},
                                                                                        {"name": "Bob", "deck_id": b}]}).json()
    gid = game["game"]["id"]
    room = _room(client, gid)
    room.shared = True
    _, token = client.app.state.services.hub.claim_seat(room, name="Bob", seat=None)  # type: ignore[attr-defined]
    return gid, token


def _tunnel_without_origin(client: TestClient) -> TestClient:
    return TestClient(client.app, base_url=f"http://127.0.0.1:{TUNNEL_PORT}",
                      headers={"Host": TUNNEL_HOST, "CF-Connecting-IP": "198.51.100.7"})


# Every (method, route) the tunnel port lets through, reviewed one by one. A route added later that TUNNEL_ROUTES would let through
# (one under /api/games/{game_id}/, say) fails the walk below until it is added here: a deliberate decision, never an accident.
ALLOWED_ON_THE_TUNNEL = frozenset({
    ("DELETE", "/api/games/{game_id}"),
    ("DELETE", "/api/games/{game_id}/lobby/deck"),
    ("DELETE", "/api/games/{game_id}/next-deck"),
    ("DELETE", "/api/games/{game_id}/practice"),
    ("DELETE", "/api/games/{game_id}/predictions/{market}"),
    ("DELETE", "/api/games/{game_id}/snapshots/{snapshot_id}"),
    ("GET", "/api/assets/{asset_id}/file"),
    ("GET", "/api/cards/autocomplete"),
    ("GET", "/api/cards/glossary"),
    ("GET", "/api/cards/search"),
    ("GET", "/api/cards/{card_id}"),
    ("GET", "/api/cards/{card_id}/printings"),
    ("GET", "/api/games"),
    ("GET", "/api/games/{game_id}"),
    ("GET", "/api/games/{game_id}/collection"),
    ("GET", "/api/games/{game_id}/history"),
    ("GET", "/api/games/{game_id}/history/{position}"),
    ("GET", "/api/games/{game_id}/lobby"),
    ("GET", "/api/games/{game_id}/lobby/brought"),
    ("GET", "/api/games/{game_id}/next-deck"),
    ("GET", "/api/games/{game_id}/night/deck"),
    ("GET", "/api/games/{game_id}/pay-preview/{card_id}"),
    ("GET", "/api/games/{game_id}/predictions"),
    ("GET", "/api/games/{game_id}/result"),
    ("GET", "/api/games/{game_id}/sandbox/board"),
    ("GET", "/api/games/{game_id}/snapshots"),
    ("GET", "/api/games/{game_id}/view"),
    ("GET", "/api/games/{game_id}/watch"),
    ("GET", "/api/health"),
    ("GET", "/api/host/session"),
    ("GET", "/api/images/card-back"),
    ("GET", "/api/images/{card_id}"),
    ("GET", "/api/macros"),
    ("GET", "/api/rules/coverage"),
    ("GET", "/api/rules/support"),
    ("GET", "/api/symbols"),
    ("GET", "/api/symbols/{code}.svg"),
    ("POST", "/api/cards/batch"),
    ("POST", "/api/games/{game_id}/actions"),
    ("POST", "/api/games/{game_id}/deck-lab"),
    ("POST", "/api/games/{game_id}/history/{position}/restore"),
    ("POST", "/api/games/{game_id}/history/{position}/undo"),
    ("POST", "/api/games/{game_id}/load-deck"),
    ("POST", "/api/games/{game_id}/lobby/arrange"),
    ("POST", "/api/games/{game_id}/lobby/collection"),
    ("POST", "/api/games/{game_id}/lobby/deck"),
    ("POST", "/api/games/{game_id}/lobby/import"),
    ("POST", "/api/games/{game_id}/lobby/kick"),
    ("POST", "/api/games/{game_id}/lobby/leave"),
    ("POST", "/api/games/{game_id}/lobby/profile"),
    ("POST", "/api/games/{game_id}/lobby/ready"),
    ("POST", "/api/games/{game_id}/lobby/seat"),
    ("POST", "/api/games/{game_id}/lobby/settings"),
    ("POST", "/api/games/{game_id}/lobby/start"),
    ("POST", "/api/games/{game_id}/next-deck"),
    ("POST", "/api/games/{game_id}/night/answer"),
    ("POST", "/api/games/{game_id}/night/propose"),
    ("POST", "/api/games/{game_id}/night/reactions"),
    ("POST", "/api/games/{game_id}/night/signal"),
    ("POST", "/api/games/{game_id}/night/vote"),
    ("POST", "/api/games/{game_id}/practice"),
    ("POST", "/api/games/{game_id}/predictions"),
    ("POST", "/api/games/{game_id}/redo"),
    ("POST", "/api/games/{game_id}/result"),
    ("POST", "/api/games/{game_id}/sandbox/combat"),
    ("POST", "/api/games/{game_id}/snapshots"),
    ("POST", "/api/games/{game_id}/snapshots/{snapshot_id}/restore"),
    ("POST", "/api/games/{game_id}/test/take-back"),
    ("POST", "/api/games/{game_id}/undo"),
    ("POST", "/api/games/{game_id}/undo-request"),
    ("POST", "/api/join"),
})


def test_every_route_is_either_allowed_or_404_on_the_tunnel_port(client, tunnel_client) -> None:
    """The fail-closed guard: a route added later is a 404 on the tunnel unless TUNNEL_ROUTES names it, and one TUNNEL_ROUTES would
    let through must also be named in ALLOWED_ON_THE_TUNNEL."""
    gid, _ = _shared_game(client)
    walked = refused = 0
    allowed: set[tuple[str, str]] = set()
    for path, route in _routes(client.app.routes):
        if not isinstance(route, APIRoute):
            continue
        concrete = re.sub(r"\{([^}:]+)(:[^}]*)?\}", lambda m: gid if m.group(1) == "game_id" else "x", path)
        for method in sorted(route.methods):
            walked += 1
            if tunnel_route(method, concrete)[0]:
                allowed.add((method, path))
                continue
            refused += 1
            res = tunnel_client.request(method, concrete)
            assert res.status_code == 404 and res.json() == NOT_FOUND, (method, concrete, res.status_code)
    assert walked > 150 and refused > 80  # (the walk saw the app's routes, not an empty list)
    assert sorted(allowed - ALLOWED_ON_THE_TUNNEL) == [], "newly allowed on the tunnel: review, then add to ALLOWED_ON_THE_TUNNEL"
    assert sorted(ALLOWED_ON_THE_TUNNEL - allowed) == [], "no longer allowed on the tunnel: drop from ALLOWED_ON_THE_TUNNEL"


def test_head_options_and_trailing_slashes_are_404_on_the_tunnel_port(client, tunnel_client) -> None:
    gid, bob = _shared_game(client)
    for method, path in (("HEAD", "/api/health"), ("OPTIONS", f"/api/games/{gid}/view"), ("HEAD", f"/api/games/{gid}/view"),
                         ("PUT", f"/api/games/{gid}/view"), ("PATCH", f"/api/games/{gid}"), ("POST", f"/api/games/{gid}/save/"),
                         ("POST", f"/api/games/{gid}/assistant/"), ("GET", f"/api/games/{gid}/rules/scenario/"),
                         ("POST", f"/api/games/{gid}/lobby/bot/"), ("POST", f"/api/games/{gid}/bot/")):
        res = tunnel_client.request(method, path, headers={"X-Seat-Token": bob}, follow_redirects=False)
        assert res.status_code == 404, (method, path, res.status_code)
        if method != "HEAD":
            assert res.json() == NOT_FOUND, (method, path)


def test_the_tunnel_branch_is_what_refuses(client, tunnel_client) -> None:
    """Routes that answer a LAN guest today, 404 through the tunnel (so the walk above can't pass without the guard). (/api/lan/nearby
    is the host's alone, a 403 to a guest; the others are public on the LAN.)"""
    lan = {"/api/pod/results": 200, "/api/assets": 200, "/api/pod/players": 200, "/api/cards/stats": 200, "/api/lan/nearby": 403}
    for path, status in lan.items():
        assert client.get(path, headers=guest()).status_code == status, path
        res = tunnel_client.get(path)
        assert res.status_code == 404 and res.json() == NOT_FOUND, path


@pytest.mark.parametrize("method,path,allowed,gid", [
    ("GET", "/", True, None),
    ("GET", "/assets/index-abc.js", True, None),
    ("GET", "/api/health", True, None),
    ("GET", "/api/host/session", True, None),
    ("POST", "/api/host/session", False, None),
    ("POST", "/api/join", True, None),
    ("GET", "/api/games", True, None),
    ("POST", "/api/games", False, None),
    ("GET", "/api/cards/search", True, None),
    ("GET", "/api/cards/abc", True, None),
    ("GET", "/api/cards/abc/printings", True, None),
    ("GET", "/api/cards/stats", False, None),
    ("POST", "/api/cards/batch", True, None),
    ("POST", "/api/cards/cache-art", False, None),
    ("GET", "/api/images/card-back", True, None),
    ("GET", "/api/symbols", True, None),
    ("GET", "/api/symbols/W.svg", True, None),
    ("GET", "/api/assets/a1/file", True, None),
    ("GET", "/api/assets", False, None),
    ("GET", "/api/assets/a1", False, None),
    ("GET", "/api/rules/support", True, None),
    ("GET", "/api/rules/inventory", False, None),
    ("GET", "/api/macros", True, None),
    ("POST", "/api/macros", False, None),
    ("GET", "/api/games/g1", True, "g1"),
    ("DELETE", "/api/games/g1", True, "g1"),
    ("GET", "/api/games/g1/view", True, "g1"),
    ("POST", "/api/games/g1/actions", True, "g1"),
    ("POST", "/api/games/g1/lobby/deck", True, "g1"),
    ("GET", "/api/games/g1/lobby/brought", True, "g1"),
    ("HEAD", "/api/games/g1/view", False, None),
    ("OPTIONS", "/api/games/g1", False, None),
    ("PUT", "/api/games/g1", False, None),
    ("POST", "/api/games/g1/save", False, None),
    ("POST", "/api/games/g1/save/", False, None),
    ("POST", "/api/games/g1/lobby/bot/", False, None),
    ("POST", "/api/games/g1/saved", True, "g1"),
    ("POST", "/api/games/g1/assistant", False, None),
    ("GET", "/api/games/g1/rules/scenario", False, None),
    ("POST", "/api/games/g1/host/seat-link", False, None),
    ("POST", "/api/games/g1/share", False, None),
    ("POST", "/api/games/g1/lobby/bot", False, None),
    ("POST", "/api/games/g1/bot", False, None),
    ("POST", "/api/games/g1/bot/step", False, None),
    ("GET", "/api/lan/decks", False, None),
    ("POST", "/api/lan/handoff", False, None),
    ("GET", "/api/saves", False, None),
    ("GET", "/ws/games/g1", False, None),  # (the socket is checked in game_socket)
])
def test_tunnel_route(method, path, allowed, gid) -> None:
    assert tunnel_route(method, path) == (allowed, gid)


def test_unshared_room_is_no_such_room(client, tunnel_client) -> None:
    gid, _, alice = create_lobby(client)
    for path in (f"/api/games/{gid}/view", f"/api/games/{gid}/lobby", f"/api/games/{gid}"):
        res = tunnel_client.get(path, headers={"X-Seat-Token": alice})
        assert res.status_code == 404 and res.json() == NO_GAME, path
    with connect_game(tunnel_client, gid, alice) as ws, pytest.raises(WebSocketDisconnect) as closed:
        ws.receive_json()
    assert closed.value.code == 4403
    _room(client, gid).shared = True
    assert tunnel_client.get(f"/api/games/{gid}/lobby", headers={"X-Seat-Token": alice}).status_code == 200


def test_practice_room_of_a_shared_room_is_served(client, tunnel_client) -> None:
    live, _, _ = create_lobby(client)
    practice, _, _ = create_lobby(client)
    services = client.app.state.services
    _room(client, practice).practice = SimpleNamespace(live=live)
    assert not deps.tunnel_serves(services, practice)
    _room(client, live).shared = True
    assert deps.tunnel_serves(services, practice) and deps.tunnel_serves(services, live)
    assert not deps.tunnel_serves(services, "nope")


def test_shared_room_plays(client, tunnel_client) -> None:
    gid, bob = _shared_game(client)
    assert tunnel_client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": bob}).status_code == 200
    with connect_game(tunnel_client, gid, bob) as ws:
        first = ws.receive_json()
        assert first["type"] == "state" and first["view"]["viewer"] == "p2"
        ws.send_json({"type": "action", "action": {"type": "draw", "count": 7}, "id": 1})
        msgs = [ws.receive_json(), ws.receive_json()]
        assert {"type": "ack", "id": 1, "status": "ACCEPTED"} in msgs


def test_wrong_host_on_the_tunnel_port_is_404(client, tunnel_client) -> None:
    gid, bob = _shared_game(client)
    assert tunnel_client.get("/api/health").status_code == 200
    for host in ("127.0.0.1:18001", "localhost", "other.trycloudflare.com", f"{TUNNEL_HOST}:443"):
        for path in ("/", "/api/health", f"/api/games/{gid}/view"):
            res = tunnel_client.get(path, headers={"Host": host, "X-Seat-Token": bob})
            assert res.status_code == 404 and res.json() == NOT_FOUND, (host, path)
        with connect_game(tunnel_client, gid, bob, headers={"Host": host}) as ws, pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4403, host


def test_the_host_computer_on_the_tunnel_port_is_a_stranger(client, tunnel_client) -> None:
    """Review Focus 5: the host's own browser, cookie and all, reaching the tunnel port directly is refused like anyone else."""
    secret = client.app.state.services.host_secret.value
    headers = {"Host": "127.0.0.1:18001", "Cookie": f"fyodor_host={secret}"}
    for path in ("/", "/api/saves", "/api/games"):
        res = tunnel_client.get(path, headers=headers)
        assert res.status_code == 404 and res.json() == NOT_FOUND, path
    assert tunnel_client.get("/api/saves", headers={"Cookie": f"fyodor_host={secret}"}).status_code == 404  # (and with the right Host)


def test_no_origin_post_is_refused_on_the_tunnel_port(client, tunnel_client) -> None:
    gid, bob = _shared_game(client)
    bare = _tunnel_without_origin(client)
    for path, body in (("/api/join", {"code": "ZZZZZZ"}), (f"/api/games/{gid}/actions", {"action": {"type": "draw"}})):
        res = bare.post(path, json=body, headers={"X-Seat-Token": bob})
        assert res.status_code == 403 and res.json() == {"detail": "Cross-site request refused"}, path
        res = bare.post(path, json=body, headers={"X-Seat-Token": bob, "Sec-Fetch-Site": "same-origin"})
        assert res.status_code == 403 and res.json() == {"detail": "Cross-site request refused"}, path
    with connect_game(tunnel_client, gid, bob, headers={"Origin": ""}) as ws, pytest.raises(WebSocketDisconnect) as closed:
        ws.receive_json()
    assert closed.value.code == 4403
    assert tunnel_client.post(f"/api/games/{gid}/actions", json={"action": {"type": "draw"}}, headers={"X-Seat-Token": bob}).status_code == 200


def test_http_origin_is_refused_on_the_tunnel_port(client, tunnel_client) -> None:
    gid, bob = _shared_game(client)
    services = client.app.state.services
    services.extra_origins.add("https://configured.example")
    for origin in (f"http://{TUNNEL_HOST}", f"https://{TUNNEL_HOST}:8443", "https://configured.example", "http://testserver", "null"):
        res = tunnel_client.post("/api/join", json={"code": "ZZZZZZ"}, headers={"Origin": origin})
        assert res.status_code == 403 and res.json() == {"detail": "Cross-site request refused"}, origin
        with connect_game(tunnel_client, gid, bob, headers={"Origin": origin}) as ws, pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 4403, origin


def test_lan_handoff_routes_404_on_the_tunnel_port(client, tunnel_client) -> None:
    lan = {"CF-Connecting-IP": "192.168.1.5"}
    for method, path in (("POST", "/api/lan/handoff"), ("POST", "/api/lan/handoff/missing"), ("GET", "/api/lan/decks"),
                         ("GET", "/api/lan/nearby"), ("POST", "/api/lan/send-decks")):
        res = tunnel_client.request(method, path, headers=lan, content=b"{}")
        assert res.status_code == 404 and res.json() == NOT_FOUND, path


def test_games_list_and_summary_hide_codes_on_the_tunnel_port(client, tunnel_client) -> None:
    gid, _ = _shared_game(client)
    code = _room(client, gid).code
    assert any(g["code"] == code for g in client.get("/api/games").json())
    assert client.get(f"/api/games/{gid}").json()["code"] == code
    assert client.get(f"/api/games/{gid}/lobby", headers=guest()).json()["game"]["code"] == code  # (a started table, no seat)
    assert tunnel_client.get("/api/games").json() == []
    summary = tunnel_client.get(f"/api/games/{gid}").json()
    assert summary["id"] == gid and summary["code"] is None
    lobby = tunnel_client.get(f"/api/games/{gid}/lobby").json()  # no seat token: before any seat check
    assert lobby["phase"] == "playing" and lobby["game"]["id"] == gid and lobby["game"]["code"] is None


def test_an_unshared_room_cannot_be_joined_by_its_code_through_the_tunnel(client, tunnel_client) -> None:
    """Critical (review 1): a LAN code names no room through the tunnel unless that room is shared; the answer, and the failure the
    address is charged, are an unknown code's."""
    gid, code, _ = create_lobby(client)
    room = _room(client, gid)
    seats = {pid: s.token for pid, s in room.seats.items()}
    services = client.app.state.services
    unknown = tunnel_client.post("/api/join", json={"code": "ZZZZZZ", "name": "Eve"})
    res = tunnel_client.post("/api/join", json={"code": code, "name": "Eve"})
    assert res.status_code == unknown.status_code == 403 and res.json() == unknown.json() == {"detail": "Unknown room code or wrong password"}
    assert {pid: s.token for pid, s in room.seats.items()} == seats and not room.spectator_tokens  # no seat was claimed
    assert len(services.join_limiter_addr._failures["198.51.100.7"]) == 2  # both kept as failures
    assert code not in services.join_limiter_room._failures  # (a room key would say the code exists)
    room.shared = True  # once shared, the invite code joins (never the LAN code), and the answer has no code
    assert tunnel_client.post("/api/join", json={"code": code, "name": "Eve"}).status_code == 403
    invite = services.hub.new_invite_code(room)
    joined = tunnel_client.post("/api/join", json={"code": invite, "name": "Eve"})
    assert joined.status_code == 200 and joined.json()["game"]["code"] is None


def test_health_is_trimmed_for_guests(client, tunnel_client) -> None:
    from app import __version__

    assert client.get("/api/health", headers=guest()).json() == {"status": "ok", "version": __version__}
    assert tunnel_client.get("/api/health").json() == {"status": "ok", "version": __version__, "tunnel": True}
    host = client.get("/api/health").json()
    assert host["status"] == "ok" and "card_database" in host and "tunnel" not in host


def test_pod_stats_and_assets_list_404_on_the_tunnel_port(client, tunnel_client) -> None:
    for path in ("/api/pod/results", "/api/pod/players", "/api/pod/export", "/api/assets", "/api/cards/stats"):
        res = tunnel_client.get(path)
        assert res.status_code == 404 and res.json() == NOT_FOUND, path


def test_tunnel_port_serves_nothing_when_stopped(client, tunnel_client) -> None:
    gid, bob = _shared_game(client)
    client.app.state.services.tunnel.state = "stopped"
    for path in ("/", "/api/health", f"/api/games/{gid}/view"):
        res = tunnel_client.get(path, headers={"X-Seat-Token": bob})
        assert res.status_code == 404 and res.json() == NOT_FOUND, path
    with connect_game(tunnel_client, gid, bob) as ws, pytest.raises(WebSocketDisconnect) as closed:
        ws.receive_json()
    assert closed.value.code == 4403


def test_invite_hostname_is_refused_on_the_lan_port(client, tunnel_client) -> None:
    for host in (TUNNEL_HOST, f"{TUNNEL_HOST}:8000"):
        assert client.get("/api/health", headers={"Host": host}).status_code == 400, host
