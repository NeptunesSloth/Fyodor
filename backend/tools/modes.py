"""Per-mode coverage of modal cards (development tool; wave 24D, AUTOMATION_INVENTORY B-bucket #8).

    python -m tools.modes --db ../data/cards.sqlite --out modes.json [-j 3]

A modal card is carried out already (700.2, ``modal_abilities``); when it isn't FULL, the inventory only says "the modal line" — one
mode's wording holds all of its bullets back. This reads every non-FULL Commander-legal card with a "Choose … —" line and bullets,
rebuilds each mode ALONE (the header's trigger / cost words + the mode, or the mode as a spell line) and asks ``coverage`` about
that. The result lists the failing modes per card and the recurring failing mode wordings (digits and the card name normalised)."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from app.config import load_settings
from app.rules import commander, coverage
from tools.commander_coverage import rows

_HEADER = re.compile(r"^(?P<lead>.*?)\bchoose (?:one|two|three|any number|up to \w+|one or both|one or more)\b[^—\n]*—\s*$", re.IGNORECASE)


def modes_of(text: str) -> list[tuple[str, str]]:
    """[(lead words before "choose", mode text)] for each bullet of each modal line of ``text``."""
    out: list[tuple[str, str]] = []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        m = _HEADER.match(line.strip())
        if m is None:
            continue
        for follow in lines[i + 1:]:
            if not follow.startswith("•"):
                break
            out.append((m["lead"].strip(), follow.lstrip("• ").strip()))
    return out


def alone(data: dict[str, Any], lead: str, mode: str) -> dict[str, Any]:
    """The card with this one mode as its only text line (a trigger / cost lead keeps its words, "Whenever ~ attacks, draw a card.")."""
    text = f"{lead} {mode[:1].lower()}{mode[1:]}" if lead else mode
    return {**data, "id": f"{data.get('id')}#{text}", "oracle_text": text, "faces": [], "layout": "normal", "keywords": []}  # (the id keys a cache)


def card(data: dict[str, Any]) -> dict[str, Any] | None:
    if commander.legality(data) != "legal":
        return None
    texts = [str(data.get("oracle_text") or ""), *(str(f.get("oracle_text") or "") for f in data.get("faces") or [])]
    modes = [x for t in texts for x in modes_of(t)]
    if not modes or coverage.of_card_data(data).level == "FULL":
        return None
    name = str(data.get("name"))
    failing = []
    for lead, mode in modes:
        if coverage.of_card_data(alone(data, lead, mode)).level != "FULL":
            failing.append(mode)
    return {"name": name, "rank": int(data.get("edhrec_rank") or 10**9), "modes": len(modes), "failing": failing}


def normal(mode: str, name: str) -> str:
    return re.sub(r"\d+", "N", mode.replace(name, "~").replace(name.split(",")[0], "~"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("-j", type=int, default=3)
    args = ap.parse_args(argv)
    data, _ = rows(args.db or load_settings().cards_db_path)
    with ProcessPoolExecutor(args.j) as pool:
        cards = [c for c in pool.map(card, data, chunksize=128) if c is not None]
    cards.sort(key=lambda c: (c["rank"], c["name"]))
    recurring = Counter(normal(m, c["name"]) for c in cards for m in c["failing"])
    clean = sum(1 for c in cards if not c["failing"])
    report = {"cards": cards, "recurring": recurring.most_common(80), "no_failing_mode": clean}
    args.out.write_text(json.dumps(report, indent=1), "utf-8")
    print(f"{len(cards)} non-FULL modal cards; {clean} have no failing mode alone (held back by another line)")
    for text, n in recurring.most_common(40):
        print(f"{n:4d}  {text[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
