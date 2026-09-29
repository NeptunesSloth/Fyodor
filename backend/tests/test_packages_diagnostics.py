"""Portable game packages (export / validated import) and the local diagnostics export."""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.images import png
from tests.test_protocol_privacy import P1_DECK, P2_DECK


@pytest.fixture()
def game(client):
    a = client.post("/api/decks", json={"text": P1_DECK}).json()["id"]
    b = client.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    body = client.post("/api/games", json={"mode": "local", "players": [{"name": "Alice", "deck_id": a}, {"name": "Bob", "deck_id": b}]}).json()
    return body["game"]["id"]


def act(client, gid, action, viewer="p1"):
    res = client.post(f"/api/games/{gid}/actions", json={"action": action, "viewer": viewer})
    assert res.status_code == 200, res.text
    return res.json()


def state(client, gid):
    return client.app.state.services.hub.get(gid).session.state


def upload(client, data, kind, name):
    res = client.post(f"/api/assets?kind={kind}&name={name}", content=data, headers={"Content-Type": "application/octet-stream"})
    assert res.status_code == 201, res.text
    return res.json()


def make_package(client, gid):
    mat = upload(client, png(16, 9, (10, 80, 30)), "playmat", "Forest mat")
    sleeve = upload(client, png(5, 7, (120, 0, 0)), "card_back", "Red sleeves")
    act(client, gid, {"type": "set_appearance", "sleeve": sleeve["id"], "playmat": {"asset_id": mat["id"]}})
    act(client, gid, {"type": "draw", "count": 3})
    first = next(c.card_id for c in state(client, gid).cards.values() if c.card_id)
    oracle = client.get(f"/api/cards/{first}").json()["oracle_id"]
    client.post("/api/macros", json={"scope": "card", "oracle_id": oracle, "definition": {"name": "Ping", "steps": [{"op": "CHANGE_LIFE", "player": "each_opponent", "delta": -1}]}})
    client.post("/api/macros", json={"scope": "card", "oracle_id": "not-in-this-game", "definition": {"name": "Other", "steps": [{"op": "FLIP_COIN"}]}})
    save = client.post(f"/api/games/{gid}/save", json={"name": "Friday game"}).json()
    res = client.get(f"/api/saves/{save['id']}/package")
    assert res.status_code == 200 and res.headers["content-type"] == "application/zip"
    assert 'filename="Friday game.fyodor.zip"' in res.headers["content-disposition"]
    return res.content, save, mat, sleeve


def test_package_round_trip_on_a_clean_machine(client, game):
    blob, save, mat, sleeve = make_package(client, game)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert {a["id"] for a in manifest["assets"]} == {mat["id"], sleeve["id"]}
        assert [m["definition"]["name"] for m in json.loads(zf.read("macros.json"))] == ["Ping"]  # only this game's cards
    before = state(client, game).model_dump(mode="json")

    # simulate the other machine: none of the game's assets, macros or saves exist
    services = client.app.state.services
    client.delete(f"/api/games/{game}")
    for a in (mat, sleeve):
        assert client.delete(f"/api/assets/{a['id']}").status_code == 204
    for m in client.get("/api/macros").json():
        client.delete(f"/api/macros/{m['id']}")
    client.delete(f"/api/saves/{save['id']}")

    res = client.post("/api/packages/import", content=blob, headers={"Content-Type": "application/zip"})
    assert res.status_code == 201, res.text
    out = res.json()
    assert out["assets_added"] == 2 and out["macros_added"] == 1 and out["save"]["name"] == "Friday game (imported)"
    loaded = client.post(f"/api/saves/{out['save']['id']}/load", json={"mode": "local"}).json()
    st = services.hub.get(loaded["game"]["id"]).session.state
    p1 = st.players["p1"]
    new_ids = {p1.sleeve, p1.playmat.asset_id}
    assert new_ids.isdisjoint({mat["id"], sleeve["id"]})  # re-created under fresh ids and remapped
    assert client.get(f"/api/assets/{p1.playmat.asset_id}/file").content == png(16, 9, (10, 80, 30))
    assert st.zones == {k: v for k, v in before["zones"].items()} and len(st.zones["p1:hand"]) == 3
    assert [m["name"] for m in client.get("/api/macros").json()] == ["Ping"]

    # importing again reuses identical images and skips duplicate macros
    again = client.post("/api/packages/import", content=blob).json()
    assert again["assets_added"] == 0 and again["macros_added"] == 0


def zip_of(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_hostile_packages_are_rejected(client, game, settings):
    blob, *_ = make_package(client, game)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        good = {n: zf.read(n) for n in zf.namelist()}
    manifest = json.loads(good["manifest.json"])

    def attempt(files):
        return client.post("/api/packages/import", content=zip_of(files))

    def with_manifest(**changes):
        m = json.loads(json.dumps(manifest))
        m.update(changes)
        return {**good, "manifest.json": json.dumps(m).encode()}

    assert client.post("/api/packages/import", content=b"MZ not a zip").status_code == 422
    assert attempt({"manifest.json": b'{"format": "something-else", "version": 1}'}).status_code == 422
    assert attempt(with_manifest(version=99)).status_code == 422
    # path traversal / arbitrary names in the manifest
    for bad_file in ("../../etc/passwd", "/etc/passwd", "assets/../../x.png", "assets\\x.png"):
        m = with_manifest(assets=[{**manifest["assets"][0], "file": bad_file}])
        assert attempt(m).status_code == 422
    # a disguised executable with a matching checksum is still not an image
    import hashlib
    evil = b"MZ\x90\x00" + b"\x00" * 200
    entry = {**manifest["assets"][0], "sha256": hashlib.sha256(evil).hexdigest()}
    files = with_manifest(assets=[entry])
    files[entry["file"]] = evil
    res = attempt(files)
    assert res.status_code == 422 and "image" in res.json()["detail"].lower()
    # tampered image
    files = dict(good)
    files[manifest["assets"][0]["file"]] = png(3, 3)
    assert "checksum" in attempt(files).json()["detail"]
    # macros must be declarative data
    files = {**good, "macros.json": json.dumps([{"scope": "library", "definition": {"name": "x", "steps": [{"op": "EXEC", "code": "import os"}]}}]).encode()}
    assert attempt(files).status_code == 422
    # corrupt save
    assert attempt({**good, "save.fyodor": b"garbage"}).status_code == 422
    # nothing was written outside the data directory
    assert not (settings.data_dir.parent / "x.png").exists()
    # the host computer only
    remote = TestClient(client.app, client=("192.168.1.20", 50000))
    assert remote.post("/api/packages/import", content=blob).status_code == 403
    assert remote.get(f"/api/saves/{'0' * 32}/package").status_code == 403


def test_diagnostics_exclude_private_information_unless_opted_in(client, game):
    act(client, game, {"type": "draw", "count": 7})
    act(client, game, {"type": "note", "card_id": state(client, game).zones["p1:hand"][0], "text": "secret plan"})
    hand_names = {state(client, game).cards[c].name for c in state(client, game).zones["p1:hand"]}
    res = client.get("/api/diagnostics")
    assert res.status_code == 200 and "attachment" in res.headers["content-disposition"]
    text = res.text
    body = res.json()
    assert body["includes_private_information"] is False
    assert body["rooms"][0]["cards"] > 0 and body["rooms"][0]["problems"] == []
    assert "secret plan" not in text and not any(n in text for n in hand_names)
    assert "Counterspell" not in text  # nothing from decklists either
    private = client.get("/api/diagnostics?include_private=true")
    assert "secret plan" in private.text and "PRIVATE" in private.headers["content-disposition"]
    remote = TestClient(client.app, client=("192.168.1.20", 50000))
    assert remote.get("/api/diagnostics").status_code == 403
