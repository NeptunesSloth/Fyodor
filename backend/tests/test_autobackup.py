"""Automatic backups: when they run, what they keep, the second copy, and the API that shows them."""

from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.storage.backup import KEEP_AUTO_DAYS, KEEP_AUTO_RECENT, KEEP_BACKUPS, prune
from tests.conftest import claim_host
from tests.test_pod_stats import new_game, record

DAY = 86400.0


def _b(name: str, mtime: float, auto: bool) -> dict:
    return {"name": name, "mtime": mtime, "auto": auto}


def test_prune_keeps_recent_autos_one_per_day_and_twelve_by_hand():
    now = time.mktime((2026, 10, 31, 22, 0, 0, 0, 0, -1))
    # three automatic backups a day for ten days (newest first), and 14 made by hand
    autos = [_b(f"a{d}-{h}", now - d * DAY - h * 3600, True) for d in range(10) for h in range(3)]
    manual = [_b(f"m{i}", now - i * 600, False) for i in range(14)]
    backups = sorted(autos + manual, key=lambda b: -b["mtime"])
    drop = set(prune(backups, now=now))
    kept_auto = [b for b in autos if b["name"] not in drop]
    assert [b["name"] for b in manual if b["name"] in drop] == ["m12", "m13"] and KEEP_BACKUPS == 12
    assert [b["name"] for b in kept_auto[:KEEP_AUTO_RECENT]] == [b["name"] for b in autos[:KEEP_AUTO_RECENT]]
    days = {time.strftime("%Y-%m-%d", time.localtime(b["mtime"])) for b in kept_auto}
    assert len(days) == KEEP_AUTO_DAYS  # one per day for the past week, nothing older
    assert all(now - b["mtime"] < KEEP_AUTO_DAYS * DAY for b in kept_auto)
    assert len(kept_auto) == KEEP_AUTO_RECENT + (KEEP_AUTO_DAYS - 3)  # the newest eight span three days


def test_automatic_backups_run_only_when_something_changed(client):
    auto = client.app.state.services.autobackups
    assert auto.status()["enabled"] and auto.status()["interval_minutes"] == 30
    auto.stop()  # the background thread would race these direct calls
    assert auto.startup() is None  # nothing worth keeping yet
    gid = new_game(client, names=("Jonathan", "Mike"))
    first = auto.tick()
    assert first is not None and first["auto"] and first["reason"] == "while playing"
    assert first["name"].startswith("fyodor-autobackup-")
    assert auto.tick() is None  # nothing changed since
    assert auto.startup() is None  # a backup from today already exists

    # a recorded game asks for one at once (the background thread runs it; here we run it directly)
    assert record(client, gid, "single", ["p1"]).status_code in (200, 201)
    after = auto.run_pending()
    assert after is not None and after["reason"] == "after a recorded game"
    listed = client.get("/api/backups").json()
    assert listed["auto"]["last"]["name"] == after["name"] and listed["auto"]["last_error"] is None
    assert [b["reason"] for b in listed["backups"][:2]] == ["after a recorded game", "while playing"]
    # an automatic backup restores like any other
    assert client.post(f"/api/backups/{after['name']}/restore").json()["restart_required"] is True


def test_startup_backup_when_the_newest_is_old(client):
    services = client.app.state.services
    services.autobackups.stop()
    new_game(client, names=("Jonathan", "Mike"))
    made = services.backup()  # by hand, then pretend it's from two days ago
    old = time.time() - 2 * DAY
    os.utime(services.settings.data_dir / "backups" / made["name"], (old, old))
    first = services.autobackups.startup()
    assert first is not None and first["reason"] == "start-up"


def test_backups_are_mirrored_to_a_second_folder(tmp_path: Path, card_db):
    mirror = tmp_path / "usb" / "Fyodor backups"
    settings = load_settings({"FYODOR_DATA_DIR": str(card_db.parent), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist"),
                              "FYODOR_BACKUP_COPY_DIR": str(mirror)})
    with TestClient(create_app(settings)) as c:
        claim_host(c)
        made = c.post("/api/backups").json()
        assert made["copied_to"] == str(mirror) and (mirror / made["name"]).is_file()
        assert c.get("/api/backups").json()["auto"]["copy_dir"] == str(mirror)
        (mirror / "fyodor-backup-20200101-000000.zip").write_bytes(b"gone from the host")
        c.post("/api/backups")
        assert not (mirror / "fyodor-backup-20200101-000000.zip").exists()  # the mirror follows the rotation


def test_a_missing_second_folder_does_not_lose_the_backup(tmp_path: Path, card_db):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a file where the folder should be")
    settings = load_settings({"FYODOR_DATA_DIR": str(card_db.parent), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist"),
                              "FYODOR_BACKUP_COPY_DIR": str(blocker)})
    with TestClient(create_app(settings)) as c:
        claim_host(c)
        services = c.app.state.services
        services.autobackups.stop()
        new_game(c, names=("Jonathan", "Mike"))
        made = services.autobackups.tick()
        assert made is not None and (settings.data_dir / "backups" / made["name"]).is_file()
        assert "Couldn't copy" in services.autobackups.status()["last_error"]


def test_automatic_backups_can_be_turned_off(tmp_path: Path, card_db):
    settings = load_settings({"FYODOR_DATA_DIR": str(card_db.parent), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist"),
                              "FYODOR_AUTO_BACKUP_MINUTES": "0"})
    with TestClient(create_app(settings)) as c:
        claim_host(c)
        auto = c.app.state.services.autobackups
        assert auto.status()["enabled"] is False and auto._thread is None
        auto.soon("after a recorded game")
        assert auto.run_pending() is None


def test_the_background_thread_backs_up_after_a_recorded_game(client):
    auto = client.app.state.services.autobackups
    gid = new_game(client, names=("Jonathan", "Mike"))
    assert record(client, gid, "single", ["p2"]).status_code in (200, 201)
    deadline = time.time() + 10
    while (auto.last or {}).get("reason") != "after a recorded game" and time.time() < deadline:
        time.sleep(0.05)
    assert auto.last and auto.last["reason"] == "after a recorded game"
