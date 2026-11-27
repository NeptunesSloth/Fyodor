"""Request bodies are bounded before a route reads them (the body limit in app/main.py): BODY_LIMIT for every route, and a larger
allowance only for the routes that bound their own bodies."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.assets.validate import MAX_BYTES
from app.main import BODY_LIMIT, TOO_LARGE, body_limit
from tests.conftest import guest
from tests.test_lobby import create_lobby, h

JSON = {"Content-Type": "application/json"}


def _padded_join(size: int) -> bytes:
    # a join a handler would answer (a wrong code: 403, counted against the address), padded with a field the model ignores
    body = json.dumps({"code": "ZZZZZZ", "name": "Mallory", "pad": ""}).encode()
    return body[:-2] + b"x" * (size - len(body)) + b'"}'


def _chunks(data: bytes, size: int = 64 * 1024):
    # a generator body: the client sends it chunked, with no Content-Length
    for i in range(0, len(data), size):
        yield data[i:i + size]


def test_an_oversized_join_is_413_before_the_handler(client: TestClient):
    services = client.app.state.services  # type: ignore[attr-defined]
    res = client.post("/api/join", content=_padded_join(BODY_LIMIT + 1), headers={**JSON, **guest(client)})
    assert res.status_code == 413, res.text
    assert not services.join_limiter_addr._failures  # the handler never ran: nothing was counted
    # the same join under the limit reaches the handler (a wrong code)
    assert client.post("/api/join", content=_padded_join(BODY_LIMIT - 1024), headers={**JSON, **guest(client)}).status_code == 403


def test_a_chunked_body_without_a_length_is_counted_as_it_arrives(client: TestClient):
    services = client.app.state.services  # type: ignore[attr-defined]
    res = client.post("/api/join", content=_chunks(_padded_join(BODY_LIMIT + 1)), headers={**JSON, **guest(client)})
    assert "content-length" not in res.request.headers and res.request.headers.get("transfer-encoding") == "chunked"
    assert res.status_code == 413, res.text
    assert not services.join_limiter_addr._failures


def test_a_route_with_its_own_bound_takes_a_larger_body(client: TestClient):
    # Teach Fyodor's import file may be 512 KB (app/storage/taught.py): a 300 KB file reaches the route, which reads it and says what it
    # thinks of it (not a Teach Fyodor file), sent with a length and sent chunked
    raw = b"[" + b" " * 300_000 + b"]x"
    assert client.post("/api/teach/import", content=raw, headers=JSON).status_code == 422
    assert client.post("/api/teach/import", content=_chunks(raw), headers=JSON).status_code == 422
    # and over that route's own bound it is refused before the route reads it
    assert client.post("/api/teach/import", content=b" " * (600 * 1024), headers=JSON).status_code == 413


def test_a_deck_at_its_own_bound_is_not_refused(client: TestClient):
    # the lobby takes saved Archidekt JSON up to 2,000,000 characters and the deck library up to 5,000,000 (their models): such a body
    # reaches the route, which answers it itself (not a deck it can read), never with the body limit's refusal
    gid, _code, alice = create_lobby(client)
    lobby = client.post(f"/api/games/{gid}/lobby/deck", json={"json": "x" * 2_000_000}, headers=h(alice))
    assert lobby.status_code != 500 and lobby.json()["detail"] != TOO_LARGE, lobby.text
    deck = client.post("/api/decks/preview", json={"json": "x" * 5_000_000})
    assert deck.status_code != 500 and deck.json()["detail"] != TOO_LARGE, deck.text


def _no_seat(_path: str) -> bool:
    return False


def _any_seat(_path: str) -> bool:
    return True


def test_the_allowances_are_only_for_their_routes():
    def limit(path: str) -> int:
        return body_limit(path, host=True, seat_ok=_any_seat, tunnel=False)

    assert limit("/api/join") == BODY_LIMIT
    assert limit("/api/host/session") == BODY_LIMIT
    assert limit("/api/teach/check") == BODY_LIMIT
    assert limit("/api/cards/batch") == BODY_LIMIT
    assert limit("/api/games/abc/actions") == BODY_LIMIT
    assert limit("/api/assets/abc") == BODY_LIMIT  # renaming an asset is small; its file is not
    assert limit("/api/assets/abc/file") > BODY_LIMIT
    assert limit("/api/assets") > BODY_LIMIT
    assert limit("/api/lan/handoff") > BODY_LIMIT
    assert limit("/api/games/abc/lobby/deck") > BODY_LIMIT
    assert limit("/api/games/abc/lobby/deck/x") == BODY_LIMIT  # whole path only, never a prefix
    assert limit("/api/joinx") == BODY_LIMIT


def test_who_may_use_an_allowance():
    assert body_limit("/api/assets", host=False, seat_ok=_no_seat, tunnel=False) > BODY_LIMIT  # "any": the route stops it itself
    assert body_limit("/api/backups/restore", host=False, seat_ok=_any_seat, tunnel=False) == BODY_LIMIT  # "host"
    assert body_limit("/api/backups/restore", host=True, seat_ok=_no_seat, tunnel=False) > BODY_LIMIT
    assert body_limit("/api/games/abc/lobby/deck", host=False, seat_ok=_no_seat, tunnel=False) == BODY_LIMIT  # "seat"
    assert body_limit("/api/games/abc/lobby/deck", host=True, seat_ok=_no_seat, tunnel=False) > BODY_LIMIT
    assert body_limit("/api/games/abc/lobby/deck", host=False, seat_ok=_any_seat, tunnel=False) > BODY_LIMIT
    # on the tunnel port: never an "any" or "host" allowance (whatever the caller says about host); a seat keeps the lobby's
    for path in ("/api/assets", "/api/lan/handoff", "/api/lan/handoff/missing", "/api/backups/restore", "/api/browser-decks"):
        assert body_limit(path, host=True, seat_ok=_any_seat, tunnel=True) == BODY_LIMIT
    assert body_limit("/api/games/abc/lobby/deck", host=True, seat_ok=_no_seat, tunnel=True) == BODY_LIMIT
    assert body_limit("/api/games/abc/lobby/deck", host=False, seat_ok=_any_seat, tunnel=True) > BODY_LIMIT


BIG = {"json": "x" * 300_000}


def test_a_guest_gets_256k_on_host_routes(client: TestClient):
    res = client.put("/api/browser-decks", content=b"x" * 300_000, headers={**JSON, **guest(client)})
    assert res.status_code == 413 and res.json()["detail"] == TOO_LARGE, res.text
    assert client.post("/api/decks/preview", json=BIG, headers=guest(client)).json()["detail"] == TOO_LARGE


def test_the_host_keeps_the_large_allowance(client: TestClient):
    res = client.put("/api/browser-decks", content=b"x" * 300_000, headers=JSON)
    assert res.json()["detail"] != TOO_LARGE, res.text
    assert client.post("/api/decks/preview", json=BIG).json()["detail"] != TOO_LARGE


def test_a_stranger_gets_256k_on_lobby_routes(client: TestClient):
    gid, _code, _alice = create_lobby(client)
    _gid2, _code2, other_token = create_lobby(client)
    for headers in ({}, h("not-a-token"), h(other_token)):
        res = client.post(f"/api/games/{gid}/lobby/deck", json=BIG, headers={**guest(client), **headers})
        assert res.status_code == 413 and res.json()["detail"] == TOO_LARGE, (headers, res.text)


def test_a_seat_keeps_the_lobby_allowance(client: TestClient):
    gid, code, alice = create_lobby(client)
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    for token in (alice, bob):
        res = client.post(f"/api/games/{gid}/lobby/deck", json=BIG, headers={**guest(client), **h(token)})
        assert res.json()["detail"] != TOO_LARGE, res.text
    # the host, with no seat token at all
    assert client.post(f"/api/games/{gid}/lobby/deck", json=BIG).json()["detail"] != TOO_LARGE


# a "My decks" collection of 1,800 distinct cards (about 15-20 saved Commander decks): over 256 KB as JSON
COLLECTION = {"collection": [{"name": "Some Card Name", "quantity": 1, "section": "main",
                              "printing_id": "00000000-0000-0000-0000-000000000000",
                              "oracle_id": "00000000-0000-0000-0000-000000000000"}] * 1800}


def test_on_the_tunnel_port_a_seat_keeps_the_lobby_allowance(client: TestClient, tunnel_client: TestClient):
    assert len(json.dumps(COLLECTION)) > BODY_LIMIT
    gid, code, _alice = create_lobby(client)
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    _gid2, _code2, other_token = create_lobby(client)
    client.app.state.services.hub.get(gid).shared = True  # type: ignore[attr-defined]
    # a seat of the shared table, through the invite link: the body reaches the route (which answers for the cards it can't find)
    res = tunnel_client.post(f"/api/games/{gid}/lobby/collection", json=COLLECTION, headers=h(bob))
    assert res.status_code != 413 and res.json()["detail"] != TOO_LARGE, res.text
    # a stranger, a made-up token or another table's seat: 256 KB
    for headers in ({}, h("not-a-token"), h(other_token)):
        res = tunnel_client.post(f"/api/games/{gid}/lobby/collection", json=COLLECTION, headers=headers)
        assert res.status_code == 413 and res.json()["detail"] == TOO_LARGE, (headers, res.text)


def test_no_host_or_any_allowance_on_the_tunnel_port():
    # whatever the caller says about the host, and whoever holds a seat: those allowances are the LAN's
    for path in ("/api/browser-decks", "/api/decks/preview", "/api/teach/import", "/api/assets", "/api/lan/handoff"):
        assert body_limit(path, host=True, seat_ok=_any_seat, tunnel=True) == BODY_LIMIT, path


def test_the_route_speaks_first_for_streamed_uploads(client: TestClient):
    # just over the image limit, so past the route's bound but within bound + BODY_LIMIT: the route's own words are what the user reads
    res = client.post("/api/assets?kind=playmat", content=b"x" * (MAX_BYTES + 1024), headers={"Content-Type": "image/png"})
    assert res.status_code == 413 and res.json()["detail"] == "Images are limited to 20 MB", res.text
