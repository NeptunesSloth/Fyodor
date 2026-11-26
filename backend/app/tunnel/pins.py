"""The cloudflared release Fyodor uses, pinned by version and SHA-256. Nothing is recorded at run time; to change the version, redo
the by-hand check (docs/superpowers/specs/2026-11-25-stage2-audit.md, Provider verification) and edit this file."""

from __future__ import annotations

from dataclasses import dataclass

CLOUDFLARED_VERSION = "2026.10.7"


@dataclass(frozen=True)
class Asset:
    """``sha256``: the downloaded file (the .tgz itself for an archive). ``binary_sha256``: the executable (equal to ``sha256``
    unless ``archive``, then the hash of the ``cloudflared`` member)."""

    name: str
    sha256: str
    archive: bool
    binary_sha256: str


_WINDOWS = Asset(
    "cloudflared-windows-amd64.exe",
    "2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343",
    False,
    "2493dbc168923bb3e59e5e7716f71deced92992eea9acd6e9d74f84ac7751343",
)

# macOS: GitHub's digest is that of the .tgz (the bytes downloaded); the release notes list the hash of the extracted executable.
ASSETS: dict[tuple[str, str], Asset] = {
    ("windows", "amd64"): _WINDOWS,
    ("windows", "arm64"): _WINDOWS,
    ("darwin", "amd64"): Asset(
        "cloudflared-darwin-amd64.tgz",
        "02f3edfd87684dd5b705607688e4eb4b323f6e777b81e7b3a85af556aa356848",
        True,
        "5c55e77da7012cebca19170357e196176c48c9647cc2ead404702fa125ddbd86",
    ),
    ("darwin", "arm64"): Asset(
        "cloudflared-darwin-arm64.tgz",
        "3586ccf397e98e5f437e60e7c307ca6ac463e110580503af8bb8e6f9ebf831bd",
        True,
        "2136431d5eb467bf447d2ee514b713e192719b143aec1d9e09bf7dc290d5bb12",
    ),
    ("linux", "amd64"): Asset(
        "cloudflared-linux-amd64",
        "1f99fb518b83dec2ba8d870a7cc991d82a77e6196295a3d2754ba17ab9f91872",
        False,
        "1f99fb518b83dec2ba8d870a7cc991d82a77e6196295a3d2754ba17ab9f91872",
    ),
    ("linux", "arm64"): Asset(
        "cloudflared-linux-arm64",
        "3df43aedc9ff291d1735b5cb576cb97e0b157488796db2e32b28aecabb445775",
        False,
        "3df43aedc9ff291d1735b5cb576cb97e0b157488796db2e32b28aecabb445775",
    ),
}

_MACHINES = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


def normalise_machine(machine: str) -> str:
    m = machine.lower()
    return _MACHINES.get(m, m)


def release_url(asset: Asset) -> str:
    return f"https://github.com/cloudflare/cloudflared/releases/download/{CLOUDFLARED_VERSION}/{asset.name}"
