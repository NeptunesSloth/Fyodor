"""The host secret: what makes a browser the host's, instead of where its connection comes from.

Behind a tunnel every remote player arrives from the loopback address, so "loopback means host" cannot stand. The host's own
browser is given this secret by the launcher (in the address it opens) and keeps it in a cookie (app/api/host.py); everyone
else has none. A new secret is made on every server start. The file only lets a separate launcher process read the current
one: it is created for its owner alone (mode 0o600; on Windows the user profile's own access rules are the protection)."""

from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path

HOST_COOKIE = "fyodor_host"
SECRET_FILE = "host.secret"


class HostSecret:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.value = secrets.token_urlsafe(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)  # (the mode below only applies to a new file: an older one with wider access must not stay)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(self.value)

    def matches(self, candidate: str | None) -> bool:
        if not candidate:
            return False
        return hmac.compare_digest(candidate.encode(), self.value.encode())


def read_host_secret(data_dir: Path) -> str | None:
    """The running server's secret, for a launcher that is not that server (None: no server has written one)."""
    try:
        return (data_dir / SECRET_FILE).read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None
