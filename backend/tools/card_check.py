"""Oracle text, coverage level and unsupported lines of named cards, capped (development tool).

    python -m tools.card_check --db ../data/cards.sqlite "Card Name" ["Other Card" ...]
    python -m tools.card_check --db ../data/cards.sqlite --list names.txt      # one name per line: the ones not FULL, then a count
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.config import load_settings
from app.rules import commander, coverage
from tools.commander_coverage import rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path)
    ap.add_argument("--list", type=Path, help="file of card names; prints only the ones not FULL, then a count")
    ap.add_argument("names", nargs="*")
    args = ap.parse_args(argv)
    order = args.list.read_text("utf-8").splitlines() if args.list else args.names
    wanted = {n.strip() for n in order if n.strip()}
    by = {d["name"]: d for d in rows(args.db or load_settings().cards_db_path)[0]
          if d["name"] in wanted and commander.legality(d) == "legal"}
    full = 0
    for name in order:
        d = by.get(name.strip())
        if d is None:
            continue
        cov = coverage.of_card_data(d)
        full += cov.level == "FULL"
        if args.list and cov.level == "FULL":
            continue
        print(f"== {cov.level} {d['name']}")
        if not args.list:
            print((d.get("oracle_text") or " // ".join(f.get("oracle_text", "") for f in d["faces"]))[:1200])
        for f in cov.features:
            if not f.supported:
                print("  - " + f.label.replace("\n", " ")[:300])
    if args.list:
        print(f"\n{full}/{len(by)} FULL, {len(by) - full} still not FULL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
