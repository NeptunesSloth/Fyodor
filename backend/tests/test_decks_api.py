from __future__ import annotations

KRENKO_LIST = """Commander
1 Krenko, Mob Boss

Deck
1 Sol Ring (CMM) 410
1 Sol Ring (C21)
1 Arcane Signet
1 Command Tower
1 Counterspell
1 Solring
30 Mountain
"""


def test_parse_preview(client):
    res = client.post("/api/decks/parse", json={"text": KRENKO_LIST})
    assert res.status_code == 200
    body = res.json()
    assert body["unresolved"][0]["name"] == "Solring"
    assert body["unresolved"][0]["suggestions"][0] == "Sol Ring"
    sol = [e for e in body["entries"] if e["name"] == "Sol Ring"]
    assert {e["set_code"] for e in sol} == {"cmm", "c21"}  # different printings stay separate


def test_create_get_update_duplicate_delete(client):
    res = client.post("/api/decks", json={"text": KRENKO_LIST, "name": "Goblins"})
    assert res.status_code == 201
    deck = res.json()
    assert deck["name"] == "Goblins"
    assert deck["summary"]["commanders"] == ["Krenko, Mob Boss"]
    assert deck["summary"]["color_identity"] == ["R"]
    assert deck["import_report"]["unresolved"][0]["name"] == "Solring"
    messages = [w["message"] for w in deck["warnings"]]
    assert any("Solring" in m for m in messages)
    assert any("Counterspell is outside" in m for m in messages)
    assert any("2 copies of Sol Ring" in m for m in messages)
    assert any("Commander decks have 100" in m for m in messages)

    listing = client.get("/api/decks").json()
    assert [d["name"] for d in listing] == ["Goblins"]
    assert listing[0]["cover_id"]

    # edit: fix the typo by name only, swap commander
    entries = [e for e in deck["entries"] if e["name"] != "Solring"]
    entries.append({"section": "main", "quantity": 1, "name": "Lightning Bolt"})
    res = client.put(f"/api/decks/{deck['id']}", json={"name": "Goblins v2", "format": "commander", "entries": entries})
    assert res.status_code == 200
    updated = res.json()
    bolt = next(e for e in updated["entries"] if e["name"] == "Lightning Bolt")
    assert bolt["printing_id"]
    assert not any("Solring" in w["message"] for w in updated["warnings"])

    dup = client.post(f"/api/decks/{deck['id']}/duplicate").json()
    assert dup["name"] == "Goblins v2 (copy)"
    assert len(dup["entries"]) == len(updated["entries"])

    export = client.get(f"/api/decks/{deck['id']}/export", params={"format": "plain"}).text
    assert export.startswith("Commander\n1 Krenko, Mob Boss")
    archidekt_text = client.get(f"/api/decks/{deck['id']}/export").text
    assert archidekt_text.startswith("1x Krenko, Mob Boss (ddn) 13 [Commander{top}]")

    assert client.delete(f"/api/decks/{deck['id']}").status_code == 204
    assert client.get(f"/api/decks/{deck['id']}").status_code == 404
    assert len(client.get("/api/decks").json()) == 1


def test_default_name_from_commander(client):
    deck = client.post("/api/decks", json={"text": KRENKO_LIST}).json()
    assert deck["name"] == "Krenko, Mob Boss"


def test_import_append(client):
    deck = client.post("/api/decks", json={"text": "1 Sol Ring", "name": "T"}).json()
    res = client.post(f"/api/decks/{deck['id']}/import", json={"text": "4 Lightning Bolt", "mode": "append"}).json()
    assert [(e["name"], e["quantity"]) for e in res["entries"]] == [("Sol Ring", 1), ("Lightning Bolt", 4)]
    assert any("Lightning Bolt" in w["message"] for w in res["warnings"])  # four copies break Commander's singleton rule


def test_constructed_and_sandbox_decks_open_as_commander_decks(client):
    """Fyodor is Commander-only: a deck sent with an old format (an export, an older client) is kept, as a Commander deck."""
    for fmt in ("constructed", "sandbox"):
        deck = client.post("/api/decks", json={"text": "1 Sol Ring", "name": fmt, "format": fmt}).json()
        assert deck["format"] == "commander"
    assert client.post("/api/decks", json={"text": "1 Sol Ring", "format": "modern"}).status_code == 422


def test_validation_rejects_bad_input(client):
    assert client.post("/api/decks", json={"text": "x" * 250_000}).status_code == 422
    assert client.put("/api/decks/nope", json={"name": "", "entries": []}).status_code == 422
    bad_entry = {"name": "X", "entries": [{"quantity": 0, "name": "Sol Ring"}]}
    assert client.put("/api/decks/nope", json=bad_entry).status_code == 422
    assert client.put("/api/decks/nope", json={"name": "X", "entries": []}).status_code == 404


def test_names_are_sanitized(client):
    deck = client.post("/api/decks", json={"text": "", "name": "Evil‮\x00  deck   name"}).json()
    assert deck["name"] == "Evil deck name"


def test_stored_constructed_decks_become_commander_decks(tmp_path):
    """App DB migration 8: decks saved as Constructed or Sandbox before the formats were removed keep their cards."""
    from app.storage.app_db import MIGRATIONS, open_app_db
    from app.storage.db import connect, migrate

    path = tmp_path / "app.sqlite"
    conn = connect(path)
    migrate(conn, MIGRATIONS[:7], name="app")
    conn.execute("INSERT INTO decks (id, name, format, notes, created_at, updated_at) VALUES ('d1', 'Burn', 'constructed', '', 'x', 'x')")
    conn.execute("INSERT INTO decks (id, name, format, notes, created_at, updated_at) VALUES ('d2', 'Pile', 'sandbox', '', 'x', 'x')")
    conn.commit()
    conn.close()
    conn = open_app_db(path)
    assert [r[0] for r in conn.execute("SELECT format FROM decks ORDER BY id")] == ["commander", "commander"]


def test_deck_folders(client):
    """-- deck folders -- a deck sits in at most one folder; saving the list never moves it; a folder renames or empties."""
    a = client.post("/api/decks", json={"text": "Commander\n1 Krenko, Mob Boss\nDeck\n1 Mountain", "name": "A"}).json()["id"]
    b = client.post("/api/decks", json={"text": "Commander\n1 Krenko, Mob Boss\nDeck\n1 Mountain", "name": "B"}).json()["id"]
    folders = lambda: {d["id"]: d["folder"] for d in client.get("/api/decks").json()}  # noqa: E731
    assert folders() == {a: "", b: ""}
    assert client.put(f"/api/decks/{a}/folder", json={"folder": "  Pod   decks "}).json()["folder"] == "Pod decks"
    assert client.put(f"/api/decks/{b}/folder", json={"folder": "Pod decks"}).status_code == 200
    assert client.put("/api/decks/nope/folder", json={"folder": "X"}).status_code == 404
    deck = client.get(f"/api/decks/{a}").json()
    assert client.put(f"/api/decks/{a}", json={k: deck[k] for k in ("name", "format", "notes", "entries", "categories")}).status_code == 200
    assert folders() == {a: "Pod decks", b: "Pod decks"}
    copy = client.post(f"/api/decks/{a}/duplicate").json()["id"]
    assert folders()[copy] == "Pod decks"
    assert client.post("/api/deck-folders/rename", json={"old": "Pod decks", "new": "Retired"}).json()["moved"] == 3
    client.put(f"/api/decks/{b}/folder", json={"folder": ""})
    assert folders() == {a: "Retired", b: "", copy: "Retired"}
    client.post("/api/deck-folders/rename", json={"old": "Retired", "new": ""})
    assert set(folders().values()) == {""}


def test_precons_are_bundled_and_added_once_into_their_folder(client):
    precons = client.get("/api/decks/precons").json()
    assert len(precons) >= 150 and all(p["commanders"] for p in precons)
    first = precons[0]
    assert not first["added"]
    assert client.post("/api/decks/precons", json={"ids": [first["id"]]}).json()["added"] == 1
    assert client.post("/api/decks/precons", json={"ids": [first["id"]]}).json()["added"] == 0  # already there
    decks = client.get("/api/decks").json()
    assert [(d["name"], d["folder"]) for d in decks] == [(first["name"], "Precons")]
    assert next(p for p in client.get("/api/decks/precons").json() if p["id"] == first["id"])["added"]
