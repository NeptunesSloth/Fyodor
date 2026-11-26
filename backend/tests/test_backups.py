"""BACKUP FYODOR / restore, pre-migration backups and the database recovery mode (M20)."""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile

from fastapi.testclient import TestClient

from app.main import create_app
from app.storage.backup import pre_migration_backup
from tests.conftest import claim_host, guest
from tests.test_protocol_privacy import P1_DECK


def test_backup_and_restore_round_trip(settings, card_db):
    with TestClient(create_app(settings)) as c:
        claim_host(c)
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
        claim_host(c)
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
    res = client.post("/api/backups", headers=guest())
    assert res.status_code == 403  # without the host cookie, even from loopback, a guest is refused


def test_a_damaged_database_starts_in_recovery_mode(settings, card_db):
    with TestClient(create_app(settings)) as c:
        claim_host(c)
        c.post("/api/decks", json={"text": P1_DECK})
    path = settings.app_db_path
    for suffix in ("-wal", "-shm"):
        (path.parent / (path.name + suffix)).unlink(missing_ok=True)
    data = bytearray(path.read_bytes())
    data[100:4096] = b"\x00\xff" * ((4096 - 100) // 2)  # wreck the first page
    path.write_bytes(bytes(data))
    with TestClient(create_app(settings)) as c:
        claim_host(c)
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
        claim_host(c)
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
        claim_host(c)
        assert c.get("/api/backups").json()["restore_pending"] is False
        assert c.get("/api/restored-decks").json()["decks"] == mine
        assert c.delete("/api/restored-decks").status_code == 204
        assert c.get("/api/restored-decks").json()["decks"] == []


def test_automatic_backups_carry_the_synced_my_decks(settings, card_db):
    """The host browser mirrors My decks to the server, so a backup made without a browser (automatic) carries them too."""
    mine = [{"id": "x", "name": "Atraxa", "body": {"text": "1 Atraxa, Praetors' Voice"}}]
    with TestClient(create_app(settings)) as c:
        claim_host(c)
        services = c.app.state.services
        before = services.autobackups._changes()
        assert c.put("/api/browser-decks", json={"browser_decks": mine}).status_code == 204
        assert services.autobackups._changes() > before  # an automatic backup is due (no database write needed)
        assert services._has_data()
        made = services.backup(reason="test")
        blob = (settings.data_dir / "backups" / made["name"]).read_bytes()
        assert json.loads(zipfile.ZipFile(io.BytesIO(blob)).read("browser-decks.json")) == mine


# -- card art in hand-made backups (an offline computer restoring a backup gets the decks' art too) ---------------------

JPEG = b"\xff\xd8\xff\xe0" + b"art" * 100
KRENKO_DECK = "Commander\n1x Krenko, Mob Boss (ddn) 13\nDeck\n1x Lightning Bolt (clb) 187\n"


def _plant(images, card_id: str, body: bytes = JPEG, *, size: str = "normal", face: int = 0, is_token: bool = False):
    path = images.path_for(card_id, face=face, size=size, is_token=is_token)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def _other_settings(tmp_path):
    from app.cards.importer import build_database
    from app.config import load_settings
    from tests.fixtures.cards import fixture_cards

    other = load_settings({"FYODOR_DATA_DIR": str(tmp_path / "offline"), "FYODOR_FRONTEND_DIST": str(tmp_path / "nodist")})
    other.ensure_dirs()
    build_database(fixture_cards(), other.cards_db_path, meta={"bulk_type": "test"})
    return other


def test_hand_made_backups_carry_the_decks_card_art(settings, card_db, tmp_path):
    from app.cards.images import CARD_BACK_ID
    from tests.fixtures.cards import GOBLIN, cid

    krenko, bolt, elves = cid("Krenko, Mob Boss|ddn|13"), cid("Lightning Bolt|clb|187"), cid("Llanowar Elves|dom|168")
    with TestClient(create_app(settings)) as c:
        claim_host(c)
        services = c.app.state.services
        deck = c.post("/api/decks", json={"text": KRENKO_DECK, "name": "Goblins"}).json()
        assert {e["printing_id"] for e in deck["entries"]} >= {krenko, bolt}
        images = services.images
        _plant(images, krenko)
        _plant(images, krenko, size="large")
        _plant(images, bolt)
        _plant(images, GOBLIN["id"], is_token=True)  # the token Krenko makes
        _plant(images, elves)  # cached, but in no deck: stays out
        back = images.card_back_path()
        back.parent.mkdir(parents=True, exist_ok=True)
        back.write_bytes(JPEG)
        made = c.post("/api/backups").json()
        assert made["art"] == 5 and made["art_left_out"] == 0
        zf = zipfile.ZipFile(settings.data_dir / "backups" / made["name"])
        names = set(zf.namelist())
        assert {f"images/cards/{krenko[:2]}/{krenko}-0-normal.jpg", f"images/cards/{krenko[:2]}/{krenko}-0-large.jpg",
                f"images/cards/{bolt[:2]}/{bolt}-0-normal.jpg", f"images/tokens/{GOBLIN['id'][:2]}/{GOBLIN['id']}-0-normal.jpg",
                f"images/backs/{CARD_BACK_ID}-normal.jpg"} <= names
        assert not any(elves in n for n in names)
        assert json.loads(zf.read("manifest.json"))["art"] == 5
        zf.close()
        # automatic backups never carry art (a dozen of them are kept)
        auto = services.backup(reason="test")
        with zipfile.ZipFile(settings.data_dir / "backups" / auto["name"]) as az:
            assert not any(n.startswith("images/") for n in az.namelist())
        blob = (settings.data_dir / "backups" / made["name"]).read_bytes()

    # restore onto an offline computer that has no art for Krenko yet, but newer art for Lightning Bolt
    other = _other_settings(tmp_path)
    with TestClient(create_app(other)) as c:
        claim_host(c)
        newer = _plant(c.app.state.services.images, bolt, JPEG + b"newer")
        staged = c.post("/api/backups/restore", content=blob)
        assert staged.status_code == 200 and staged.json()["art"] == 5
    with TestClient(create_app(other)) as c:
        claim_host(c)
        images = c.app.state.services.images
        assert c.get(f"/api/decks/{deck['id']}").status_code == 200
        assert images.find(krenko) == images.path_for(krenko) and images.find(krenko).read_bytes() == JPEG
        assert images.find(krenko, size="large") is not None
        assert images.find(GOBLIN["id"]) is not None and images.card_back() is not None
        assert newer.read_bytes() == JPEG + b"newer"  # art already here is never replaced
        assert images.find(elves) is None
        assert not (other.data_dir / "restore-pending").exists()


def test_restore_refuses_odd_art_names_and_skips_what_isnt_art(client, settings):
    made = client.post("/api/backups").json()
    with zipfile.ZipFile(settings.data_dir / "backups" / made["name"]) as zf:
        base = {n: zf.read(n) for n in zf.namelist()}
    good = "0aeebaf5-8c7d-4636-9e82-8c27447861f7"

    def upload(extra: dict[str, bytes]):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for n, data in {**base, **extra}.items():
                zf.writestr(n, data)
        return client.post("/api/backups/restore", content=buf.getvalue())

    for name in (f"images/cards/0a/../../{good}-0-normal.jpg", "images/cards/ab/not-a-uuid-0-normal.jpg",
                 f"images/cards/zz/{good}-0-normal.jpg", f"images/cards/0a/{good}-0-huge.jpg",
                 f"images/cards/0a/{good}-7-normal.jpg", f"images/cards/0a/{good.upper()}-0-normal.jpg",
                 f"images/elsewhere/0a/{good}-0-normal.jpg", "images/symbols/evil.svg", "images/run.exe",
                 f"/images/cards/0a/{good}-0-normal.jpg"):
        assert upload({name: JPEG}).status_code == 422, name
    # the right name, the wrong content: left out, the rest still restores
    res = upload({f"images/cards/0a/{good}-0-normal.jpg": b"MZ not a jpeg",
                  f"images/tokens/0a/{good}-0-small.jpg": b"\xff\xd8\xff" + b"x" * 3_000_000,
                  "images/symbols/W.svg": b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                  "images/symbols/symbology.json": b"[1, 2]"})
    assert res.status_code == 200 and res.json()["art"] == 0
    assert not (settings.data_dir / "restore-pending" / "images").exists() or not any(
        p.is_file() for p in (settings.data_dir / "restore-pending" / "images").rglob("*"))
