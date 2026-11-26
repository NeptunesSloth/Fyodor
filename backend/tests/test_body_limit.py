"""Request bodies are bounded before a route reads them (the body limit in app/main.py): BODY_LIMIT for every route, and a larger
allowance only for the routes that bound their own bodies."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

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


def test_the_allowances_are_only_for_their_routes():
    assert body_limit("/api/join") == BODY_LIMIT
    assert body_limit("/api/host/session") == BODY_LIMIT
    assert body_limit("/api/teach/check") == BODY_LIMIT
    assert body_limit("/api/cards/batch") == BODY_LIMIT
    assert body_limit("/api/games/abc/actions") == BODY_LIMIT
    assert body_limit("/api/assets/abc") == BODY_LIMIT  # renaming an asset is small; its file is not
    assert body_limit("/api/assets/abc/file") > BODY_LIMIT
    assert body_limit("/api/assets") > BODY_LIMIT
    assert body_limit("/api/lan/handoff") > BODY_LIMIT
    assert body_limit("/api/games/abc/lobby/deck") > BODY_LIMIT
    assert body_limit("/api/games/abc/lobby/deck/x") == BODY_LIMIT  # whole path only, never a prefix
    assert body_limit("/api/joinx") == BODY_LIMIT
