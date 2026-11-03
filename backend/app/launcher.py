"""One-command start for the pod's host computer: ``python -m app.launcher``.

Checks the pieces a game night needs, starts the server, prints the address other devices use
and opens the browser. Everything is local; nothing here contacts the Internet.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass

from app.config import FROZEN, Settings, load_settings


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


def _open_when_ready(url: str) -> None:
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1):  # noqa: S310 - our own local server
                break
        except OSError:
            time.sleep(0.2)
    webbrowser.open(url)


def main(argv: list[str] | None = None) -> int:
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
    if args.port:
        env["FYODOR_PORT"] = str(args.port)
    settings = load_settings(env)

    print("Fyodor — checking this computer\n")
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

    local = f"http://127.0.0.1:{settings.port}"
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
        threading.Thread(target=_open_when_ready, args=(local,), daemon=True).start()

    import uvicorn

    from app.main import create_app

    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level=settings.log_level.lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
