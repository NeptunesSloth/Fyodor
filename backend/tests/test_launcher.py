"""The one-command launcher's preflight checks (no server is started)."""

from __future__ import annotations

import socket
import sqlite3

import pytest

from app import launcher
from app.config import load_settings


@pytest.fixture(autouse=True)
def install_dir(tmp_path, monkeypatch):
    """A Fyodor install of the test's own (no bundled window or card database unless a test puts one there)."""
    root = tmp_path / "install"
    root.mkdir()
    monkeypatch.setattr(launcher, "_install_dir", lambda: root)
    # nor a Chrome/Edge of this computer's: a developer's Windows usually has one, which would always win
    monkeypatch.setattr(launcher, "installed_browsers", lambda: [])
    return root


def test_preflight_reports_what_is_missing(tmp_path, capsys):
    env = {"FYODOR_DATA_DIR": str(tmp_path / "data"), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist"), "FYODOR_PORT": "0"}
    checks = {c.label.split(":")[0].split(" ")[0]: c for c in launcher.preflight(load_settings(env))}
    assert checks["Data"].ok and checks["Python"].ok
    assert not checks["Card"].ok and "Settings → Card database" in checks["Card"].hint
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
    import tools.update_cards

    monkeypatch.setattr(tools.update_cards, "main", lambda argv: calls.append(argv) or 0)
    monkeypatch.setattr(launcher, "serve", lambda settings, browser=False: served.update(host=settings.host))
    assert launcher.main(["--port", "0", "--no-browser"]) == 0
    assert calls and calls[0][:2] == ["--images", "none"]  # missing card database: fetched once
    assert served["host"] == "0.0.0.0"  # LAN by default
    launcher.main(["--port", "0", "--no-browser", "--local"])
    assert served["host"] == "127.0.0.1"


def test_check_output_survives_a_console_that_cannot_print_check_marks(tmp_path):
    """Windows writes redirected output in its ANSI code page (cp1252): `Fyodor.exe --check > out.txt` must not crash on ✓/✗."""
    import os
    import subprocess
    import sys

    dist = tmp_path / "dist"
    dist.mkdir()
    env = {**os.environ, "FYODOR_DATA_DIR": str(tmp_path / "d"), "FYODOR_FRONTEND_DIST": str(dist), "PYTHONIOENCODING": "cp1252"}
    run = subprocess.run([sys.executable, "-m", "app.launcher", "--check", "--port", "0", "--no-browser"],
                         capture_output=True, env=env, timeout=60)
    assert run.returncode == 0, run.stderr.decode("cp1252", "replace")[-600:]
    assert b"Card database missing" in run.stdout


def test_the_installer_s_card_database_is_put_in_place_on_the_first_start(tmp_path, install_dir):
    (install_dir / "seed").mkdir()
    sqlite3.connect(install_dir / "seed" / "cards.sqlite").execute("create table t (x)").connection.commit()
    settings = load_settings({"FYODOR_DATA_DIR": str(tmp_path / "d")})
    assert launcher.seed_card_database(settings) and settings.cards_db_path.is_file()
    assert not settings.cards_db_path.with_suffix(".sqlite.part").exists()
    # never over one already there (a newer download, say)
    settings.cards_db_path.write_bytes(b"mine")
    assert not launcher.seed_card_database(settings) and settings.cards_db_path.read_bytes() == b"mine"


def test_no_seed_no_copy(tmp_path):
    settings = load_settings({"FYODOR_DATA_DIR": str(tmp_path / "d")})
    assert not launcher.seed_card_database(settings) and not settings.cards_db_path.exists()


def test_the_table_opens_in_fyodor_s_own_window_when_it_has_one(tmp_path, install_dir, monkeypatch):
    opened: list = []
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(("system", url)))
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda argv, **kw: opened.append(("own", argv)))
    settings = load_settings({"FYODOR_DATA_DIR": str(tmp_path / "d")})
    launcher.open_table("http://127.0.0.1:8000", settings)
    assert opened == [("system", "http://127.0.0.1:8000")]  # no window of its own: the default browser
    opened.clear()
    monkeypatch.setattr(launcher, "installed_browsers", lambda: [])
    (install_dir / "browser").mkdir()
    (install_dir / "browser" / "chrome.exe").write_bytes(b"")
    launcher.open_table("http://127.0.0.1:8000", settings)
    kind, argv = opened[0]
    assert kind == "own" and argv[0].endswith("chrome.exe") and "--app=http://127.0.0.1:8000" in argv
    assert f"--user-data-dir={settings.data_dir / 'window'}" in argv


def test_starting_fyodor_again_opens_the_table_instead_of_failing_on_the_port(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FYODOR_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setattr(launcher, "_running_fyodor", lambda url: True)
    opened: list[str] = []
    monkeypatch.setattr(launcher, "open_table", lambda url, settings: opened.append(url))
    assert launcher.main(["--local"]) == 0
    assert opened == ["http://127.0.0.1:8000"] and "already running" in capsys.readouterr().out


def test_windows_8_1_gets_the_chromium_that_still_runs_there(install_dir, monkeypatch):
    for d in ("browser", "browser-legacy"):
        (install_dir / d).mkdir()
        (install_dir / d / "chrome.exe").write_bytes(b"")
    monkeypatch.setattr(launcher, "_windows_major", lambda: 10)  # Windows 10 and 11
    assert launcher.bundled_browser() == install_dir / "browser" / "chrome.exe"
    monkeypatch.setattr(launcher, "_windows_major", lambda: 6)  # Windows 8.1
    assert launcher.bundled_browser() == install_dir / "browser-legacy" / "chrome.exe"


def test_restart_from_settings_starts_the_server_again_in_the_same_program(tmp_path, monkeypatch):
    """After a restore, Settings → Restart Fyodor: the server stops and starts again in place (no window to find and
    close), which is when the staged restore is applied."""
    import json
    import threading
    import time
    import urllib.request

    import app.main

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    settings = load_settings({"FYODOR_DATA_DIR": str(tmp_path / "d"), "FYODOR_PORT": str(port), "FYODOR_AUTO_BACKUP_MINUTES": "0"})
    made: list = []
    real = app.main.create_app

    def create_app(st):
        made.append(real(st))
        return made[-1]

    monkeypatch.setattr(app.main, "create_app", create_app)
    t = threading.Thread(target=launcher.serve, args=(settings,), daemon=True)
    t.start()
    url = f"http://127.0.0.1:{port}"

    def up(n: int) -> bool:
        for _ in range(150):
            if len(made) >= n:
                try:
                    with urllib.request.urlopen(f"{url}/api/health", timeout=1):
                        return True
                except OSError:
                    pass
            time.sleep(0.1)
        return False

    assert up(1)
    req = urllib.request.Request(f"{url}/api/restart", data=b"{}", method="POST", headers={"Content-Type": "application/json", "Cookie": f"fyodor_host={made[0].state.services.host_secret.value}"})  # (as the host)
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 202 and json.loads(r.read())["restarting"] is True
    assert up(2)  # a new server, from a new app, on the same port
    made[-1].state.request_restart.__defaults__[0].should_exit = True  # stop for good (no restart)
    t.join(10)
    assert not t.is_alive() and len(made) == 2


def test_an_up_to_date_chrome_or_edge_on_the_computer_comes_first(install_dir, monkeypatch, tmp_path):
    (install_dir / "browser").mkdir()
    (install_dir / "browser" / "chrome.exe").write_bytes(b"")
    chrome = tmp_path / "Chrome" / "Application"
    (chrome / "131.0.6778.86").mkdir(parents=True)
    (chrome / "chrome.exe").write_bytes(b"")
    assert launcher._browser_version(chrome / "chrome.exe") == 131
    monkeypatch.setattr(launcher, "installed_browsers", lambda: [("Chrome", chrome / "chrome.exe")])
    assert [n for n, _ in launcher.windows_to_try()] == ["Chrome", "Fyodor's own window"]


def test_a_slow_window_is_left_open_and_the_console_says_what_to_do(tmp_path, install_dir, monkeypatch, capsys):
    (install_dir / "browser").mkdir()
    (install_dir / "browser" / "chrome.exe").write_bytes(b"")
    monkeypatch.setattr(launcher, "installed_browsers", lambda: [])
    launched: list = []
    monkeypatch.setattr(launcher, "_launch", lambda name, exe, url, settings: launched.append(name) or object())
    monkeypatch.setattr(launcher, "WINDOW_WAIT", 0.05)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: launched.append("system"))
    launcher.PAGE_SEEN.clear()
    launcher.open_table("http://127.0.0.1:8000", load_settings({"FYODOR_DATA_DIR": str(tmp_path / "d")}), watch=True)
    assert launched == ["Fyodor's own window"]  # not replaced by the default browser (an offline PC's old Edge)
    assert "hasn't appeared" in capsys.readouterr().out


def test_fyodors_own_window_runs_without_the_network_service_sandbox(tmp_path, monkeypatch):
    # a portable Fyodor unpacked on the Desktop: its Chromium's sandboxed network service can't read its own folder
    started: list[list[str]] = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda args, **kw: started.append(args) or object())
    settings = load_settings({"FYODOR_DATA_DIR": str(tmp_path / "d")})
    launcher._launch("Fyodor's own window", tmp_path / "chrome.exe", "http://127.0.0.1:8000", settings)
    launcher._launch("Chrome", tmp_path / "chrome.exe", "http://127.0.0.1:8000", settings)
    own, chrome = ([a for a in args if a.startswith("--disable-features=")] for args in started)
    assert own == ["--disable-features=Translate,MediaRouter,NetworkServiceSandbox"]
    assert chrome == ["--disable-features=Translate,MediaRouter"]  # an installed browser keeps its sandbox


def test_reopening_a_running_table_carries_the_host_secret_from_its_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FYODOR_DATA_DIR", str(tmp_path / "d"))
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "host.secret").write_text("s3cret-value")
    monkeypatch.setattr(launcher, "_running_fyodor", lambda url: True)
    opened: list[str] = []
    monkeypatch.setattr(launcher, "open_table", lambda url, settings: opened.append(url))
    assert launcher.main(["--local"]) == 0
    assert opened == ["http://127.0.0.1:8000/#host=s3cret-value"]
    assert "s3cret-value" not in capsys.readouterr().out  # never printed


def test_every_start_opens_the_window_with_that_starts_secret(tmp_path, monkeypatch):
    """A first start and the in-app restart each open a window holding the secret of the server just made."""
    import threading
    import time

    import app.main

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    settings = load_settings({"FYODOR_DATA_DIR": str(tmp_path / "d"), "FYODOR_PORT": str(port), "FYODOR_AUTO_BACKUP_MINUTES": "0"})
    made: list = []
    real = app.main.create_app
    monkeypatch.setattr(app.main, "create_app", lambda st: made.append(real(st)) or made[-1])
    opened: list[str] = []
    monkeypatch.setattr(launcher, "open_table", lambda url, settings, watch=False: opened.append(url))
    threading.Thread(target=launcher.serve, args=(settings, True), daemon=True).start()

    def wait(cond) -> None:
        for _ in range(150):
            if cond():
                return
            time.sleep(0.1)
        raise AssertionError("timed out")

    wait(lambda: len(opened) == 1)
    made[0].state.request_restart()
    wait(lambda: len(opened) == 2)
    secrets_made = [m.state.services.host_secret.value for m in made]
    assert opened == [f"http://127.0.0.1:{port}/#host={v}" for v in secrets_made] and secrets_made[0] != secrets_made[1]


def test_a_slow_window_note_never_prints_the_host_secret(tmp_path, install_dir, monkeypatch, capsys):
    (install_dir / "browser").mkdir()
    (install_dir / "browser" / "chrome.exe").write_bytes(b"")
    monkeypatch.setattr(launcher, "installed_browsers", lambda: [])
    monkeypatch.setattr(launcher, "_launch", lambda name, exe, url, settings: object())
    monkeypatch.setattr(launcher, "WINDOW_WAIT", 0.05)
    launcher.PAGE_SEEN.clear()
    url = launcher.host_url("http://127.0.0.1:8000", "s3cret-value")
    launcher.open_table(url, load_settings({"FYODOR_DATA_DIR": str(tmp_path / "d")}), watch=True)
    out = capsys.readouterr().out
    assert "hasn't appeared" in out and "http://127.0.0.1:8000" in out and "s3cret-value" not in out


def test_the_server_is_built_with_a_frame_limit_just_above_the_message_limit(tmp_path):
    """uvicorn would buffer a 16 MiB frame before the app's 64 KiB check ran; the transport limit is the message limit plus a margin."""
    from app.api.games import MAX_WS_MESSAGE

    options = launcher.server_options(load_settings({"FYODOR_DATA_DIR": str(tmp_path), "FYODOR_PORT": "8765"}))
    assert MAX_WS_MESSAGE < options["ws_max_size"] <= MAX_WS_MESSAGE + 4096
    assert (options["port"], options["log_level"]) == (8765, "info")
