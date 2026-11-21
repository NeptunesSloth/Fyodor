"""The client address (for rate limits and logs) comes from X-Forwarded-For only when a configured proxy sent it (app/api/deps.py)."""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.config import Settings, load_settings
from app.main import create_app


@pytest.mark.parametrize("trusted,peer,xff,expected", [
    ((), "203.0.113.9", "127.0.0.1", "203.0.113.9"),                      # header ignored by default
    (("127.0.0.1",), "127.0.0.1", "198.51.100.7", "198.51.100.7"),
    (("127.0.0.1",), "127.0.0.1", "1.2.3.4, 198.51.100.7", "198.51.100.7"),  # rightmost, not first
    (("127.0.0.1", "10.0.0.0/8"), "127.0.0.1", "198.51.100.7, 10.0.0.2", "198.51.100.7"),
    (("127.0.0.1",), "127.0.0.1", "not-an-ip", "127.0.0.1"),
    (("127.0.0.1",), "127.0.0.1", None, "127.0.0.1"),
    (("127.0.0.1",), "::ffff:127.0.0.1", "198.51.100.7", "198.51.100.7"),  # IPv4-mapped peer matches an IPv4 entry
    (("127.0.0.1",), "203.0.113.9", "198.51.100.7", "203.0.113.9"),        # peer not a proxy: header ignored
    (("127.0.0.1",), "127.0.0.1", "198.51.100.7, ::ffff:127.0.0.1", "198.51.100.7"),
    (("127.0.0.1",), "127.0.0.1", "127.0.0.1, 127.0.0.1", "127.0.0.1"),    # every hop trusted: the peer
    (("127.0.0.1",), "127.0.0.1", "198.51.100.7, junk", "127.0.0.1"),      # a garbled hop poisons the chain
    ((), None, "198.51.100.7", ""),                                        # no peer at all: one shared bucket
    (("127.0.0.1",), None, "198.51.100.7", ""),
    ((), "testclient", None, "testclient"),                                # a non-IP peer is passed through, never trusted
])
def test_client_address(trusted, peer, xff, expected):
    assert deps._resolve(peer, xff, trusted) == expected


def test_settings_trusted_proxies(tmp_path):
    base = {"FYODOR_DATA_DIR": str(tmp_path)}
    assert load_settings(base).trusted_proxies == ()
    assert load_settings({**base, "FYODOR_TRUSTED_PROXIES": " "}).trusted_proxies == ()
    assert load_settings({**base, "FYODOR_TRUSTED_PROXIES": "127.0.0.1, 10.0.0.0/8"}).trusted_proxies == ("127.0.0.1", "10.0.0.0/8")


@pytest.mark.parametrize("bad", ["nope", "127.0.0.1, 300.1.1.1", "10.0.0.0/99"])
def test_settings_bad_trusted_proxy_is_a_startup_error(tmp_path, bad):
    with pytest.raises(ValueError, match="FYODOR_TRUSTED_PROXIES"):
        load_settings({"FYODOR_DATA_DIR": str(tmp_path), "FYODOR_TRUSTED_PROXIES": bad})


def test_forged_forwarded_for_does_not_pass_the_lan_gate(settings: Settings):
    forged = {"X-Forwarded-For": "192.168.1.5", "content-type": "application/json"}
    with TestClient(create_app(settings), client=("8.8.8.8", 5000)) as c:
        assert c.post("/api/lan/handoff", content=b"{}", headers=forged).status_code == 403
        assert c.post("/api/lan/handoff/missing", json={"ids": []}, headers=forged).status_code == 403
        assert c.post("/api/lan/handoff", content=b"{}", headers={**forged, "X-Forwarded-For": "127.0.0.1"}).status_code == 403


def test_forged_forwarded_for_from_loopback_does_not_pass_either(settings: Settings):
    with TestClient(create_app(settings), client=("127.0.0.1", 5000)) as c:  # nothing trusted: loopback is just a peer
        r = c.post("/api/lan/handoff/missing", json={"ids": []}, headers={"X-Forwarded-For": "8.8.8.8"})
        assert r.status_code == 200  # the peer (loopback) is on the local network; the header said otherwise and was ignored


def test_trusted_proxy_hands_over_the_real_client(settings: Settings):
    behind = dataclasses.replace(settings, trusted_proxies=("127.0.0.1",))
    with TestClient(create_app(behind), client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/lan/handoff/missing", json={"ids": []}, headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 403


def test_forged_header_does_not_change_the_join_throttle_key(settings: Settings):
    with TestClient(create_app(settings), client=("203.0.113.9", 5000)) as c:
        for i in range(5):
            assert c.post("/api/join", json={"code": "NOPE", "name": "x"}, headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code == 403
        assert c.post("/api/join", json={"code": "NOPE", "name": "x"}, headers={"X-Forwarded-For": "10.9.9.9"}).status_code == 429
