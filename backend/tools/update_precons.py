"""Refresh the bundled Commander precon decklists (``app/decks/precons.json``) from MTGJSON.

    python -m tools.update_precons

Run by hand when new precons come out; the app itself never goes online for them. Each deck is stored as a plain
decklist (the same text the deck importer reads), with exact printings, so the pod can add any precon offline.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

BASE = "https://mtgjson.com/api/v5"
OUT = Path(__file__).resolve().parents[1] / "app" / "decks" / "precons.json"


def _get(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Fyodor precon update"})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - fixed https host
        return json.load(r)["data"]


def _lines(cards: list[dict[str, Any]]) -> list[str]:
    return [f"{c['count']} {c['name']} ({c['setCode']}) {c['number']}" for c in cards]


def decklist(deck: dict[str, Any]) -> str:
    return "\n".join(["Commander", *_lines(deck["commander"]), "", "Deck", *_lines(deck["mainBoard"])])


def main() -> int:
    # (a Collector's Edition is the same list in foil: left out)
    listing = [d for d in _get(f"{BASE}/DeckList.json") if d["type"] == "Commander Deck" and "Collector's Edition" not in d["name"]]
    out = []
    for i, d in enumerate(sorted(listing, key=lambda d: (d["releaseDate"], d["name"]))):
        deck = _get(f"{BASE}/decks/{d['fileName']}.json")
        if not deck.get("commander"):
            continue
        out.append({"id": d["fileName"], "name": d["name"], "set": d["code"], "released": d["releaseDate"],
                    "commanders": [c["name"] for c in deck["commander"]], "text": decklist(deck)})
        print(f"{i + 1}/{len(listing)} {d['name']}", file=sys.stderr)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), "utf-8")
    print(f"{len(out)} precons -> {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
