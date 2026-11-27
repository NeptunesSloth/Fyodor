"""Response headers (HSTS only over https, CSP, framing, referrer), the API docs being absent outside development, and player text
that reaches a log (app/main.py, app/api/deps.py, app/multiplayer/hub.py, app/cards/art_keeper.py)."""

from __future__ import annotations

import dataclasses
import logging

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.decks.models import DeckIn
from app.main import CSP, create_app, csp
from app.multiplayer.lobby import LobbySettings

HSTS = "max-age=31536000"
PROXY = ("127.0.0.1",)


def _client(settings: Settings, *, https: bool = False, peer: str = "203.0.113.9", **changes) -> TestClient:
    app = create_app(dataclasses.replace(settings, **changes))
    return TestClient(app, base_url="https://testserver" if https else "http://testserver", client=(peer, 5000))


# ------------------------------------------------------------------------------------------------------------------- HSTS


def test_no_hsts_on_plain_http(settings: Settings):
    with _client(settings) as c:
        assert "strict-transport-security" not in c.get("/api/health").headers


def test_hsts_on_direct_https(settings: Settings):
    with _client(settings, https=True) as c:
        assert c.get("/api/health").headers["strict-transport-security"] == HSTS


def test_hsts_when_a_trusted_proxy_says_https(settings: Settings):
    with _client(settings, peer="127.0.0.1", trusted_proxies=PROXY) as c:
        res = c.get("/api/health", headers={"X-Forwarded-Proto": "https"})
        assert res.headers["strict-transport-security"] == HSTS


def test_no_hsts_when_a_stranger_says_https(settings: Settings):
    with _client(settings, peer="203.0.113.9", trusted_proxies=PROXY) as c:
        assert "strict-transport-security" not in c.get("/api/health", headers={"X-Forwarded-Proto": "https"}).headers
    with _client(settings, peer="127.0.0.1") as c:  # nothing trusted: even loopback is just a peer
        assert "strict-transport-security" not in c.get("/api/health", headers={"X-Forwarded-Proto": "https"}).headers


def test_a_trusted_proxy_saying_http_gets_no_hsts(settings: Settings):
    with _client(settings, peer="127.0.0.1", trusted_proxies=PROXY) as c:
        assert "strict-transport-security" not in c.get("/api/health", headers={"X-Forwarded-Proto": "http"}).headers


def test_hsts_is_exactly_max_age(settings: Settings):
    with _client(settings, https=True) as c:
        value = c.get("/api/health").headers["strict-transport-security"].lower()
    assert "includesubdomains" not in value and "preload" not in value


def test_refusals_carry_the_headers_too(settings: Settings):
    with _client(settings, https=True) as c:
        bad_host = c.get("/api/health", headers={"Host": "evil.example"})
        cross = c.post("/api/games", json={}, headers={"Sec-Fetch-Site": "cross-site"})
        too_large = c.post("/api/join", content=b"x" * (300 * 1024), headers={"Content-Type": "application/json"})
    for res, code in ((bad_host, 400), (cross, 403), (too_large, 413)):
        assert res.status_code == code
        assert res.headers["strict-transport-security"] == HSTS
        assert res.headers["x-content-type-options"] == "nosniff"


# --------------------------------------------------------------------------------------------- what is always sent, pinned


def test_always_sent_headers(settings: Settings):
    with _client(settings) as c:
        h = c.get("/api/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "no-referrer"
    assert h["content-security-policy"] == csp("testserver")


def test_csp_pins():
    directives = {d.split()[0]: d.split()[1:] for d in (p.strip() for p in CSP.split(";")) if d}
    assert directives["default-src"] == ["'self'"]
    assert directives["frame-ancestors"] == ["'none'"]
    assert directives["object-src"] == ["'none'"]
    assert "unsafe-eval" not in CSP
    assert directives["script-src"] == ["'self'"]
    # every source anywhere in the policy is a keyword or 'self': no host, and no bare ws:/wss: scheme (any host); data: is for
    # inline images only. (The game socket's own host is named per request: test_connect_src_names_this_host)
    allowed = {"'self'", "'none'", "'unsafe-inline'", "data:"}
    for name, sources in directives.items():
        if name in {"frame-ancestors", "base-uri", "form-action", "object-src"}:
            continue
        assert set(sources) <= allowed, (name, sources)
    assert "http:" not in CSP and "https:" not in CSP and "*" not in CSP


def test_connect_src_names_this_host(settings: Settings):
    with _client(settings) as c:
        csp = c.get("/api/health", headers={"Host": "192.168.1.20:8000"}).headers["content-security-policy"]
    assert "connect-src 'self' ws://192.168.1.20:8000 wss://192.168.1.20:8000;" in csp


def test_refused_host_gets_self_only(settings: Settings):
    with _client(settings) as c:
        res = c.get("/api/health", headers={"Host": "evil.example"})
    assert res.status_code == 400
    assert "connect-src 'self';" in res.headers["content-security-policy"]
    assert "evil" not in res.headers["content-security-policy"]


def test_csp_never_echoes_odd_host_text():
    assert csp("a;b") == CSP and csp("x y") == CSP and csp("[fe80::1%a;b]") == CSP and csp("") == CSP


# ------------------------------------------------------------------------------------------------------------ the API docs


def test_docs_are_absent_by_default(settings: Settings):
    assert settings.dev_tools is False
    with _client(settings) as c:
        for path in ("/openapi.json", "/docs", "/redoc"):
            res = c.get(path)
            assert res.status_code == 404, path
            assert "openapi" not in res.text.lower() and "swagger" not in res.text.lower(), path


def test_docs_are_served_with_dev_tools(settings: Settings):
    with _client(settings, dev_tools=True) as c:
        assert c.get("/openapi.json").json()["openapi"].startswith("3.")
        assert "swagger" in c.get("/docs").text.lower()
        assert c.get("/redoc").status_code == 200


# ----------------------------------------------------------------------------------------------------------------- the logs

FORGED = "Friday\nINFO     app.fake: forged line\x1b[31m red\x1b]0;title\x07"


def _assert_one_clean_line(caplog: pytest.LogCaptureFixture, marker: str) -> None:
    records = [r for r in caplog.records if marker in r.getMessage()]
    assert records, "the log line was not written"
    for r in records:
        text = r.getMessage()
        assert "\n" not in text and "\r" not in text and not any(ord(ch) < 32 or ord(ch) == 127 for ch in text), repr(text)
    formatted = [logging.Formatter("%(message)s").format(r) for r in records]
    assert all(len(f.splitlines()) == 1 for f in formatted)


def test_lobby_name_cannot_forge_a_log_line(client: TestClient, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO):
        res = client.post("/api/games", json={"mode": "lan", "lobby": True, "name": FORGED, "seats": 4, "players": []})
    assert res.status_code == 201, res.text
    _assert_one_clean_line(caplog, "Created lobby")


def test_lobby_name_is_clean_before_it_is_logged(settings: Settings, caplog: pytest.LogCaptureFixture):
    with _client(settings) as c, caplog.at_level(logging.INFO):
        c.app.state.services.hub.create_lobby(LobbySettings(name=FORGED))
    _assert_one_clean_line(caplog, "Created lobby")


def test_deck_name_is_clean_before_the_art_keeper_logs_it():
    assert not any(ord(ch) < 32 for ch in DeckIn(name=FORGED, entries=[]).name)


# ------------------------------------------------------------------------------------- the host cookie follows the same rule


def _claim(c: TestClient, **headers: str):
    return c.post("/api/host/session", json={"secret": c.app.state.services.host_secret.value}, headers=headers)


def _secure(res) -> bool:
    return "secure" in res.headers["set-cookie"].lower().split("; ")


def test_host_cookie_is_secure_behind_a_trusted_proxy_saying_https(settings: Settings):
    with _client(settings, peer="127.0.0.1", trusted_proxies=PROXY) as c:
        assert _secure(_claim(c, **{"X-Forwarded-Proto": "https"}))


def test_host_cookie_ignores_a_strangers_https_claim(settings: Settings):
    with _client(settings, peer="203.0.113.9", trusted_proxies=PROXY) as c:
        assert not _secure(_claim(c, **{"X-Forwarded-Proto": "https"}))
    with _client(settings, peer="127.0.0.1") as c:  # nothing trusted
        assert not _secure(_claim(c, **{"X-Forwarded-Proto": "https"}))


def test_host_cookie_is_not_secure_on_plain_http(settings: Settings):
    with _client(settings) as c:
        assert not _secure(_claim(c))
