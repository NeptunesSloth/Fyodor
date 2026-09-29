"""Commander rules coverage across the whole Commander-legal card pool (development tool).

    python -m tools.commander_coverage                      # the card DB in the data dir
    python -m tools.commander_coverage --db path/cards.sqlite

Writes ``data/reports/commander_rules_coverage.{md,json}``, ``commander_coverage.md`` and
``mechanics.md``. If a pod inventory exists (``python -m tools.rules_inventory``), pod cards and
pod commanders go to the front of the missing-feature queue. Offline: it reads the local card
database and the stored Comprehensive Rules only.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from app.config import load_settings
from app.rules import analysis, coverage, pool
from app.rules.engine import RULES_ENGINE_VERSION
from app.rules.research import current_version
from tools.rules_research import cr as crmod
from tools.rules_research.store import REPORTS_DIR, latest_text


def rows(db_path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    out = []
    # One entry per Oracle card: the default printing.
    for r in db.execute("SELECT p.* FROM printings p JOIN oracle_defaults d ON d.printing_id = p.id WHERE p.is_token = 0"):
        d = dict(r)
        for key in ("colors", "color_identity", "keywords"):
            d[key] = json.loads(d[key] or "[]")
        d["faces"] = json.loads(d.pop("card_faces") or "null") or []
        d["legalities"] = json.loads(d["legalities"] or "{}")
        out.append(d)
    meta = {k: v for k, v in db.execute("SELECT key, value FROM meta")}
    db.close()
    return out, meta


def pod_ids(reports: Path) -> tuple[set[str], set[str]]:
    path = reports / "rules_inventory.json"
    if not path.is_file():
        return set(), set()
    inv = json.loads(path.read_text("utf-8"))
    return {c["oracle_id"] for c in inv.get("cards", [])}, set(inv.get("commander_oracle_ids", []))


def mechanics(cr_text: str | None, keyword_cards: dict[str, int], reports_dir: Path) -> str:
    lines = ["# Mechanics (Comprehensive Rules 701 keyword actions / 702 keyword abilities)", ""]
    if cr_text is None:
        return "\n".join([*lines, "No stored rules: run python -m tools.rules_research.update", ""])
    rules = crmod.parse(cr_text)
    lines += [f"Rules effective {rules.effective}. Card counts: Commander-legal cards whose Oracle keywords list it.", "",
              "| Rule | Mechanic | Kind | Commander cards | Status |", "|---|---|---|---|---|"]
    known_actions = set(analysis.KEYWORD_ACTIONS)
    missing_actions = []
    for num, rule in rules.rules.items():
        if num[:3] not in ("701", "702") or num.count(".") != 1 or num[-1].isalpha() or num in ("701.1", "702.1"):
            continue
        name = rule.text.split("\n")[0].strip()
        low = name.lower()
        kind = "keyword action" if num.startswith("701") else "keyword ability"
        count = keyword_cards.get(low, 0)
        status = "supported" if low in coverage.SUPPORTED_KEYWORDS else ("—" if count == 0 else "missing")
        if count == 0 and status != "supported":
            status = "ignore (no Commander-legal cards)"
        if num.startswith("701") and low not in known_actions:
            missing_actions.append(name)
        lines.append(f"| {num} | {name} | {kind} | {count} | {status} |")
    if missing_actions:
        lines += ["", "Keyword actions in the rules that `app/rules/analysis.KEYWORD_ACTIONS` doesn't list yet: "
                  + ", ".join(missing_actions)]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, help="card database (default: the data dir's cards.sqlite)")
    parser.add_argument("--out", type=Path, default=REPORTS_DIR)
    args = parser.parse_args(argv)
    db = args.db or load_settings().cards_db_path
    cards, meta = rows(db)
    pod, pod_cmdrs = pod_ids(args.out)
    rep = pool.analyse(cards, pod_oracle_ids=pod, pod_commander_ids=pod_cmdrs)
    data = pool.as_json(rep, {
        "generated_at": time.strftime("%Y-%m-%d %H:%M"), "card_data": meta.get("bulk_updated_at") or meta.get("source"),
        "comprehensive_rules": current_version(), "rules_engine_version": RULES_ENGINE_VERSION,
    })
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "commander_rules_coverage.json").write_text(json.dumps(data, indent=1), "utf-8")
    (args.out / "commander_rules_coverage.md").write_text(pool.markdown(data), "utf-8")
    (args.out / "commander_coverage.md").write_text(pool.commander_markdown(data), "utf-8")
    (args.out / "mechanics.md").write_text(mechanics(latest_text(), dict(rep.keyword_cards), args.out), "utf-8")
    lv = data["levels"]
    print(f"Commander-legal cards: {data['commander_legal_cards']} — " + ", ".join(f"{k} {v}" for k, v in lv.items()))
    print(f"Possible commanders: {data['possible_commanders']} — "
          + ", ".join(f"{k} {v}" for k, v in data["commander_levels"].items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
