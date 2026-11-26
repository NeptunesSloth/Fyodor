"""Shared rooms and invite codes: a shared LAN room has a separate 10-character invite code that only the tunnel port accepts; the
table's 6-character LAN code works on the LAN port only."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.game.visibility import SPECTATOR
from app.multiplayer import hub as hub_module
from app.multiplayer.discovery import lan_tables
from app.multiplayer.hub import CODE_ALPHABET, GameHub, Room
from tests.conftest import guest
from tests.test_lobby import create_lobby

REFUSED = {"detail": "Unknown room code or wrong password"}
OTHER = {"CF-Connecting-IP": "203.0.113.40"}


def _hub(client: Any) -> GameHub:
    return client.app.state.services.hub


def _share(client: Any, **extra: Any) -> tuple[str, str, str, Room]:
    """A lobby, shared with an invite code; (game id, LAN code, invite code, room)."""
    gid, code, _ = create_lobby(client, **extra)
    room = _hub(client).get(gid)
    room.shared = True
    return gid, code, _hub(client).new_invite_code(room), room


def test_invite_code_is_ten_characters_of_the_alphabet() -> None:
    hub = GameHub()
    room = hub._new_room("g0", "lan", None)
    hub.rooms[room.id] = room
    codes = set()
    for i in range(1, 201):
        r = hub._new_room(f"g{i}", "lan", None)
        r.invite_code = hub.new_invite_code(r)
        hub.rooms[r.id] = r
        assert len(r.invite_code) == 10 and set(r.invite_code) <= set(CODE_ALPHABET)
        codes.add(r.invite_code)
    assert len(codes) == 200
    assert hub.new_invite_code(room) != room.code


def test_invite_code_is_kept_once_made() -> None:
    hub = GameHub()
    room = hub._new_room("g", "lan", None)
    hub.rooms[room.id] = room
    first = hub.new_invite_code(room)
    assert room.invite_code == first and hub.new_invite_code(room) == first


def test_invite_code_avoids_every_room_code(monkeypatch: pytest.MonkeyPatch) -> None:
    hub = GameHub()
    room = hub._new_room("g", "lan", None)
    other = hub._new_room("h", "lan", None)
    hub.rooms.update({room.id: room, other.id: other})
    other.code = "A" * 10
    answers = iter("A" * 10 + "B" * 10)
    monkeypatch.setattr(hub_module.secrets, "choice", lambda _alphabet: next(answers))
    assert hub.new_invite_code(room) == "B" * 10


def test_tunnel_join_takes_the_invite_code_only(client, tunnel_client) -> None:
    gid, code, invite, room = _share(client, password="open sesame")
    unknown = tunnel_client.post("/api/join", json={"code": "ZZZZZZ", "password": "open sesame", "name": "Eve"})
    res = tunnel_client.post("/api/join", json={"code": code, "password": "open sesame", "name": "Eve"})
    assert res.status_code == unknown.status_code == 403 and res.json() == unknown.json() == REFUSED
    assert not room.spectator_tokens and sum(1 for s in room.seats.values() if s.token) == 1
    joined = tunnel_client.post("/api/join", json={"code": invite.lower(), "password": "open sesame", "name": "Eve"})
    assert joined.status_code == 200 and joined.json()["game_id"] == gid and joined.json()["game"]["code"] is None


def test_lan_join_never_takes_an_invite_code(client) -> None:
    _gid, code, invite, _room = _share(client)
    res = client.post("/api/join", json={"code": invite, "name": "Eve"}, headers=guest())
    assert res.status_code == 403 and res.json() == REFUSED
    assert client.post("/api/join", json={"code": code, "name": "Eve"}, headers=guest()).status_code == 200


def test_unshared_rooms_invite_code_is_refused_on_the_tunnel_port(client, tunnel_client) -> None:
    gid, code, _ = create_lobby(client)
    room = _hub(client).get(gid)
    invite = _hub(client).new_invite_code(room)  # (made earlier, then unshared)
    assert not room.shared
    services = client.app.state.services
    unknown = tunnel_client.post("/api/join", json={"code": "ZZZZZZZZZZ", "name": "Eve"})
    res = tunnel_client.post("/api/join", json={"code": invite, "name": "Eve"})
    assert res.status_code == unknown.status_code == 403 and res.json() == unknown.json() == REFUSED
    assert invite not in services.join_limiter_room._failures  # (a room key would say the code exists)
    assert len(services.join_limiter_addr._failures["198.51.100.7"]) == 2


def test_wrong_password_on_the_tunnel_port_counts_against_cf_address(client, tunnel_client) -> None:
    _gid, _code, invite, _room = _share(client, password="right")
    for _ in range(5):
        res = tunnel_client.post("/api/join", json={"code": invite, "password": "wrong", "name": "Eve"})
        assert res.status_code == 403
    assert tunnel_client.post("/api/join", json={"code": invite, "password": "wrong", "name": "Eve"}).status_code == 429
    ok = tunnel_client.post("/api/join", json={"code": invite, "password": "right", "name": "Zed"}, headers=OTHER)
    assert ok.status_code == 200


def _started(client: Any) -> Room:
    from tests.test_tunnel_routes import _shared_game

    gid, _ = _shared_game(client)
    return _hub(client).get(gid)


def test_metadata_without_the_fields_loads(client) -> None:
    room = _started(client)
    hub = _hub(client)
    meta = hub.meta(room)
    meta.pop("invite_code")
    meta.pop("shared", None)
    hub.rooms.pop(room.id)
    back = hub.restore(meta, room.session, {})
    assert back.invite_code is None and back.shared is False


def test_restore_keeps_the_invite_code_and_is_not_shared(client) -> None:
    room = _started(client)
    hub = _hub(client)
    invite = hub.new_invite_code(room)
    meta = hub.meta(room)
    assert meta["invite_code"] == invite
    hub.rooms.pop(room.id)
    back = hub.restore(meta, room.session, {})
    assert back.invite_code == invite and back.shared is False
    assert hub.by_invite_code(invite) is None  # (closing Fyodor ended the link)
    back.shared = True
    assert hub.by_invite_code(invite) is back and hub.by_code(invite) is None


def test_views_say_shared_and_never_the_invite_code(client, tunnel_client) -> None:
    gid, _code, invite, room = _share(client)
    alice = next(s.token for s in room.seats.values() if s.token)
    lobby = tunnel_client.get(f"/api/games/{gid}/lobby", headers={"X-Seat-Token": alice}).json()
    assert lobby["game"]["shared"] is True
    listing = client.get("/api/games").json()
    assert any(g["id"] == gid and g["shared"] is True for g in listing)
    assert client.get(f"/api/games/{gid}").json()["shared"] is True
    seat = tunnel_client.post("/api/join", json={"code": invite, "name": "Eve"}).json()
    walk = [lobby, listing, seat, client.get(f"/api/games/{gid}").json(), room.summary(),
            tunnel_client.get(f"/api/games/{gid}/lobby", headers={"X-Seat-Token": seat["token"]}).json()]
    assert invite not in json.dumps(walk)
    # a started table: a seated view and a spectator view
    started = _started(client)
    invite2 = _hub(client).new_invite_code(started)
    seated = _hub(client).view(started, "p1")
    watching = _hub(client).view(started, SPECTATOR)
    assert seated["game"]["shared"] is True and watching["game"]["shared"] is True  # (_shared_game shares it)
    started.shared = False
    assert _hub(client).view(started, "p1")["game"]["shared"] is False
    assert invite2 not in json.dumps([seated, watching, _hub(client).view(started, "p1"), started.summary(commanders=True)])


def test_discovery_never_advertises_the_invite(client) -> None:
    _gid, _code, invite, room = _share(client)
    body = json.dumps(lan_tables([room]))
    assert invite not in body and "invite_code" not in body


def test_set_password_hashes_at_current_rounds(client) -> None:
    _gid, _code, _invite, room = _share(client, password="old")
    hub = _hub(client)
    before = room.password_state()
    room.password_rounds = 1000
    hub.set_password(room, "new")
    salt, stored, rounds = room.password_state()
    assert rounds == hub_module.PASSWORD_ROUNDS and salt != before[0] and stored != before[1]
    assert room.check_password("new") and not room.check_password("old")


def test_non_ascii_token_matches_nothing(client) -> None:
    room = _started(client)
    assert room.seat_for_token("tökén") is None and not room.is_host("tökén")
    gid = room.id
    res = client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": "tökén".encode("latin-1")})
    assert res.status_code < 500
    assert _hub(client).by_invite_code("ÄÄÄÄÄÄÄÄÄÄ") is None
