"""Coverage metadata (FULL / PARTIAL / MANUAL) and the pod card inventory."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.rules import cards as scripts
from app.rules import coverage
from app.rules.characteristics import Characteristics, mana_value, parse_type_line
from app.rules.oracle import parse_abilities
from tests.test_protocol_privacy import P1_DECK, P2_DECK


def test_type_lines_and_mana_values():
    assert parse_type_line("Legendary Creature — Elf Druid") == (
        frozenset({"Legendary"}), frozenset({"Creature"}), frozenset({"Elf", "Druid"}))
    assert parse_type_line("Basic Land — Forest")[1] == frozenset({"Land"})
    assert mana_value("{2}{G}{G}") == 4 and mana_value("{X}{R}") == 1 and mana_value("{2/B}{G/W}") == 3


def test_oracle_lines_are_classified():
    kinds = [a.kind for a in parse_abilities(
        "Flying, vigilance\n{T}: Add {G}.\nWhen this enters, draw a card.\n{2}, {T}: Destroy target artifact.\n"
        "+1: Scry 1.\nCreatures you control get +1/+1.")]
    assert kinds == ["keywords", "mana", "triggered", "activated", "loyalty", "static"]
    assert [a.kind for a in parse_abilities("Destroy target creature. (Reminder.)", spell=True)] == ["spell"]
    assert parse_abilities("({T}: Add {G}.)") == []  # basic land: reminder text only
    # keyword *actions* in a spell are its effect, not keyword abilities
    assert [a.kind for a in parse_abilities("Scry 2.\nProliferate.", spell=True)] == ["spell", "spell"]


def test_card_coverage_levels(cards):
    mountain = coverage.of_card_data(cards.resolve("Mountain"))
    bolt = coverage.of_card_data(cards.resolve("Lightning Bolt"))
    tower = coverage.of_card_data(cards.resolve("Command Tower"))
    assert mountain.level == "PARTIAL" and mountain.manual_parts == ["{T}: Add {R} (basic land type)"]
    assert tower.level == "PARTIAL"
    assert bolt.level == "MANUAL" and "Lightning Bolt deals 3 damage to any target." in bolt.manual_parts


def test_full_only_when_every_part_is_supported(cards, monkeypatch):
    monkeypatch.setattr(coverage, "SUPPORTED", {"play:land", "mana:intrinsic"})
    assert coverage.of_card_data(cards.resolve("Forest")).level == "FULL"
    vanilla = Characteristics(name="Grizzly Bears", types=frozenset({"Creature"}), power="2", toughness="2")
    assert coverage.of_characteristics(vanilla).level == "MANUAL"
    monkeypatch.setattr(coverage, "SUPPORTED", {"cast:spell", "combat"})
    assert coverage.of_characteristics(vanilla).level == "FULL"


def test_scripts_cover_abilities(cards):
    bolt = cards.resolve("Lightning Bolt")
    script = scripts.CardScript(oracle_id=bolt["oracle_id"], name="Lightning Bolt", covers=frozenset({0}))
    scripts._REGISTRY[script.oracle_id] = script
    try:
        cov = coverage.of_card_data(bolt)
        assert "Lightning Bolt deals 3 damage to any target." not in cov.manual_parts
        assert cov.level == "PARTIAL"  # still needs "cast:spell"
    finally:
        del scripts._REGISTRY[script.oracle_id]


def test_coverage_api(client):
    bolt = client.get("/api/cards/search?q=Lightning Bolt").json()["results"][0]
    res = client.get(f"/api/rules/coverage?card_ids={bolt['id']},nonexistent").json()
    assert res[bolt["id"]]["level"] == "MANUAL" and "nonexistent" not in res
    by_oracle = client.get(f"/api/rules/coverage?oracle_ids={bolt['oracle_id']}").json()
    assert by_oracle[bolt["oracle_id"]]["name"] == "Lightning Bolt"
    assert "play:land" in client.get("/api/rules/support").json()["features"]
    assert client.get("/api/rules/coverage?card_ids=" + ",".join(["x"] * 300)).status_code == 422


def test_pod_inventory_from_library_and_saved_games(client):
    client.post("/api/decks", json={"text": P1_DECK})
    b = client.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    a2 = client.post("/api/decks", json={"text": "Deck\n1x Sol Ring\n1x Lightning Bolt\n5x Island\n1x Totally Fake Card"}).json()
    assert a2["id"]
    game = client.post("/api/games", json={"mode": "local", "players": [{"name": "Bob", "deck_id": b}]}).json()
    client.post(f"/api/games/{game['game']['id']}/save", json={"name": "s"})
    report = client.get("/api/rules/inventory").json()
    rows = {r["name"]: r for r in report["cards"]}
    assert len(report["decks"]) == 3 and report["games"] == 1
    assert rows["Sol Ring"]["deck_count"] == 2 and rows["Island"]["copies"] == 15 and rows["Island"]["basic_land"]
    assert rows["Lightning Bolt"]["deck_count"] == 2 and rows["Lightning Bolt"]["games"] == 1
    assert report["cards"][0]["deck_count"] == 2  # most-played first
    assert rows["Lightning Bolt"]["coverage"] == "MANUAL" and rows["Island"]["coverage"] == "PARTIAL"
    assert report["summary"]["PARTIAL"] >= 2 and 0 <= report["weighted_full"] <= 1
    md = client.get("/api/rules/inventory.md").text
    assert "| Sol Ring |" in md and "Rules coverage" in md
    remote = TestClient(client.app, client=("192.168.1.20", 50000))
    assert remote.get("/api/rules/inventory").status_code == 403
    assert remote.get("/api/rules/support").status_code == 200  # card-level info is public


def test_inventory_tool(settings, card_db, tmp_path, capsys):
    from tools import rules_inventory

    deck_file = tmp_path / "goblins.txt"
    deck_file.write_text(P2_DECK)
    out = tmp_path / "out"
    code = rules_inventory.main(["--data-dir", str(settings.data_dir), "--deck-file", str(deck_file), "--out", str(out)])
    assert code == 0 and "1 decks" in capsys.readouterr().out
    report = json.loads((out / "rules_inventory.json").read_text())
    assert {r["name"] for r in report["cards"]} >= {"Krenko, Mob Boss", "Mountain", "Lightning Bolt"}
    assert (out / "rules_inventory.md").read_text().startswith("# Rules coverage")
