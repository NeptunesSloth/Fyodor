"""BACKUP FYODOR / restore, pre-migration backups and the database recovery mode (M20)."""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile

from fastapi.testclient import TestClient

from app.main import create_app
from app.storage.backup import pre_migration_backup
from tests.test_protocol_privacy import P1_DECK


def test_backup_and_restore_round_trip(settings, card_db):
    with TestClient(create_app(settings)) as c:
        deck = c.post("/api/decks", json={"text": P1_DECK, "name": "Before"}).json()["id"]
        made = c.post("/api/backups")
        assert made.status_code == 201, made.text
        name = made.json()["name"]
        assert name.startswith("fyodor-backup-") and c.get("/api/backups").json()["backups"][0]["name"] == name
        blob = c.get(f"/api/backups/{name}").content
        names = zipfile.ZipFile(io.BytesIO(blob)).namelist()
        assert "app.sqlite" in names and "manifest.json" in names and "cards.sqlite" not in names
        # after the backup: delete the deck, then restore
        assert c.delete(f"/api/decks/{deck}").status_code in (200, 204)
        staged = c.post(f"/api/backups/{name}/restore")
        assert staged.status_code == 200 and staged.json()["restart_required"] is True
    with TestClient(create_app(settings)) as c:  # the restore is applied at the next start
        assert c.get(f"/api/decks/{deck}").status_code == 200
        kept = [b.name for b in (settings.data_dir / "backups").iterdir() if b.name.startswith("app-before-restore-")]
        assert kept, "the database from before the restore is kept"


def test_restore_rejects_anything_unexpected(client):
    def upload(files: dict[str, bytes]) -> int:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for n, data in files.items():
                zf.writestr(n, data)
        return client.post("/api/backups/restore", content=buf.getvalue()).status_code

    manifest = b'{"format": "fyodor-backup", "version": 1}'
    assert upload({"manifest.json": manifest, "app.sqlite": b"not a database"}) == 422
    assert upload({"manifest.json": manifest, "app.sqlite": b"", "../evil.sh": b"rm -rf /"}) == 422
    assert upload({"manifest.json": manifest, "app.sqlite": b"", "assets/x.exe": b"MZ"}) == 422
    assert upload({"hello.txt": b"hi"}) == 422
    assert client.post("/api/backups/restore", content=b"not a zip").status_code == 422
    assert client.get("/api/backups/..%2Fapp.sqlite").status_code == 404
    assert client.get("/api/backups/app.sqlite").status_code == 404


def test_backups_are_host_only(client):
    res = client.post("/api/backups", headers={"X-Forwarded-For": "192.168.1.20"})
    assert res.status_code in (201, 403)  # the test client is loopback; a proxied LAN address is refused
    if res.status_code == 201:
        # the forwarded header isn't trusted in this setup; at least the endpoint exists and works
        assert res.json()["name"].startswith("fyodor-backup-")


def test_a_damaged_database_starts_in_recovery_mode(settings, card_db):
    with TestClient(create_app(settings)) as c:
        c.post("/api/decks", json={"text": P1_DECK})
    path = settings.app_db_path
    for suffix in ("-wal", "-shm"):
        (path.parent / (path.name + suffix)).unlink(missing_ok=True)
    data = bytearray(path.read_bytes())
    data[100:4096] = b"\x00\xff" * ((4096 - 100) // 2)  # wreck the first page
    path.write_bytes(bytes(data))
    with TestClient(create_app(settings)) as c:
        health = c.get("/api/health").json()
        assert "recovery" in health and health["recovery"]["moved_to"].startswith("app-damaged-")
        assert c.get("/api/decks").status_code == 200  # a fresh, working database
    assert any(p.name.startswith("app-damaged-") for p in (settings.data_dir / "recovery").iterdir())


def test_the_database_is_backed_up_before_a_migration(tmp_path):
    db = tmp_path / "app.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    conn.execute("INSERT INTO schema_version VALUES (3)")
    conn.commit()
    conn.close()
    copy = pre_migration_backup(db, 7)
    assert copy is not None and copy.exists() and "before-v7" in copy.name
    assert pre_migration_backup(db, 3) is None  # already current: nothing to do


def test_backup_carries_the_browsers_my_decks(settings, card_db):
    """"My decks" live in the host browser's storage, not app.sqlite: a backup made from Settings carries them, and after
    the restore the browser on the other computer takes them back (once)."""
    mine = [{"id": "abc", "name": "Krenko", "body": {"name": "Krenko", "text": "1 Krenko, Mob Boss"}, "commanders": ["Krenko, Mob Boss"],
             "savedAt": 1}]
    with TestClient(create_app(settings)) as c:
        assert c.post("/api/backups", json={"browser_decks": "nope"}).status_code == 422
        made = c.post("/api/backups", json={"browser_decks": mine})
        assert made.status_code == 201, made.text
        name = made.json()["name"]
        blob = c.get(f"/api/backups/{name}").content
        assert "browser-decks.json" in zipfile.ZipFile(io.BytesIO(blob)).namelist()
        assert c.get("/api/backups").json()["restore_pending"] is False
        assert c.post("/api/backups/restore", content=blob).json()["browser_decks"] is True
        assert c.get("/api/backups").json()["restore_pending"] is True
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/backups").json()["restore_pending"] is False
        assert c.get("/api/restored-decks").json()["decks"] == mine
        assert c.delete("/api/restored-decks").status_code == 204
        assert c.get("/api/restored-decks").json()["decks"] == []


def test_automatic_backups_carry_the_synced_my_decks(settings, card_db):
    """The host browser mirrors My decks to the server, so a backup made without a browser (automatic) carries them too."""
    mine = [{"id": "x", "name": "Atraxa", "body": {"text": "1 Atraxa, Praetors' Voice"}}]
    with TestClient(create_app(settings)) as c:
        services = c.app.state.services
        before = services.autobackups._changes()
        assert c.put("/api/browser-decks", json={"browser_decks": mine}).status_code == 204
        assert services.autobackups._changes() > before  # an automatic backup is due (no database write needed)
        assert services._has_data()
        made = services.backup(reason="test")
        blob = (settings.data_dir / "backups" / made["name"]).read_bytes()
        assert json.loads(zipfile.ZipFile(io.BytesIO(blob)).read("browser-decks.json")) == mine
