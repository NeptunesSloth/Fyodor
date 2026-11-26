"""Application settings.

Settings come from environment variables prefixed with ``FYODOR_`` (a ``.env``
file in the working directory is also read). Every path is resolved relative to
the configured data directory, so no machine-specific path is hard-coded.
"""

from __future__ import annotations

import ipaddress
import os
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# the downloadable app (PyInstaller): the table interface ships inside the bundle, and cards and
# saves live in the player's home folder, which survives replacing the app with a newer one
FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    REPO_ROOT = Path(getattr(sys, "_MEIPASS", REPO_ROOT))
DATA_ROOT = Path.home() / "Fyodor" if FROZEN else REPO_ROOT


def install_dir() -> Path:
    """Where Fyodor is installed: beside Fyodor.exe (the installer's browser/ and seed/ folders sit there); dist/Fyodor in a checkout."""
    return Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[2] / "dist" / "Fyodor"


def bundled_images() -> Path | None:
    """-- offline token art -- the card pictures the installer carries (seed/images: every token's art), read in place; None without."""
    path = install_dir() / "seed" / "images"
    return path if path.is_dir() else None


def _load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    frontend_dist: Path | None = None
    autosave_every: int = 10
    history_limit: int = 500
    assistant_url: str | None = None  # Ollama-compatible endpoint; unset = assistant disabled
    assistant_model: str = "llama3.1"
    allow_network: bool = True  # explicit, user-initiated online features (Archidekt import, art caching)
    auto_backup_minutes: int = 30  # automatic backups while something changed (0 = off); see app/storage/autobackup.py
    backup_copy_dir: Path | None = None  # a second folder every backup is copied to (USB stick, synced folder)
    dev_tools: bool = False  # developer tools such as EXPORT RULES SCENARIO (FYODOR_DEV_TOOLS=1)
    # finding tables on the network (app/multiplayer/discovery.py): answer on this UDP port in LAN mode, and search from the
    # Play page; FYODOR_DISCOVERY=0 does neither
    discovery: bool = True
    discovery_port: int = 47474
    scryfall_api: str = "https://api.scryfall.com"
    user_agent: str = "Fyodor-MTG-Tabletop/0.1"
    # -- art folders -- more folders of card pictures, read in place after the cache (app/cards/art_folders.py)
    art_dirs: tuple[Path, ...] = ()
    # reverse proxies / tunnels whose X-Forwarded-For is believed (IPs or CIDRs, FYODOR_TRUSTED_PROXIES); none by default, so the
    # header is ignored (app/api/deps.py client_address)
    trusted_proxies: tuple[str, ...] = ()
    # host names (besides IP addresses, localhost and this computer's name) this server answers to, lower-case, no ports
    # (FYODOR_EXTRA_HOSTS); see app/netguard.py
    extra_hosts: tuple[str, ...] = ()
    # the game socket's seat token in the query string (old clients; it ends up in URLs and logs): only FYODOR_LEGACY_WS_TOKEN=1
    legacy_ws_token: bool = False
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def cards_db_path(self) -> Path:
        return self.data_dir / "cards.sqlite"

    @property
    def app_db_path(self) -> Path:
        return self.data_dir / "app.sqlite"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def downloads_dir(self) -> Path:
        return self.data_dir / "downloads"

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.images_dir / "cards", self.images_dir / "tokens", self.downloads_dir, self.assets_dir):
            path.mkdir(parents=True, exist_ok=True)


def _proxies(value: str | None) -> tuple[str, ...]:
    entries = tuple(e.strip() for e in (value or "").split(",") if e.strip())
    for entry in entries:
        try:
            ipaddress.ip_network(entry, strict=False)
        except ValueError:
            raise ValueError(f"FYODOR_TRUSTED_PROXIES: {entry!r} is not an IP address or CIDR range") from None
    return entries


def _extra_hosts(value: str | None) -> tuple[str, ...]:
    """FYODOR_EXTRA_HOSTS: comma-separated bare host names or IP literals (no port, scheme, path or space), lower-cased. Empty entries
    (a trailing comma) are skipped, as in FYODOR_TRUSTED_PROXIES."""
    entries = tuple(e.strip().lower() for e in (value or "").split(",") if e.strip())
    for entry in entries:
        if ":" in entry or "/" in entry or any(c.isspace() for c in entry):
            raise ValueError(f"FYODOR_EXTRA_HOSTS: {entry!r} is not a bare host name or IP address (no port, scheme, path or space)")
    return entries


def load_settings(env: dict[str, str] | None = None) -> Settings:
    source: dict[str, str] = {}
    source.update(_load_dotenv(Path.cwd() / ".env"))
    source.update(os.environ if env is None else env)

    def get(name: str) -> str | None:
        return source.get(f"FYODOR_{name}")

    data_dir = Path(get("DATA_DIR") or (DATA_ROOT / "data")).expanduser().resolve()
    dist = get("FRONTEND_DIST")
    frontend_dist = Path(dist).expanduser().resolve() if dist else REPO_ROOT / "frontend" / "dist"
    cors = get("CORS_ORIGINS")
    return Settings(
        data_dir=data_dir,
        host=get("HOST") or "127.0.0.1",
        port=int(get("PORT") or 8000),
        log_level=(get("LOG_LEVEL") or "INFO").upper(),
        cors_origins=tuple(o.strip() for o in cors.split(",") if o.strip())
        if cors
        else Settings.__dataclass_fields__["cors_origins"].default,  # type: ignore[arg-type]
        frontend_dist=frontend_dist if frontend_dist.is_dir() else None,
        autosave_every=int(get("AUTOSAVE_EVERY") or 10),
        history_limit=int(get("HISTORY_LIMIT") or 500),
        assistant_url=get("ASSISTANT_URL") or None,
        assistant_model=get("ASSISTANT_MODEL") or "llama3.1",
        allow_network=_bool(get("ALLOW_NETWORK"), True),
        auto_backup_minutes=int(get("AUTO_BACKUP_MINUTES") or 30),
        backup_copy_dir=Path(copy_dir).expanduser().resolve() if (copy_dir := get("BACKUP_COPY_DIR")) else None,
        dev_tools=_bool(get("DEV_TOOLS"), False),
        discovery=_bool(get("DISCOVERY"), True),
        discovery_port=int(get("DISCOVERY_PORT") or 47474),
        trusted_proxies=_proxies(get("TRUSTED_PROXIES")),
        legacy_ws_token=get("LEGACY_WS_TOKEN") == "1",
        extra_hosts=_extra_hosts(get("EXTRA_HOSTS")),
        art_dirs=tuple(Path(d.strip().strip('"')).expanduser() for d in (get("ART_DIRS") or "").split(os.pathsep) if d.strip()),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
