"""The pinned cloudflared download (app/tunnel/binary.py, pins.py). No network: httpx.MockTransport."""

from __future__ import annotations

import hashlib
import io
import re
import tarfile

import httpx
import pytest

from app.tunnel import binary, pins
from app.tunnel.binary import TunnelUnavailable

PAYLOAD = b"#!fake cloudflared\n" * 50


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_client(handler):
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    return (lambda **kw: httpx.Client(transport=httpx.MockTransport(respond), **kw)), calls


def never(request):
    pytest.fail("network used")


def direct_asset(monkeypatch, data: bytes = PAYLOAD, key=("linux", "amd64")) -> pins.Asset:
    asset = pins.Asset("cloudflared-linux-amd64", sha(data), False, sha(data))
    monkeypatch.setitem(pins.ASSETS, key, asset)
    return asset


def tgz(name: str, content: bytes, symlink: bool = False) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name)
        if symlink:
            info.type = tarfile.SYMTYPE
            info.linkname = "elsewhere"
            tar.addfile(info)
        else:
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def ok(body: bytes):
    return lambda request: httpx.Response(200, content=body)


def test_existing_verified_binary_needs_no_network(tmp_path, monkeypatch):
    asset = direct_asset(monkeypatch)
    target = tmp_path / f"cloudflared-{pins.CLOUDFLARED_VERSION}"
    target.write_bytes(PAYLOAD)
    client, calls = make_client(never)
    assert (
        binary.ensure_binary(tmp_path, client, allow_network=False, system="linux", machine="x86_64")
        == target
    )
    assert not calls and binary.verify(target, asset)


def test_download_is_verified_and_renamed(tmp_path, monkeypatch):
    direct_asset(monkeypatch)
    client, calls = make_client(ok(PAYLOAD))
    path = binary.ensure_binary(tmp_path, client, allow_network=True, system="Linux", machine="x86_64")
    assert path == tmp_path / f"cloudflared-{pins.CLOUDFLARED_VERSION}"
    assert path.read_bytes() == PAYLOAD
    assert [p.name for p in tmp_path.iterdir()] == [path.name]
    assert str(calls[0].url) == pins.release_url(pins.ASSETS[("linux", "amd64")])


def test_windows_name_has_exe(tmp_path, monkeypatch):
    asset = pins.Asset("cloudflared-windows-amd64.exe", sha(PAYLOAD), False, sha(PAYLOAD))
    monkeypatch.setitem(pins.ASSETS, ("windows", "amd64"), asset)
    client, _ = make_client(ok(PAYLOAD))
    path = binary.ensure_binary(tmp_path, client, allow_network=True, system="Windows", machine="AMD64")
    assert path.name == f"cloudflared-{pins.CLOUDFLARED_VERSION}.exe"


def test_a_wrong_hash_leaves_nothing_and_raises(tmp_path, monkeypatch):
    direct_asset(monkeypatch)
    client, _ = make_client(ok(PAYLOAD + b"tampered"))
    with pytest.raises(TunnelUnavailable, match="didn't match the expected checksum"):
        binary.ensure_binary(tmp_path, client, allow_network=True, system="linux", machine="amd64")
    assert list(tmp_path.iterdir()) == []


def test_allow_network_false_never_downloads(tmp_path, monkeypatch):
    direct_asset(monkeypatch)
    client, calls = make_client(never)
    with pytest.raises(TunnelUnavailable, match=r"FYODOR_ALLOW_NETWORK=0"):
        binary.ensure_binary(tmp_path, client, allow_network=False, system="linux", machine="amd64")
    assert not calls and list(tmp_path.iterdir()) == []


def test_download_stops_at_the_size_cap(tmp_path, monkeypatch):
    direct_asset(monkeypatch)
    monkeypatch.setattr(binary, "MAX_DOWNLOAD_BYTES", 100)
    client, _ = make_client(ok(b"x" * 5000))
    with pytest.raises(TunnelUnavailable):
        binary.ensure_binary(tmp_path, client, allow_network=True, system="linux", machine="amd64")
    assert list(tmp_path.iterdir()) == []


def test_archive_is_extracted_and_both_hashes_checked(tmp_path, monkeypatch):
    archive = tgz("cloudflared", PAYLOAD)
    asset = pins.Asset("cloudflared-darwin-arm64.tgz", sha(archive), True, sha(PAYLOAD))
    monkeypatch.setitem(pins.ASSETS, ("darwin", "arm64"), asset)
    client, _ = make_client(ok(archive))
    path = binary.ensure_binary(tmp_path, client, allow_network=True, system="Darwin", machine="arm64")
    assert path.read_bytes() == PAYLOAD and path.name == f"cloudflared-{pins.CLOUDFLARED_VERSION}"
    assert [p.name for p in tmp_path.iterdir()] == [path.name]


def test_archive_whose_member_hash_differs_is_refused(tmp_path, monkeypatch):
    archive = tgz("cloudflared", PAYLOAD)
    asset = pins.Asset("cloudflared-darwin-arm64.tgz", sha(archive), True, sha(b"something else"))
    monkeypatch.setitem(pins.ASSETS, ("darwin", "arm64"), asset)
    client, _ = make_client(ok(archive))
    with pytest.raises(TunnelUnavailable, match="didn't match"):
        binary.ensure_binary(tmp_path, client, allow_network=True, system="darwin", machine="arm64")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "name,symlink", [("../cloudflared", False), ("bin/cloudflared", False), ("cloudflared", True)]
)
def test_archive_member_with_a_path_is_refused(tmp_path, monkeypatch, name, symlink):
    archive = tgz(name, PAYLOAD, symlink)
    asset = pins.Asset("cloudflared-darwin-arm64.tgz", sha(archive), True, sha(PAYLOAD))
    monkeypatch.setitem(pins.ASSETS, ("darwin", "arm64"), asset)
    client, _ = make_client(ok(archive))
    with pytest.raises(TunnelUnavailable):
        binary.ensure_binary(tmp_path, client, allow_network=True, system="darwin", machine="arm64")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "system,machine,name",
    [
        ("Windows", "AMD64", "cloudflared-windows-amd64.exe"),
        ("Windows", "ARM64", "cloudflared-windows-amd64.exe"),
        ("Darwin", "x86_64", "cloudflared-darwin-amd64.tgz"),
        ("Darwin", "arm64", "cloudflared-darwin-arm64.tgz"),
        ("Linux", "x86_64", "cloudflared-linux-amd64"),
        ("Linux", "aarch64", "cloudflared-linux-arm64"),
    ],
)
def test_platform_map(system, machine, name):
    assert binary.asset_for(system, machine).name == name


def test_unsupported_platform(tmp_path):
    assert binary.asset_for("freebsd", "amd64") is None
    client, calls = make_client(never)
    with pytest.raises(TunnelUnavailable, match="isn't available on this kind of computer"):
        binary.ensure_binary(tmp_path, client, allow_network=True, system="freebsd", machine="amd64")
    assert not calls


def test_a_replaced_binary_fails_verify(tmp_path, monkeypatch):
    asset = direct_asset(monkeypatch)
    target = tmp_path / f"cloudflared-{pins.CLOUDFLARED_VERSION}"
    target.write_bytes(PAYLOAD)
    assert binary.verify(target, asset)
    target.write_bytes(bytes([PAYLOAD[0] ^ 1]) + PAYLOAD[1:])
    assert not binary.verify(target, asset)
    client, calls = make_client(ok(PAYLOAD))
    assert (
        binary.ensure_binary(tmp_path, client, allow_network=True, system="linux", machine="amd64") == target
    )
    assert len(calls) == 1 and target.read_bytes() == PAYLOAD


def test_verify_missing_file_is_false(tmp_path, monkeypatch):
    assert not binary.verify(tmp_path / "nope", direct_asset(monkeypatch))


def test_pins_are_well_formed():
    assert re.fullmatch(r"\d{4}\.\d{1,2}\.\d+", pins.CLOUDFLARED_VERSION)
    assert set(pins.ASSETS) == {
        ("windows", "amd64"),
        ("windows", "arm64"),
        ("darwin", "amd64"),
        ("darwin", "arm64"),
        ("linux", "amd64"),
        ("linux", "arm64"),
    }
    for asset in pins.ASSETS.values():
        assert re.fullmatch(r"[0-9a-f]{64}", asset.sha256) and re.fullmatch(
            r"[0-9a-f]{64}", asset.binary_sha256
        )
        assert pins.release_url(asset).startswith(
            "https://github.com/cloudflare/cloudflared/releases/download/"
        )
        assert asset.archive == asset.name.endswith(".tgz")
        assert asset.archive or asset.sha256 == asset.binary_sha256
