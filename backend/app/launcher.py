"""One-command start for the pod's host computer: ``python -m app.launcher``.

Checks the pieces a game night needs, starts the server, prints the address other devices use
and opens the browser. Everything is local; nothing here contacts the Internet.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from app.config import FROZEN, Settings, install_dir, load_settings


@dataclass
class Check:
    ok: bool
    label: str
    hint: str = ""


def lan_addresses() -> list[str]:
    found: set[str] = set()
    with contextlib.suppress(OSError), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))  # no packet is sent; this just picks the LAN interface
        found.add(s.getsockname()[0])
    with contextlib.suppress(OSError):
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(str(info[4][0]))
    return sorted(a for a in found if not a.startswith("127."))


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            return False
    return True


def preflight(settings: Settings) -> list[Check]:
    from app.cards.images import ImageStore
    from app.cards.repository import CardRepository

    checks = [Check(sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}", "Fyodor needs Python 3.11 or newer")]
    try:
        settings.ensure_dirs()
        probe = settings.data_dir / ".write-test"
        probe.write_text("ok")
        probe.unlink()
        checks.append(Check(True, f"Data folder {settings.data_dir}"))
    except OSError as exc:
        checks.append(Check(False, f"Data folder {settings.data_dir}", f"not writable: {exc}"))
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    try:
        stats = repo.stats()
    finally:
        repo.close()
    if stats["available"]:
        checks.append(Check(True, f"Card database: {stats['oracle_cards']:,} cards"))
    else:
        checks.append(Check(False, "Card database missing",
                            "download it once while online: Settings → Card database (games can't resolve decks without it)"))
    checks.append(Check(settings.frontend_dist is not None, "Table interface built",
                        "run: (cd frontend && npm install && npm run build)"))
    checks.append(Check(port_free(settings.host, settings.port), f"Port {settings.port} is free",
                        "another program (or Fyodor already) is using it; pass --port or stop the other one"))
    return checks


def _install_dir() -> Path:
    """Where Fyodor is installed: beside Fyodor.exe (the installer's browser/ and seed/ folders sit there)."""
    return install_dir()


def _windows_major() -> int:
    """10 for Windows 10 and 11, 6 for 8.1 (and 7, 8); 0 off Windows."""
    get = getattr(sys, "getwindowsversion", None)
    return int(get().major) if get else 0


def bundled_browser() -> Path | None:
    """Fyodor's own window: the Chromium the Windows installer ships, so an old, un-updatable system browser
    (an offline computer's Edge) is never in the way. Current Chromium needs Windows 10; on 8.1 the installer's
    Chromium 109 (the last for 8.1) is used instead. None when there isn't one (a source checkout)."""
    root = _install_dir()
    current, legacy = root / "browser" / "chrome.exe", root / "browser-legacy" / "chrome.exe"
    order = [legacy, current] if 0 < _windows_major() < 10 else [current, legacy]
    return next((exe for exe in order if exe.is_file()), None)


def seed_card_database(settings: Settings) -> bool:
    """The first start on a computer with no card database: copy in the one the installer carries. True if it did."""
    seed = _install_dir() / "seed" / "cards.sqlite"
    if settings.cards_db_path.exists() or not seed.is_file():
        return False
    settings.ensure_dirs()
    part = settings.cards_db_path.with_suffix(".sqlite.part")
    shutil.copyfile(seed, part)  # (a half-copied file never looks like a database: renamed only once whole)
    part.replace(settings.cards_db_path)
    return True


def _running_fyodor(url: str) -> bool:
    """Is a Fyodor already serving here? (Opening it twice brings the table back instead of failing on the port.)"""
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=1.5) as r:  # noqa: S310 - our own local server
            return b'"status"' in r.read(400)
    except OSError:
        return False


PAGE_SEEN = threading.Event()  # set when a window has asked this server for the table's page (serve() watches)
WINDOW_WAIT = 45.0  # seconds before the console says what to do if the window still shows nothing
MODERN = 111  # Chrome/Edge from this version draw everything the table uses


def _browser_version(exe: Path) -> int:
    """The major version of an installed Chrome or Edge: its Application folder holds a folder per version."""
    majors = [int(d.name.split(".")[0]) for d in exe.parent.iterdir() if d.is_dir() and d.name.count(".") == 3 and d.name.split(".")[0].isdigit()] \
        if exe.parent.is_dir() else []
    return max(majors, default=0)


def installed_browsers() -> list[tuple[str, Path]]:
    """Chrome and Edge already on this Windows computer, new enough for the table (signed and kept up to date by
    their makers, so security software trusts them). An old one, like an offline computer's Edge, is skipped."""
    if os.name != "nt":
        return []
    env = os.environ
    roots = [env.get("PROGRAMFILES", r"C:\Program Files"), env.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), env.get("LOCALAPPDATA", "")]
    found: list[tuple[str, Path]] = []
    for name, rel in (("Chrome", r"Google\Chrome\Application\chrome.exe"), ("Edge", r"Microsoft\Edge\Application\msedge.exe")):
        for root in roots:
            exe = Path(root) / rel if root else None
            if exe is not None and exe.is_file() and _browser_version(exe) >= MODERN:
                found.append((name, exe))
                break
    return found


def windows_to_try() -> list[tuple[str, Path]]:
    """In order: an up-to-date Chrome or Edge on this computer, then the Chromium the installer ships."""
    own = bundled_browser()
    return installed_browsers() + ([("Fyodor's own window", own)] if own else [])


# what a window's profile keeps of the page between starts (Chromium's layout under the profile folder)
_PAGE_CACHES = ("Cache", "Code Cache", "GPUCache", "Service Worker")


def forget_old_page(profile: Path, settings: Settings) -> bool:
    """A window kept from an older build could open that build's page against this server (its saved copy, sent before
    the page was served no-cache): when the built page differs from the one this profile last opened, its caches go.
    Returns whether they were cleared. Logins, settings and anything else in the profile stay."""
    dist = settings.frontend_dist
    index = dist / "index.html" if dist is not None else None
    if index is None or not index.is_file():
        return False
    stamp = profile / "fyodor-page"
    page = index.read_bytes()
    with contextlib.suppress(OSError):
        if stamp.read_bytes() == page:
            return False
    cleared = False
    for root in (profile, profile / "Default"):
        for name in _PAGE_CACHES:
            target = root / name
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
                cleared = True
    with contextlib.suppress(OSError):
        profile.mkdir(parents=True, exist_ok=True)
        stamp.write_bytes(page)
    return cleared


def _launch(name: str, exe: Path, url: str, settings: Settings) -> subprocess.Popen[bytes] | None:
    own = name.startswith("Fyodor")
    profile = settings.data_dir / ("window" if own else f"window-{name.lower()}")  # its own profile
    forget_old_page(profile, settings)
    # Chromium's network service runs in an AppContainer, which can only read a program folder that grants
    # ALL APPLICATION PACKAGES (Program Files does). A portable copy unpacked under the user's profile
    # (Desktop, Downloads) doesn't: the network service dies and the window never asks for the page.
    # Fyodor's own window only opens this computer's server, so it runs that service unboxed.
    features = "Translate,MediaRouter" + (",NetworkServiceSandbox" if own else "")
    try:
        return subprocess.Popen(  # noqa: S603 - a browser opening our own local address
            [str(exe), f"--app={url}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
             "--disable-background-networking", "--disable-component-update", "--disable-sync",
             f"--disable-features={features}", "--enable-unsafe-swiftshader",  # 3D even without a graphics driver
             "--enable-logging", f"--log-file={profile / 'browser.log'}",  # why, if it ever shows nothing
             "--start-maximized"],
            close_fds=True,
        )
    except OSError as exc:
        print(f"  ({name} would not start: {exc})")
        return None


def open_table(url: str, settings: Settings, watch: bool = False) -> None:
    """The table in a window of its own (the first of windows_to_try that starts), else the default browser. With
    ``watch`` (this program is the server), a window that hasn't asked for the page after WINDOW_WAIT seconds gets a
    note in this console. It isn't closed: a first start can be slow while security software scans the browser."""
    for name, exe in windows_to_try():
        if _launch(name, exe, url, settings) is None:
            continue
        if watch and not PAGE_SEEN.wait(WINDOW_WAIT):
            log = settings.data_dir / ("window" if name.startswith("Fyodor") else f"window-{name.lower()}") / "browser.log"
            print(f"\n  The table hasn't appeared in {name} yet. A first start can take a minute. If it stays empty, close"
                  f" the window and open Fyodor again, or open {url} in any up-to-date browser. (Its log: {log})\n")
        return
    webbrowser.open(url)


def _open_when_ready(url: str, settings: Settings) -> None:
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1):  # noqa: S310 - our own local server
                break
        except OSError:
            time.sleep(0.2)
    open_table(url, settings, watch=True)


def main(argv: list[str] | None = None) -> int:
    # Windows writes redirected output (`Fyodor.exe --check > out.txt`) in its ANSI code page, which has no ✓/✗/—:
    # print a stand-in for what it can't encode rather than crash the checks
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(prog="fyodor", description="Start the Fyodor table on this computer.")
    # game night is a pod on one network: other devices may join unless --local says otherwise
    parser.add_argument("--local", action="store_true", help="only this computer can connect")
    parser.add_argument("--lan", action="store_true", help=argparse.SUPPRESS)  # the default now; kept for old shortcuts
    parser.add_argument("--port", type=int, default=None, help="port to listen on (default 8000)")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    parser.add_argument("--check", action="store_true", help="only run the checks and exit")
    args = parser.parse_args(argv)

    env = dict(os.environ)
    args.lan = not args.local
    if args.lan:
        env["FYODOR_HOST"] = "0.0.0.0"  # noqa: S104 - explicit opt-in for LAN play
    if args.port is not None:  # --port 0: any free port (the tests use it so a busy 8000 never matters)
        env["FYODOR_PORT"] = str(args.port)
    settings = load_settings(env)

    local = f"http://127.0.0.1:{settings.port}"
    if not args.check and _running_fyodor(local):
        print("Fyodor is already running on this computer: opening the table.")
        if not args.no_browser:
            open_table(local, settings)
        return 0

    print("Fyodor — checking this computer\n")
    if not args.check and seed_card_database(settings):
        print("  First start: the card database that came with Fyodor is now in place (no Internet needed).")
    checks = preflight(settings)
    if not args.check and any(c.label == "Card database missing" for c in checks):
        print("  First run: downloading the Magic card database (one time, needs Internet, about 80 MB)…")
        from tools.update_cards import main as update_cards

        with contextlib.suppress(Exception):  # offline: the check below explains what to do
            update_cards(["--images", "none", "--data-dir", str(settings.data_dir)])
        checks = preflight(settings)
    for c in checks:
        print(f"  {'✓' if c.ok else '✗'} {c.label}" + ("" if c.ok else f"\n      → {c.hint}"))
    blocking = [c for c in checks if not c.ok and not c.label.startswith("Card database")]
    if args.check:
        return 1 if blocking else 0
    if blocking:
        print("\nFix the items marked ✗ and run this again.")
        if FROZEN:  # double-clicked: keep the window open long enough to read why
            input("Press Enter to close.")
        return 1

    print(f"\nOpen the table on this computer: {local}")
    if args.lan:
        addrs = lan_addresses()
        if addrs:
            print("\n  Friends on your network open:  " + "  or  ".join(f"http://{a}:{settings.port}" for a in addrs))
            print("  (or send them the invite link shown in the lobby once you open a LAN table)")
            if settings.discovery:  # app/multiplayer/discovery.py
                print("  Friends running Fyodor on their own computer see your LAN tables under Play → Games on your network.")
            print()
        else:
            print("No network address found — are you connected to Wi-Fi/Ethernet?")
        app_name = "Fyodor" if FROZEN else "Python"  # the downloadable app runs as Fyodor(.exe)
        ports = f"TCP {settings.port}" + (f" and UDP {settings.discovery_port}" if settings.discovery else "")
        print(f"(If they can't connect, allow {app_name} through this computer's firewall for private networks: {ports}.)")
    else:
        print("Only this computer can connect (--local). Start without --local to let the rest of the pod join.")
    print("Press Ctrl+C to stop. Games are autosaved.\n")

    if not args.no_browser:
        threading.Thread(target=_open_when_ready, args=(local, settings), daemon=True).start()

    serve(settings)
    return 0


def serve(settings: Settings) -> None:
    """Run the server; Settings → Restart (after a restore) stops it and starts it again here, in the same program,
    which is when a staged restore is applied (app/storage/backup.py)."""
    import uvicorn

    from app.main import create_app

    while True:
        again = threading.Event()
        app = create_app(settings)
        server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower()))

        def request_restart(server: uvicorn.Server = server, again: threading.Event = again) -> None:
            again.set()
            server.should_exit = True

        app.state.request_restart = request_restart

        @app.middleware("http")
        async def note_the_page(request, call_next):  # type: ignore[no-untyped-def]
            if request.url.path == "/" or request.url.path.startswith("/assets/"):
                PAGE_SEEN.set()  # a window asked for the table (open_table watches for this)
            return await call_next(request)

        server.run()
        if not again.is_set():
            return
        print("\nRestarting Fyodor…\n")


if __name__ == "__main__":
    raise SystemExit(main())
