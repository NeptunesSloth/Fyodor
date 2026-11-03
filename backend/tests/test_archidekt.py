"""Archidekt compatibility: text exports, API JSON, URL import, export round trip, source diff."""

from __future__ import annotations

import copy
import json
import time
from collections import Counter
from pathlib import Path

import httpx
import pytest

from app.cards.importer import build_database
from app.decks import archidekt, service
from app.decks.models import DeckImportRequest
from tests.fixtures.cards import cid, fixture_cards

FIXTURES = Path(__file__).parent / "fixtures" / "archidekt"
COMMANDER_TEXT = (FIXTURES / "commander_export.txt").read_text()
CONSTRUCTED_TEXT = (FIXTURES / "constructed_export.txt").read_text()
DECK_JSON = json.loads((FIXTURES / "commander_deck.json").read_text())


def by_name(entries, name, section=None):
    return [e for e in entries if e.name == name and (section is None or e.section == section)]


def sections(entries):
    out: Counter[str] = Counter()
    for e in entries:
        out[e.section] += e.quantity
    return dict(out)


# --------------------------------------------------------------------------- URL / id parsing


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://archidekt.com/decks/3949701/upping_the_average_atraxa", "3949701"),
        ("archidekt.com/decks/123", "123"),
        ("https://www.archidekt.com/decks/77#main", "77"),
        ("https://archidekt.com/api/decks/88/", "88"),
        ("  4242 ", "4242"),
        ("https://moxfield.com/decks/abc", None),
        ("not a deck", None),
    ],
)
def test_extract_deck_id(value, expected):
    assert archidekt.extract_deck_id(value) == expected


# --------------------------------------------------------------------------- text exports


def test_commander_text_export_keeps_everything(cards):
    result = service.import_any(DeckImportRequest(text=COMMANDER_TEXT), cards)
    entries, report = result.entries, result.report
    assert sections(entries) == {"commander": 1, "main": 50, "sideboard": 2, "maybeboard": 1}
    assert report.commanders == ["Atraxa, Praetors' Voice"]
    assert report.cards_total == 53  # maybeboard excluded
    assert not report.unresolved

    atraxa = by_name(entries, "Atraxa, Praetors' Voice")[0]
    assert (atraxa.set_code, atraxa.collector_number, atraxa.resolution) == ("2x2", "190", "exact")
    assert by_name(entries, "Arcane Signet")[0].finish == "foil"
    assert by_name(entries, "Swords to Plowshares")[0].finish == "etched"
    assert by_name(entries, "Counterspell")[0].categories == ["Interaction", "Counterspell"]
    assert by_name(entries, "Llanowar Elves")[0].categories == ["Ramp", "Creature"]
    delver = by_name(entries, "Delver of Secrets // Insectile Aberration")[0]
    assert delver.tags == ["Have"] and delver.printing_id == cid("Delver of Secrets // Insectile Aberration|isd|51")
    assert by_name(entries, "Opt")[0].section == "maybeboard"
    assert by_name(entries, "Pyroblast")[0].section == "sideboard"

    # unknown printing -> right card, sensible printing, reported (never fails the deck)
    bolt = by_name(entries, "Lightning Bolt")[0]
    assert bolt.printing_id and bolt.resolution == "fallback"
    assert bolt.requested and bolt.requested.set_code == "xyz"
    assert report.fallbacks == [{"name": "Lightning Bolt", "requested": "XYZ #1", "used": "CLB #187", "resolution": "fallback"}]
    assert report.exact_printings == 53  # every other printing (all boards) matched exactly

    cats = {c.name: c for c in service.deck_categories(result.parsed)}
    assert cats["Commander"].premier
    assert not cats["Sideboard"].included_in_deck and not cats["Maybeboard"].included_in_deck
    assert {"Ramp", "Land", "Interaction", "Counterspell", "Removal", "Creature"} <= set(cats)


def test_constructed_text_export_keeps_multiple_printings(cards):
    result = service.import_any(DeckImportRequest(text=CONSTRUCTED_TEXT), cards)
    entries = result.entries
    assert sections(entries) == {"main": 60, "sideboard": 5, "maybeboard": 1}
    sol = by_name(entries, "Sol Ring")
    assert sorted((e.set_code, e.quantity, e.finish) for e in sol) == [("c21", 2, "foil"), ("cmm", 2, "nonfoil")]
    assert all(e.resolution == "exact" for e in entries)
    assert by_name(entries, "Swords to Plowshares")[0].section == "sideboard"


def test_single_bracket_token_resolved_as_set_or_category(cards):
    entries = service.import_any(DeckImportRequest(text="1 Sol Ring [C21]\n1x Arcane Signet [Ramp]\n1 Opt [Maybe]"), cards).entries
    assert by_name(entries, "Sol Ring")[0].set_code == "c21"
    assert by_name(entries, "Arcane Signet")[0].categories == ["Ramp"]
    assert by_name(entries, "Opt")[0].section == "maybeboard"


def test_plain_section_headers_still_work(cards):
    text = "Commander\n1 Atraxa, Praetors' Voice\n\nMainboard\n1 Sol Ring\n\nSideboard\n1 Opt\n\nMaybeboard\n1 Pyroblast\n"
    assert sections(service.import_any(DeckImportRequest(text=text), cards).entries) == {
        "commander": 1, "main": 1, "sideboard": 1, "maybeboard": 1,
    }


# --------------------------------------------------------------------------- API JSON


def test_archidekt_json_uses_exact_scryfall_ids(cards):
    result = service.import_any(DeckImportRequest(json=json.dumps(DECK_JSON)), cards)
    entries, report = result.entries, result.report
    assert result.source and result.source.kind == "archidekt" and result.source.id == "424242"
    assert result.format == "commander"
    assert sections(entries) == {"commander": 1, "main": 48, "sideboard": 2, "maybeboard": 2}  # main includes the custom card
    assert report.commanders == ["Atraxa, Praetors' Voice"]
    assert by_name(entries, "Sol Ring")[0].finish == "foil"
    assert by_name(entries, "Counterspell")[0].finish == "etched"
    assert by_name(entries, "Fire // Ice")[0].section == "maybeboard"  # category excluded from deck
    assert not by_name(entries, "Llanowar Elves")  # soft-deleted on Archidekt
    # printing id Scryfall no longer knows -> resolved through the oracle id
    bolt = by_name(entries, "Lightning Bolt")[0]
    assert bolt.resolution == "fallback" and bolt.oracle_id == cid("oracle|Lightning Bolt") and bolt.printing_id
    assert [u.name for u in report.unresolved] == ["Homebrew Dragon"]
    assert any("Homebrew Dragon" in n for n in report.notes)
    assert all(e.resolution == "exact" for e in entries if e.name not in ("Lightning Bolt", "Homebrew Dragon"))


def test_only_the_primary_category_takes_a_card_out_of_the_deck(cards):
    """Archidekt decides "in the deck" by a card's first (primary) category: a card filed under Creature that also
    carries a Maybeboard or Sideboard category still counts. Shape from a real deck (archidekt.com/decks/21442172):
    Stirring Hopesinger ['Creature', 'Maybeboard'] and Beacon of Immortality ['Maybeboard', 'Sideboard']; the site
    shows "Deck size: 100" where the import counted 97."""
    before = service.import_any(DeckImportRequest(json=json.dumps(DECK_JSON)), cards)
    deck = copy.deepcopy(DECK_JSON)
    recat = {"Sol Ring": ["Ramp", "Maybeboard"], "Swords to Plowshares": ["Removal", "Sideboard"], "Opt": ["Maybeboard", "Sideboard"]}
    for item in deck["cards"]:
        name = item["card"]["oracleCard"]["name"]
        if name in recat:
            item["categories"] = recat[name]
    result = service.import_any(DeckImportRequest(json=json.dumps(deck)), cards)
    entries = result.entries
    assert by_name(entries, "Sol Ring")[0].section == "main"
    assert by_name(entries, "Swords to Plowshares")[0].section == "main"
    assert by_name(entries, "Opt")[0].section == "maybeboard"  # primary Maybeboard: out of the deck
    assert by_name(entries, "Sol Ring")[0].categories == ["Ramp", "Maybeboard"]  # kept for export
    assert result.report.cards_total == before.report.cards_total  # a second category moves nothing out


def test_json_with_unexpected_shape_is_rejected_cleanly(cards):
    with pytest.raises(archidekt.ArchidektError):
        service.import_any(DeckImportRequest(json='{"hello": 1}'), cards)
    with pytest.raises(archidekt.ArchidektError):
        service.import_any(DeckImportRequest(json="{nope"), cards)
    # malformed individual cards are skipped, not fatal
    broken = copy.deepcopy(DECK_JSON)
    broken["cards"].append({"quantity": "x", "card": None})
    broken["cards"].append("garbage")
    result = service.import_any(DeckImportRequest(json=json.dumps(broken)), cards)
    assert result.report.errors and result.entries


# --------------------------------------------------------------------------- export round trip


def test_archidekt_export_round_trip(cards):
    first = service.import_any(DeckImportRequest(text=COMMANDER_TEXT), cards).entries
    text = archidekt.format_archidekt_text([e.model_dump() for e in first])
    assert "1x Atraxa, Praetors' Voice (2x2) 190 [Commander{top}]" in text
    assert "2x Pyroblast (ice) 213 [Sideboard{noDeck}]" in text
    assert "1x Opt (eld) 59 [Maybeboard{noDeck}{noPrice}]" in text
    assert "1x Arcane Signet (cmm) 370 *F* [Ramp]" in text
    second = service.import_any(DeckImportRequest(text=text), cards).entries

    def key(entries):
        return sorted((e.section, e.quantity, e.name, e.set_code, e.collector_number, e.finish, tuple(e.categories))
                      for e in entries)

    assert key(first) == key(second)


# --------------------------------------------------------------------------- fetch error handling


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_deck_errors_are_readable():
    with _client(lambda r: httpx.Response(404)) as c, pytest.raises(archidekt.ArchidektError, match="doesn't exist"):
        archidekt.fetch_deck("1", user_agent="t", client=c)
    with _client(lambda r: httpx.Response(403)) as c, pytest.raises(archidekt.ArchidektError, match="private"):
        archidekt.fetch_deck("1", user_agent="t", client=c)
    with _client(lambda r: httpx.Response(200, json={"detail": "x"})) as c, pytest.raises(archidekt.ArchidektError):
        archidekt.fetch_deck("1", user_agent="t", client=c)

    def boom(request):
        raise httpx.ConnectError("offline")

    with _client(boom) as c, pytest.raises(archidekt.ArchidektError, match="Could not reach"):
        archidekt.fetch_deck("1", user_agent="t", client=c)
    with _client(lambda r: httpx.Response(200, json=DECK_JSON)) as c:
        assert archidekt.fetch_deck("424242", user_agent="t", client=c)["id"] == 424242


# --------------------------------------------------------------------------- API workflow


@pytest.fixture()
def remote(client):
    """Stub Archidekt: tests edit ``state['deck']`` to simulate changes on the site."""
    state = {"deck": copy.deepcopy(DECK_JSON), "calls": 0}

    def fetch(deck_id):
        state["calls"] += 1
        if deck_id != "424242":
            raise archidekt.ArchidektError("Archidekt says this deck doesn't exist (or it is private).")
        return copy.deepcopy(state["deck"])

    client.app.state.services.archidekt_fetch = fetch
    return state


def test_url_import_preview_create_and_offline_use(client, remote):
    options = client.get("/api/decks/import-options").json()
    assert options["archidekt_url"] is True
    preview = client.post("/api/decks/preview", json={"archidekt": "https://archidekt.com/decks/424242/atraxa"}).json()
    assert preview["report"]["commanders"] == ["Atraxa, Praetors' Voice"]
    assert preview["report"]["fallbacks"][0]["name"] == "Lightning Bolt"
    assert "Ramp" in preview["report"]["categories"]
    assert preview["source"]["id"] == "424242"

    deck = client.post("/api/decks", json={"archidekt": "424242"}).json()
    assert deck["name"] == "Atraxa Counters (fixture)"
    assert deck["source"]["url"] == "https://archidekt.com/decks/424242"
    assert {c["name"] for c in deck["categories"]} >= {"Commander", "Ramp", "Wishlist"}
    calls = remote["calls"]
    # everything after import works without Archidekt
    assert client.get(f"/api/decks/{deck['id']}").status_code == 200
    assert client.get(f"/api/decks/{deck['id']}/export").text.startswith("1x Atraxa")
    game = client.post("/api/games", json={"players": [{"name": "A", "deck_id": deck["id"]}]}).json()
    assert game["game"]["id"]
    assert remote["calls"] == calls

    missing = client.post("/api/decks/preview", json={"archidekt": "https://archidekt.com/decks/1/x"})
    assert missing.status_code == 502 and "doesn't exist" in missing.json()["detail"]
    # a link the host won't fetch is the client's mistake (422), with that site's steps (tests/test_deck_sites.py)
    bad = client.post("/api/decks/preview", json={"archidekt": "https://example.com/decks/x"})
    assert bad.status_code == 422 and "doesn't look like" in bad.json()["detail"]
    moxfield = client.post("/api/decks/preview", json={"archidekt": "https://moxfield.com/decks/x"})
    assert moxfield.status_code == 422 and "Copy Plain Text" in moxfield.json()["detail"]


def test_source_check_apply_keeps_local_edits(client, remote):
    deck = client.post("/api/decks", json={"archidekt": "424242"}).json()
    did = deck["id"]
    assert client.post(f"/api/decks/{did}/source/check").json()["diff"]["changed"] is False

    # local edit: 30 -> 28 Islands
    entries = deck["entries"]
    for e in entries:
        if e["name"] == "Island":
            e["quantity"] = 28
    client.put(f"/api/decks/{did}", json={"name": deck["name"], "format": "commander", "entries": entries,
                                          "categories": deck["categories"]})

    # remote edits: +Opt moved to main? no: add Arcane Signet copy; remove Forest; Sol Ring reprint; Islands 30 -> 29
    cards = remote["deck"]["cards"]
    remote["deck"]["cards"] = [c for c in cards if c["card"]["oracleCard"]["name"] != "Forest"]
    for c in remote["deck"]["cards"]:
        name = c["card"]["oracleCard"]["name"]
        if name == "Sol Ring":
            c["card"]["uid"] = cid("Sol Ring|c21|263")
            c["card"]["edition"]["editioncode"], c["card"]["collectorNumber"] = "c21", "263"
        if name == "Island":
            c["quantity"] = 29
    extra = copy.deepcopy(cards[2])
    extra["card"]["uid"] = cid("Mountain|cmm|1003")
    extra["card"]["oracleCard"] = {"uid": cid("oracle|Mountain"), "name": "Mountain"}
    extra["categories"] = ["Land"]
    remote["deck"]["cards"].append(extra)

    check = client.post(f"/api/decks/{did}/source/check").json()
    diff = check["diff"]
    assert check["local_edits"] is True
    assert {a["name"] for a in diff["added"]} == {"Mountain"}
    assert {(r["name"], r["quantity"]) for r in diff["removed"]} == {("Forest", 10), ("Island", 1)}
    assert diff["printing_changed"] == [{"name": "Sol Ring", "from": "CMM #410", "to": "C21 #263"}]

    applied = client.post(f"/api/decks/{did}/source/apply").json()
    names = {e["name"]: e for e in applied["entries"]}
    assert "Forest" not in names and "Mountain" in names
    assert names["Sol Ring"]["set_code"] == "c21"
    assert names["Island"]["quantity"] == 28  # local edit wins
    assert any("Island" in c for c in applied["conflicts"])
    assert client.post(f"/api/decks/{did}/source/check").json()["diff"]["changed"] is False


def test_source_ignore_acknowledges_without_changing_deck(client, remote):
    deck = client.post("/api/decks", json={"archidekt": "424242"}).json()
    remote["deck"]["cards"] = remote["deck"]["cards"][:-3]
    before = client.get(f"/api/decks/{deck['id']}").json()["entries"]
    assert client.post(f"/api/decks/{deck['id']}/source/check").json()["diff"]["changed"] is True
    after = client.post(f"/api/decks/{deck['id']}/source/ignore").json()["entries"]
    assert after == before
    assert client.post(f"/api/decks/{deck['id']}/source/check").json()["diff"]["changed"] is False


def test_text_decks_have_no_source_link(client):
    deck = client.post("/api/decks", json={"text": COMMANDER_TEXT}).json()
    assert deck["source"] is None
    assert client.post(f"/api/decks/{deck['id']}/source/check").status_code == 409


def test_network_disabled_hides_url_import(settings, card_db):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    offline = Settings(**{**settings.__dict__, "allow_network": False})
    with TestClient(create_app(offline)) as c:
        opts = c.get("/api/decks/import-options").json()
        assert opts["archidekt_url"] is False and "disabled" in opts["archidekt_url_note"]
        assert c.post("/api/decks/preview", json={"archidekt": "424242"}).status_code == 502
        assert c.post("/api/decks/preview", json={"text": "1 Sol Ring"}).status_code == 200


def test_decks_survive_card_database_updates(client, settings):
    deck = client.post("/api/decks", json={"text": "1x Sol Ring (cmm) 410 [Ramp]\n1 Opt"}).json()
    sol = by_name_dict(deck["entries"], "Sol Ring")
    assert sol["printing_id"] == cid("Sol Ring|cmm|410")
    # a Scryfall update drops that printing
    remaining = [c for c in fixture_cards() if not (c["name"] == "Sol Ring" and c["set"] == "cmm")]
    build_database(remaining, settings.cards_db_path)
    time.sleep(0.01)
    after = client.get(f"/api/decks/{deck['id']}").json()
    sol = by_name_dict(after["entries"], "Sol Ring")
    assert sol["printing_id"] in (cid("Sol Ring|c21|263"), cid("Sol Ring|sld|999"))
    assert sol["oracle_id"] == cid("oracle|Sol Ring")
    assert sol["categories"] == ["Ramp"]
    assert any("no longer in the card database" in w["message"] for w in after["warnings"])


def by_name_dict(entries, name):
    return next(e for e in entries if e["name"] == name)


def test_cache_art_job(client, remote):
    deck = client.post("/api/decks", json={"archidekt": "424242"}).json()
    seen = {}

    def fake_cache(ids, progress):
        seen["ids"] = ids
        progress(3, 3, 0)
        return "3 downloaded"

    client.app.state.services.cache_artwork = fake_cache
    status = client.get(f"/api/decks/{deck['id']}/art-status").json()
    assert status["missing"] == status["printings"] > 0
    job = client.post(f"/api/decks/{deck['id']}/cache-art").json()
    for _ in range(50):
        state = client.get(f"/api/jobs/{job['id']}").json()
        if state["state"] != "running":
            break
        time.sleep(0.02)
    assert state["state"] == "done" and state["message"] == "3 downloaded" and state["done"] == 3
    assert set(seen["ids"]) >= {cid("Atraxa, Praetors' Voice|2x2|190")}
    assert client.get("/api/jobs/nope").status_code == 404
