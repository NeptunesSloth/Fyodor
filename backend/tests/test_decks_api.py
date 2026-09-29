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
    deck = client.post("/api/decks", json={"text": "1 Sol Ring", "name": "T", "format": "constructed"}).json()
    res = client.post(f"/api/decks/{deck['id']}/import", json={"text": "4 Lightning Bolt", "mode": "append"}).json()
    assert [(e["name"], e["quantity"]) for e in res["entries"]] == [("Sol Ring", 1), ("Lightning Bolt", 4)]
    assert any("minimum 60" in w["message"] for w in res["warnings"])


def test_validation_rejects_bad_input(client):
    assert client.post("/api/decks", json={"text": "x" * 250_000}).status_code == 422
    assert client.put("/api/decks/nope", json={"name": "", "entries": []}).status_code == 422
    bad_entry = {"name": "X", "entries": [{"quantity": 0, "name": "Sol Ring"}]}
    assert client.put("/api/decks/nope", json=bad_entry).status_code == 422
    assert client.put("/api/decks/nope", json={"name": "X", "entries": []}).status_code == 404


def test_names_are_sanitized(client):
    deck = client.post("/api/decks", json={"text": "", "name": "Evil‮\x00  deck   name"}).json()
    assert deck["name"] == "Evil deck name"
