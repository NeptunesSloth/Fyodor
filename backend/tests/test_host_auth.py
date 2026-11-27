"""Host authority is a secret held in a cookie, never the peer address (app/hostauth.py, app/api/deps.py)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_loopback_without_cookie_is_not_host(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:  # peer "testclient" = loopback
        assert c.get("/api/saves").status_code == 403


def test_cookie_makes_host(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        secret = c.app.state.services.host_secret.value  # type: ignore[attr-defined]
        assert c.post("/api/host/session", json={"secret": secret}).status_code == 204
        assert c.get("/api/saves").status_code == 200


def test_wrong_secret_refused_and_sets_nothing(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        r = c.post("/api/host/session", json={"secret": "x" * 43})
        assert r.status_code == 403 and "set-cookie" not in r.headers
        assert c.get("/api/saves").status_code == 403


def test_forged_forwarded_for_gives_nothing(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/saves", headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 403


def test_forged_cookie_gives_nothing(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        c.cookies.set("fyodor_host", "x" * 43)
        assert c.get("/api/saves").status_code == 403
        c.cookies.set("fyodor_host", "")
        assert c.get("/api/saves").status_code == 403


def test_cookie_flags(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        r = c.post("/api/host/session", json={"secret": c.app.state.services.host_secret.value})  # type: ignore[attr-defined]
        flags = r.headers["set-cookie"].lower()
        assert "httponly" in flags and "samesite=strict" in flags and "path=/" in flags
        assert "secure" not in flags  # plain http on the LAN


def test_cookie_is_secure_over_https(settings: Settings) -> None:
    with TestClient(create_app(settings), base_url="https://testserver") as c:
        r = c.post("/api/host/session", json={"secret": c.app.state.services.host_secret.value})  # type: ignore[attr-defined]
        assert "secure" in r.headers["set-cookie"].lower().split("; ")


def test_https_session_sets_the_host_prefixed_cookie(settings: Settings) -> None:
    with TestClient(create_app(settings), base_url="https://testserver") as c:
        r = c.post("/api/host/session", json={"secret": c.app.state.services.host_secret.value})  # type: ignore[attr-defined]
        cookie = r.headers["set-cookie"].lower()
        assert cookie.startswith("__host-fyodor_host=")
        assert "secure" in cookie.split("; ") and "path=/" in cookie and "domain=" not in cookie


def test_either_cookie_name_is_the_host(settings: Settings) -> None:
    for name in ("fyodor_host", "__Host-fyodor_host"):
        with TestClient(create_app(settings)) as c:
            c.cookies.set(name, c.app.state.services.host_secret.value)  # type: ignore[attr-defined]
            assert c.get("/api/host/session").json() == {"host": True}


def test_plain_http_keeps_the_plain_name(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        r = c.post("/api/host/session", json={"secret": c.app.state.services.host_secret.value})  # type: ignore[attr-defined]
        assert r.headers["set-cookie"].startswith("fyodor_host=")


def test_secret_changes_each_start_and_file_is_private(settings: Settings) -> None:
    with TestClient(create_app(settings)) as a:
        first = a.app.state.services.host_secret.value  # type: ignore[attr-defined]
        assert (settings.data_dir / "host.secret").read_text().strip() == first
    with TestClient(create_app(settings)) as b:
        second = b.app.state.services.host_secret.value  # type: ignore[attr-defined]
        assert second != first
        assert (settings.data_dir / "host.secret").read_text().strip() == second


def test_a_host_cookie_from_a_previous_start_is_refused(settings: Settings) -> None:
    # a restart makes a new secret: the host window from before it (still holding the old cookie) is a guest afterwards
    with TestClient(create_app(settings)) as a:
        assert a.post("/api/host/session", json={"secret": a.app.state.services.host_secret.value}).status_code == 204  # type: ignore[attr-defined]
        old = a.cookies.get("fyodor_host")
        assert old and a.get("/api/saves").status_code == 200
    with TestClient(create_app(settings)) as b:
        b.cookies.set("fyodor_host", old)
        assert b.get("/api/saves").status_code == 403
        assert b.get("/api/host/session").json() == {"host": False}


def test_matches_is_false_for_nothing(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        secret = c.app.state.services.host_secret  # type: ignore[attr-defined]
        assert secret.matches(secret.value) is True
        assert secret.matches(None) is False and secret.matches("") is False


def test_session_state_reports_host_false_without_the_cookie(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/host/session").json() == {"host": False}
        c.post("/api/host/session", json={"secret": c.app.state.services.host_secret.value})  # type: ignore[attr-defined]
        assert c.get("/api/host/session").json() == {"host": True}


def test_a_refusal_says_how_to_become_the_host(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/saves").json()["detail"] == "Open Fyodor from its launcher on the host computer to use host tools."


def test_an_older_secret_file_is_replaced_not_reused(settings: Settings) -> None:
    settings.ensure_dirs()
    (settings.data_dir / "host.secret").write_text("old-and-readable")
    with TestClient(create_app(settings)) as c:
        assert (settings.data_dir / "host.secret").read_text().strip() == c.app.state.services.host_secret.value  # type: ignore[attr-defined]


def test_an_oversized_secret_is_a_422_that_costs_the_address_nothing(settings: Settings) -> None:
    """A malformed body is refused before any compare and is not a wrong guess: a stranger cannot use it to spend the host's budget
    (five wrong secrets per address per 15 minutes)."""
    with TestClient(create_app(settings)) as c:
        for _ in range(8):
            r = c.post("/api/host/session", json={"secret": "x" * 10_000})
            assert r.status_code == 422 and "set-cookie" not in r.headers
        for _ in range(5):  # the whole budget is still there
            assert c.post("/api/host/session", json={"secret": "x" * 43}).status_code == 403
        secret = c.app.state.services.host_secret.value  # type: ignore[attr-defined]
        assert c.post("/api/host/session", json={"secret": secret}).status_code == 204
