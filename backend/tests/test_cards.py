from __future__ import annotations

import gzip
import json
from pathlib import Path

import httpx
import pytest

from app.cards.downloader import ImageJob, download_file, download_images
from app.cards.images import ImageStore, InvalidImageRequest
from app.cards.importer import ImportFormatError, build_database, import_file, iter_bulk_file, write_jsonl_gz
from app.cards.names import normalize_name
from app.cards.repository import CardRepository
from tests.fixtures.cards import GOBLIN, cid, fixture_cards


def test_normalize_name():
    assert normalize_name("Fire/Ice") == "fire // ice"
    assert normalize_name("  Fire  //  Ice ") == "fire // ice"
    assert normalize_name("Lim-Dûl the Necromancer") == "lim-dul the necromancer"
    assert normalize_name("Atraxa, Praetors’ Voice") == "atraxa, praetors' voice"
    assert normalize_name("Æther Vial") == "aether vial"


def test_iter_bulk_jsonl_gz_and_array(tmp_path: Path):
    cards = fixture_cards()
    jsonl = tmp_path / "c.jsonl.gz"
    write_jsonl_gz(cards, jsonl)
    assert [c["id"] for c in iter_bulk_file(jsonl)] == [c["id"] for c in cards]

    legacy = tmp_path / "c.json"
    legacy.write_text("[\n" + ",\n".join(json.dumps(c) for c in cards) + "\n]\n")
    assert len(list(iter_bulk_file(legacy))) == len(cards)

    compact = tmp_path / "compact.json.gz"
    with gzip.open(compact, "wt") as fh:
        json.dump(cards, fh)
    assert len(list(iter_bulk_file(compact))) == len(cards)

    bad = tmp_path / "bad.json"
    bad.write_text("hello")
    with pytest.raises(ImportFormatError):
        list(iter_bulk_file(bad))


def test_import_skips_art_series_and_counts(tmp_path: Path):
    result = build_database(fixture_cards(), tmp_path / "cards.sqlite")
    assert result.skipped == 1
    assert result.tokens == 2
    assert result.printings == len(fixture_cards()) - 1


def test_failed_import_keeps_previous_database(tmp_path: Path):
    dest = tmp_path / "cards.sqlite"
    build_database(fixture_cards(), dest)

    def broken():
        yield from fixture_cards()[:3]
        raise RuntimeError("network died")

    with pytest.raises(RuntimeError):
        build_database(broken(), dest)
    repo = CardRepository(dest, ImageStore(tmp_path / "img"))
    assert repo.stats()["printings"] == len(fixture_cards()) - 1
    assert not (tmp_path / "cards.sqlite.building").exists()


def test_import_file(tmp_path: Path):
    src = tmp_path / "bulk.jsonl.gz"
    write_jsonl_gz(fixture_cards(), src)
    result = import_file(src, tmp_path / "out.sqlite", meta={"bulk_type": "x"})
    assert result.oracle_cards == 56


def test_default_printing_prefers_regular_sets(cards: CardRepository):
    sol = cards.resolve("Sol Ring")
    assert sol is not None
    assert sol["set_code"] == "cmm"  # newest non-promo, non-box printing


def test_resolve_variants(cards: CardRepository):
    assert cards.resolve("sol ring", "C21")["set_code"] == "c21"
    assert cards.resolve("Sol Ring", "c21", "263")["collector_number"] == "263"
    assert cards.resolve("Sol Ring", "zzz")["set_code"] == "cmm"  # unknown set -> default
    assert cards.resolve("Fire/Ice")["name"] == "Fire // Ice"
    assert cards.resolve("Fire")["name"] == "Fire // Ice"  # face name
    assert cards.resolve("Delver of Secrets")["layout"] == "transform"
    assert cards.resolve("Lim-Dul the Necromancer")["name"] == "Lim-Dûl the Necromancer"
    assert cards.resolve("Not A Card") is None
    assert cards.resolve("Seething Song")["name"] == "Seething Song"  # exact card beats a same-named face
    assert cards.resolve("Blazing Firesinger")["name"] == "Blazing Firesinger // Seething Song"


def test_suggestions(cards: CardRepository):
    assert cards.suggest("Sol Rng")[0] == "Sol Ring"
    assert cards.suggest("Solring")[0] == "Sol Ring"
    assert "Llanowar Elves" in cards.suggest("Llanowar Elfs")


def test_search(cards: CardRepository):
    names = lambda q, **kw: [c["name"] for c in cards.search(q, **kw)]  # noqa: E731
    assert "Sol Ring" in names("sol")[:2]  # (and Sol Grail)
    assert set(names("t:instant c:r -t:creature")) == {"Fire // Ice", "Lightning Bolt", "Seething Song", "Pyroblast"}
    assert "Counterspell" in names("o:counter")
    assert set(names("t:land -t:basic")) == {"Command Tower", "Thornwood Falls", "Shivan Reef", "Sungrass Prairie",
                                              "Ancient Ziggurat", "Vivid Marsh", "Tainted Isle", "Reflecting Pool", "Barren Moor"}
    assert set(names("is:commander")) >= {"Krenko, Mob Boss", "Atraxa, Praetors' Voice"}
    assert "Atraxa, Praetors' Voice" not in names("is:commander id:r")
    assert names("mv=4 c=r") == ["Krenko, Mob Boss"]
    assert names("goblin", tokens=True) == ["Goblin"]
    assert "Goblin" not in names("goblin")
    assert names("is:token treasure", tokens=False) == ["Treasure"]


def test_card_detail_faces_and_tokens(cards: CardRepository):
    delver = cards.get(cid("Delver of Secrets // Insectile Aberration|isd|51"))
    assert delver["double_faced"] is True
    assert [f["name"] for f in delver["faces"]] == ["Delver of Secrets", "Insectile Aberration"]
    fire = cards.resolve("Fire // Ice")
    assert fire["double_faced"] is False and len(fire["faces"]) == 2
    krenko = cards.get(cards.resolve("Krenko, Mob Boss")["id"])
    assert krenko["related_tokens"][0]["id"] == GOBLIN["id"]


def test_printings(cards: CardRepository):
    sol = cards.resolve("Sol Ring")
    assert {p["set_code"] for p in cards.printings(sol["oracle_id"])} == {"cmm", "c21", "sld"}


def test_image_store_rejects_traversal(tmp_path: Path):
    store = ImageStore(tmp_path)
    for bad in ("../../etc/passwd", "ABC", "0000-..", "7d3b0c1e-6a8e-4c79-9d7a-2f9a3b6d0e11/../x"):
        with pytest.raises(InvalidImageRequest):
            store.path_for(bad)
    with pytest.raises(InvalidImageRequest):
        store.path_for(cid("x"), size="huge")


def _transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_download_images_skips_existing_and_reports_failures(tmp_path: Path):
    store = ImageStore(tmp_path)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "fail" in str(request.url):
            return httpx.Response(500)
        return httpx.Response(200, content=b"jpegdata")

    a, b, c = cid("a"), cid("b"), cid("c")
    jobs = [
        ImageJob(a, False, [{"normal": "https://x/a.jpg"}]),
        ImageJob(b, True, [{"normal": "https://x/b0.jpg"}, {"normal": "https://x/b1.jpg"}]),
        ImageJob(c, False, [{"normal": "https://x/fail.jpg"}]),
    ]
    with _transport(handler) as client:
        report = download_images(client, store, jobs, workers=2)
    assert (report.downloaded, report.failed, report.requested) == (3, 1, 4)
    assert store.path_for(b, face=1, is_token=True).read_bytes() == b"jpegdata"
    assert store.find(a) is not None
    calls.clear()
    with _transport(handler) as client:
        report = download_images(client, store, jobs, workers=2)
    assert report.skipped == 3 and calls == ["https://x/fail.jpg"]


def test_download_file_resumes(tmp_path: Path):
    payload = b"0123456789" * 100
    seen_ranges: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        rng = request.headers.get("Range")
        seen_ranges.append(rng)
        if rng:
            start = int(rng.split("=")[1].rstrip("-"))
            return httpx.Response(206, content=payload[start:])
        return httpx.Response(200, content=payload)

    dest = tmp_path / "bulk.gz"
    (tmp_path / "bulk.gz.part").write_bytes(payload[:300])
    with _transport(handler) as client:
        download_file(client, "https://x/bulk", dest)
    assert dest.read_bytes() == payload
    assert seen_ranges == ["bytes=300-"]


def test_card_api(client):
    res = client.get("/api/cards/search", params={"q": "sol ring"})
    assert res.status_code == 200
    assert res.json()["results"][0]["name"] == "Sol Ring"
    sol_id = res.json()["results"][0]["id"]
    assert client.get(f"/api/cards/{sol_id}").json()["commander_legal"] == "legal"
    assert len(client.get(f"/api/cards/{sol_id}/printings").json()) == 3
    batch = client.post("/api/cards/batch", json={"ids": [sol_id, "nope"]}).json()
    assert list(batch) == [sol_id]
    assert client.get("/api/cards/nope").status_code == 404
    assert client.get("/api/cards/autocomplete", params={"q": "kren"}).json() == ["Krenko, Mob Boss"]
    tokens = client.get("/api/cards/search", params={"q": "", "tokens": "true"}).json()["results"]
    assert {t["name"] for t in tokens} == {"Treasure", "Goblin"}


def test_image_api(client, settings):
    sol_id = client.get("/api/cards/search", params={"q": "sol"}).json()["results"][0]["id"]
    assert client.get(f"/api/images/{sol_id}").status_code == 404
    path = ImageStore(settings.images_dir).path_for(sol_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xd8jpeg")
    res = client.get(f"/api/images/{sol_id}")
    assert res.status_code == 200 and res.content == b"\xff\xd8jpeg"
    assert client.get("/api/images/..%2F..%2Fetc%2Fpasswd").status_code in (400, 404)
    assert client.get(f"/api/images/{sol_id}", params={"size": "../x"}).status_code == 422
