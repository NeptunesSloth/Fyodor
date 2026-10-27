"""The one-command launcher's preflight checks (no server is started)."""

from __future__ import annotations

import socket

from app import launcher
from app.config import load_settings


def test_preflight_reports_what_is_missing(tmp_path, capsys):
    env = {"FYODOR_DATA_DIR": str(tmp_path / "data"), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist"), "FYODOR_PORT": "0"}
    checks = {c.label.split(":")[0].split(" ")[0]: c for c in launcher.preflight(load_settings(env))}
    assert checks["Data"].ok and checks["Python"].ok
    assert not checks["Card"].ok and "update-cards" in checks["Card"].hint
    assert not checks["Table"].ok and "npm run build" in checks["Table"].hint


def test_busy_port_is_detected():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        assert not launcher.port_free("127.0.0.1", s.getsockname()[1])


def test_check_mode_exits_without_serving(tmp_path, monkeypatch, capsys):
    dist = tmp_path / "dist"
    dist.mkdir()
    for k, v in {"FYODOR_DATA_DIR": str(tmp_path / "d"), "FYODOR_FRONTEND_DIST": str(dist)}.items():
        monkeypatch.setenv(k, v)
    code = launcher.main(["--check", "--port", "0", "--no-browser"])
    out = capsys.readouterr().out
    assert code == 0 and "Card database missing" in out  # advisory, not blocking


def test_first_run_downloads_the_cards_and_lets_the_pod_join(tmp_path, monkeypatch, capsys):
    dist = tmp_path / "dist"
    dist.mkdir()
    for k, v in {"FYODOR_DATA_DIR": str(tmp_path / "d"), "FYODOR_FRONTEND_DIST": str(dist)}.items():
        monkeypatch.setenv(k, v)
    calls: list[list[str]] = []
    served: dict[str, object] = {}
    import uvicorn

    import tools.update_cards

    monkeypatch.setattr(tools.update_cards, "main", lambda argv: calls.append(argv) or 0)
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: served.update(kw))
    assert launcher.main(["--port", "0", "--no-browser"]) == 0
    assert calls and calls[0][:2] == ["--images", "none"]  # missing card database: fetched once
    assert served["host"] == "0.0.0.0"  # LAN by default
    launcher.main(["--port", "0", "--no-browser", "--local"])
    assert served["host"] == "127.0.0.1"
