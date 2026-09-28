"""Managed assets: content validation, storage, LAN rules, sleeves/playmats in games."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.assets.validate import InvalidImage, sniff
from tests.fixtures.images import jpeg_header, png, png_header_claiming, webp_vp8x


def test_formats_are_detected_from_content():
    assert (sniff(png(4, 3)).format, sniff(png(4, 3)).width, sniff(png(4, 3)).height) == ("png", 4, 3)
    info = sniff(jpeg_header(640, 480))
    assert (info.format, info.width, info.height, info.mime) == ("jpeg", 640, 480, "image/jpeg")
    assert (sniff(webp_vp8x(1200, 800)).width, sniff(webp_vp8x(1200, 800)).height) == (1200, 800)
    for bad in (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", b"GIF89a" + b"\x00" * 20, b"MZ\x90\x00" + b"\x00" * 60,
                b"#!/bin/sh\nrm -rf /\n" * 2, png_header_claiming(9000, 10)):
        with pytest.raises(InvalidImage):
            sniff(bad)


def upload(client, data, kind="playmat", name="Felt", headers=None):
    return client.post(f"/api/assets?kind={kind}&name={name}", content=data,
                       headers={"Content-Type": "application/octet-stream", **(headers or {})})


def test_upload_dedupe_replace_and_delete(client, settings):
    a = upload(client, png(8, 8), name="Green felt").json()
    b = upload(client, png(8, 8), name="Same image").json()
    assert a["sha256"] == b["sha256"] and a["id"] != b["id"] and a["width"] == 8
    files = list(settings.assets_dir.glob("*.png"))
    assert len(files) == 1 and files[0].name == f"{a['sha256']}.png"
    res = client.get(f"/api/assets/{a['id']}/file")
    assert res.status_code == 200 and res.headers["content-type"] == "image/png" and "immutable" in res.headers["cache-control"]
    assert res.content == png(8, 8)
    # disguised / unsupported uploads are rejected by content, whatever the name says
    assert upload(client, b"<svg/>" * 10, name="evil.png").status_code == 415
    assert upload(client, png(8, 8), kind="virus").status_code == 422
    # rename / duplicate / replace
    assert client.patch(f"/api/assets/{a['id']}", json={"name": "Blue felt"}).json()["name"] == "Blue felt"
    dup = client.post(f"/api/assets/{a['id']}/duplicate").json()
    assert dup["name"] == "Blue felt (copy)" and dup["sha256"] == a["sha256"]
    replaced = client.put(f"/api/assets/{a['id']}/file", content=png(16, 9, (10, 10, 90))).json()
    assert replaced["width"] == 16 and replaced["sha256"] != a["sha256"]
    for x in (b, dup):
        assert client.delete(f"/api/assets/{x['id']}").status_code == 204
    assert not (settings.assets_dir / f"{a['sha256']}.png").exists()  # last user gone: file removed
    assert (settings.assets_dir / f"{replaced['sha256']}.png").exists()
    kinds = {x["kind"] for x in client.get("/api/assets").json()}
    assert kinds == {"playmat"}


def test_files_are_served_by_id_only(client):
    for bad in ("..%2F..%2Fetc%2Fpasswd", "../app.sqlite", "0" * 16):
        assert client.get(f"/api/assets/{bad}/file").status_code == 404


def test_size_limit(client):
    big = png(4, 4) + b"\x00" * (20 * 1024 * 1024 + 10)
    assert upload(client, big).status_code == 413


def test_lan_players_bring_their_own_sleeves_and_playmats(client):
    body = client.post("/api/games", json={"mode": "lan", "players": [{"name": "Jonathan"}, {"name": "Mike"}]}).json()
    gid, host = body["game"]["id"], body["seat"]["token"]
    mike = client.post("/api/join", json={"code": body["game"]["code"], "name": "Mike"}).json()["token"]
    remote = TestClient(client.app, client=("192.168.1.20", 50000))
    assert upload(remote, png(), kind="card_back").status_code == 403  # no seat token
    sleeve = upload(remote, png(5, 7, (120, 20, 20)), kind="card_back", name="Red sleeves", headers={"X-Seat-Token": mike})
    assert sleeve.status_code == 201
    assert upload(remote, png(), kind="token_art", headers={"X-Seat-Token": mike}).status_code == 403
    sid = sleeve.json()["id"]
    assert remote.patch(f"/api/assets/{sid}", json={"name": "x"}).status_code == 403
    assert remote.delete(f"/api/assets/{sid}").status_code == 403

    def act(token, action):
        return remote.post(f"/api/games/{gid}/actions", json={"action": action}, headers={"X-Seat-Token": token})

    mat = upload(client, png(12, 8), kind="playmat").json()["id"]
    assert act(mike, {"type": "set_appearance", "sleeve": "f" * 16}).status_code == 404
    assert act(mike, {"type": "set_appearance", "sleeve": mat}).status_code == 422  # a playmat isn't a sleeve
    res = act(mike, {"type": "set_appearance", "sleeve": sid, "playmat": {"asset_id": mat, "fit": "contain", "scale": 1.5}})
    assert res.status_code == 200, res.text
    view = client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": host}).json()
    mike_view = next(p for p in view["players"] if p["id"] == "p2")
    assert mike_view["sleeve"] == sid and mike_view["playmat"]["scale"] == 1.5
    assert view["game"]["assets"][sid]["url"].startswith(f"/api/assets/{sid}/file?v=")
    # the table playmat is the host's call
    assert act(mike, {"type": "set_table_playmat", "playmat": {"asset_id": mat}}).status_code == 403
    assert act(host, {"type": "set_table_playmat", "playmat": {"asset_id": mat}}).status_code == 200
    # deleting an asset in use warns (409) unless forced
    res = client.delete(f"/api/assets/{sid}")
    assert res.status_code == 409 and "Mike's sleeves" in res.json()["detail"]
    listed = {a["id"]: a for a in client.get("/api/assets").json()}
    assert listed[sid]["used_by"] and "used_by" not in remote.get("/api/assets").json()[0]
    assert client.delete(f"/api/assets/{sid}?force=true").status_code == 204
