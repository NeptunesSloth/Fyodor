"""The cloudflared release Fyodor uses, pinned by version and SHA-256. Nothing is recorded at run time; to change the version, redo
the by-hand check (docs/superpowers/specs/2026-11-25-stage2-audit.md, Provider verification) and edit this file."""

from __future__ import annotations

from dataclasses import dataclass

CLOUDFLARED_VERSION = "2026.11.2"


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
    "555b46c85582461d189cac30d14ad05480d612613801be9f110b8ce08c5b2113",
    False,
    "555b46c85582461d189cac30d14ad05480d612613801be9f110b8ce08c5b2113",
)

# macOS: GitHub's digest is that of the .tgz (the bytes downloaded); the release notes list the hash of the extracted executable.
ASSETS: dict[tuple[str, str], Asset] = {
    ("windows", "amd64"): _WINDOWS,
    ("windows", "arm64"): _WINDOWS,
    ("darwin", "amd64"): Asset(
        "cloudflared-darwin-amd64.tgz",
        "6153d9ec629174882a3adbff2f7dc5a24b4f3bdd7ccc38eaa84fba26eb890311",
        True,
        "870dc2094f98befdd993c455234562be4eee51f8fca6e2e356df4579fa7e6766",
    ),
    ("darwin", "arm64"): Asset(
        "cloudflared-darwin-arm64.tgz",
        "f6d58eeec91ad1ec5fd1f7e4a587303772929b2625be5d24068033851c36ff55",
        True,
        "8654fbdc9057f3e13e95f7892f417f8643113bee1b91ee2388fd0acb05210d55",
    ),
    ("linux", "amd64"): Asset(
        "cloudflared-linux-amd64",
        "56f13335143ec0e22772963290683a84a04114a35ec64cbc794a4d39ff9bb8cf",
        False,
        "56f13335143ec0e22772963290683a84a04114a35ec64cbc794a4d39ff9bb8cf",
    ),
    ("linux", "arm64"): Asset(
        "cloudflared-linux-arm64",
        "04a7b7f08bce85d56b26ffe1fdbfbb21a074495a363d16f0783c40e25b5c5281",
        False,
        "04a7b7f08bce85d56b26ffe1fdbfbb21a074495a363d16f0783c40e25b5c5281",
    ),
}

_MACHINES = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


def normalise_machine(machine: str) -> str:
    m = machine.lower()
    return _MACHINES.get(m, m)


def release_url(asset: Asset) -> str:
    return f"https://github.com/cloudflare/cloudflared/releases/download/{CLOUDFLARED_VERSION}/{asset.name}"
