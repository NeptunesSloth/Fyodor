"""An imported library survives a host restart with network access disabled."""

from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app


def test_imported_decks_survive_restart_without_network(settings, card_db):
    with TestClient(create_app(settings)) as client:
        saved = []
        for name, text in [("Goblins", "Commander\n1 Krenko, Mob Boss\nDeck\n12 Mountain\n1 Sol Ring"),
                           ("Spells", "Commander\n1 Atraxa, Praetors' Voice\nDeck\n12 Island\n1 Counterspell")]:
            response = client.post("/api/decks", json={"name": name, "text": text})
            assert response.status_code == 201
            saved.append(response.json())
    offline = load_settings({"FYODOR_DATA_DIR": str(settings.data_dir), "FYODOR_ALLOW_NETWORK": "0",
                             "FYODOR_FRONTEND_DIST": str(settings.frontend_dist)})
    with TestClient(create_app(offline)) as restarted:
        assert {d["name"] for d in restarted.get("/api/decks").json()} == {"Goblins", "Spells"}
        for deck in saved:
            response = restarted.get(f"/api/decks/{deck['id']}")
            assert response.status_code == 200
            assert response.json()["entries"] == deck["entries"]
            assert all(e["printing_id"] for e in response.json()["entries"])
        assert restarted.get("/api/decks/import-options").json()["archidekt_url"] is False
