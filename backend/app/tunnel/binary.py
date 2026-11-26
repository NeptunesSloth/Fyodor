"""The pinned cloudflared executable: downloaded on first use from the official release, checked against SHA-256 hashes pinned in
the repo (pins.py), kept in the data folder, and checked again before every launch. Nothing downloaded is executed here."""

from __future__ import annotations

import hashlib
import hmac
import os
import platform
import shutil
import tarfile
from collections.abc import Callable
from pathlib import Path

import httpx

from app.tunnel import pins
from app.tunnel.pins import Asset

MAX_DOWNLOAD_BYTES = 150 * 1024 * 1024
_CHUNK = 1024 * 1024
_MEMBER = "cloudflared"


class TunnelUnavailable(Exception):
    """The invite link can't be used; the message is for the host."""


def asset_for(system: str, machine: str) -> Asset | None:
    return pins.ASSETS.get((system.lower(), pins.normalise_machine(machine)))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def verify(path: Path, asset: Asset) -> bool:
    """The file at ``path`` is the pinned executable (its SHA-256 equals ``asset.binary_sha256``)."""
    try:
        return hmac.compare_digest(_sha256(path), asset.binary_sha256)
    except OSError:
        return False


def _discard(*paths: Path) -> None:
    for p in paths:
        p.unlink(missing_ok=True)


def _download(client: Callable[..., httpx.Client], asset: Asset, part: Path) -> None:
    try:
        with client(follow_redirects=True) as c, c.stream("GET", pins.release_url(asset)) as response:
            response.raise_for_status()
            size = 0
            with part.open("wb") as out:
                for chunk in response.iter_bytes(_CHUNK):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        raise TunnelUnavailable(
                            "The tunnel program download was larger than expected, so it was stopped."
                        )
                    out.write(chunk)
    except httpx.HTTPError as exc:
        raise TunnelUnavailable(
            "The tunnel program couldn't be downloaded. Check the internet connection and try again."
        ) from exc


def _extract(archive: Path, dest: Path) -> None:
    try:
        with tarfile.open(archive, "r:gz") as tar:
            member = next((m for m in tar.getmembers() if m.name == _MEMBER and m.isreg()), None)
            source = tar.extractfile(member) if member else None
            if source is None:
                raise TunnelUnavailable(
                    "The downloaded tunnel program wasn't packaged as expected, so it wasn't used."
                )
            with source, dest.open("wb") as out:
                shutil.copyfileobj(source, out)
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise TunnelUnavailable(
            "The downloaded tunnel program couldn't be unpacked, so it wasn't used."
        ) from exc
    dest.chmod(0o755)


def ensure_binary(
    folder: Path,
    client: Callable[..., httpx.Client],
    *,
    allow_network: bool,
    system: str | None = None,
    machine: str | None = None,
) -> Path:
    """The verified cloudflared executable in ``folder``, downloading it first if it isn't there (or isn't the pinned file)."""
    system = (system or platform.system()).lower()
    asset = asset_for(system, machine or platform.machine())
    target = folder / f"cloudflared-{pins.CLOUDFLARED_VERSION}{'.exe' if system == 'windows' else ''}"
    if asset is not None and target.is_file() and verify(target, asset):
        return target
    if not allow_network:
        raise TunnelUnavailable("Internet features are turned off on this computer (FYODOR_ALLOW_NETWORK=0).")
    if asset is None:
        raise TunnelUnavailable("Sharing over the internet isn't available on this kind of computer.")

    folder.mkdir(parents=True, exist_ok=True)
    download = folder / f"{asset.name}.part"
    unpacked = folder / f"{target.name}.part"
    _discard(download, unpacked)
    try:
        _download(client, asset, download)
        if not hmac.compare_digest(_sha256(download), asset.sha256):
            raise TunnelUnavailable(
                "The downloaded tunnel program didn't match the expected checksum, so it wasn't used."
            )
        if asset.archive:
            _extract(download, unpacked)
            if not verify(unpacked, asset):
                raise TunnelUnavailable(
                    "The downloaded tunnel program didn't match the expected checksum, so it wasn't used."
                )
            ready = unpacked
        else:
            download.chmod(0o755)
            ready = download
        os.replace(ready, target)
    finally:
        _discard(download, unpacked)
    return target
