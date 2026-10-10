"""Automation inventory of every Commander-legal card (development tool).

    python -m tools.inventory --db ../data/cards.sqlite --out inventory.json [-j 3]

For each Commander-legal card: its coverage level (``coverage.of_card_data``), whether it can be a commander, and
for a non-FULL card EVERY unsupported feature line with its ``gap_rank`` family, whether it is only
"collateral" (a spell line whose own definition is automated, held back by another line of the spell), the refusal reason if the wording
is a known refusal (``coverage.refusal``) and whether the grammar produced a definition for it at all ("parsed":
the wording was classified, but its definition isn't automated; "unparsed": no definition).

The summary (also printed) has the level counts, commanders FULL, the Oracle-text classification rates over
ability lines (supported / parsed-but-unsupported / unparsed), single-blocker family counts (collateral lines ignored) and the most common
multi-blocker family combinations. The JSON is a working file: write it outside the repository.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from app.config import load_settings
from app.rules import commander, coverage
from app.rules import scripts as templates
from app.rules.characteristics import HALVES, Characteristics, half_from_data, printed_from_data
from tools.commander_coverage import rows
from tools.gap_rank import family_of


def _faces(data: dict[str, Any]) -> list[Characteristics]:
    faces = data.get("faces") or []
    if len(faces) > 1:
        halves = data.get("layout") in HALVES
        return [half_from_data(data, i) if halves else printed_from_data(data, i) for i in range(len(faces))]
    return [printed_from_data(data, 0)]


def _family(fid: str, label: str) -> str:
    """The gap_rank family of one unsupported feature (same rule as ``gap_rank.main``)."""
    if fid.startswith("keyword:"):
        return f"keyword:{label.lower()}"
    if fid.startswith(("text:", "script:", "mana:")):
        return family_of(label)
    return f"feature:{fid.split(':')[0]}"


def card(data: dict[str, Any]) -> dict[str, Any] | None:
    if commander.legality(data) != "legal":
        return None
    level = coverage.of_card_data(data).level
    lines = {"supported": 0, "parsed": 0, "unparsed": 0}
    missing: list[dict[str, Any]] = []
    for face, ch in enumerate(_faces(data)):
        defs = templates.definitions(ch)
        for f in coverage.of_characteristics(ch).features:
            is_line = f.id.startswith(("text:", "script:", "mana:", "keyword:"))
            d = defs.get(int(f.id[5:])) if f.id.startswith("text:") else None
            parsed = f.supported or d is not None
            if is_line:
                lines["supported" if f.supported else "parsed" if parsed else "unparsed"] += 1
            if not f.supported:
                # A spell is automated as a whole (coverage.features_of): a line whose own definition is
                # automated is held back only by another line of the spell ("collateral", not a blocker).
                collateral = (ch.is_instant_or_sorcery and d is not None and coverage.definition_supported(d)
                              and coverage.x_selector_ok(ch, d))
                missing.append({"id": f.id, "face": face, "text": f.label, "family": _family(f.id, f.label),
                                "parsed": parsed, "collateral": collateral, "refusal": coverage.refusal(f.label)})
    return {"name": str(data.get("name")), "rank": int(data.get("edhrec_rank") or 10**9), "level": level,
            "commander": commander.can_be_commander(data), "lines": lines, "missing": missing if level != "FULL" else []}


def summary(cards: list[dict[str, Any]], top: int = 30) -> dict[str, Any]:
    levels = Counter(c["level"] for c in cards)
    lines: Counter[str] = Counter()
    for c in cards:
        lines.update(c["lines"])
    total = sum(lines.values()) or 1
    sole: Counter[str] = Counter()
    sole_cmdr: Counter[str] = Counter()
    combos: Counter[str] = Counter()
    by_blockers: Counter[int] = Counter()
    for c in cards:
        blockers = [m for m in c["missing"] if not m["collateral"]] or c["missing"]
        fams = sorted({m["family"] for m in blockers})
        if not fams:
            continue
        by_blockers[len(blockers)] += 1
        if len(fams) == 1:
            sole[fams[0]] += 1
            sole_cmdr[fams[0]] += c["commander"]
        else:
            combos[" + ".join(fams)] += 1
    return {
        "cards": len(cards), "levels": dict(levels),
        "commanders": sum(c["commander"] for c in cards),
        "commanders_full": sum(c["commander"] and c["level"] == "FULL" for c in cards),
        "lines": dict(lines),
        "lines_pct": {k: round(100 * v / total, 2) for k, v in lines.items()},
        "classified_pct": round(100 * (lines["supported"] + lines["parsed"]) / total, 2),
        "collateral_lines": sum(m["collateral"] for c in cards for m in c["missing"]),
        "non_full_by_blocking_lines": dict(sorted(by_blockers.items())),
        "single_family": [{"family": f, "cards": n, "commanders": sole_cmdr[f]} for f, n in sole.most_common()],
        "multi_family_top": [{"families": k, "cards": n} for k, n in combos.most_common(top)],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("-j", type=int, default=3)
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args(argv)
    data, meta = rows(args.db or load_settings().cards_db_path)
    with ProcessPoolExecutor(args.j) as pool:
        cards = [c for c in pool.map(card, data, chunksize=256) if c is not None]
    cards.sort(key=lambda c: (c["rank"], c["name"]))
    report = {"meta": meta, "summary": summary(cards, args.top), "cards": cards}
    args.out.write_text(json.dumps(report, indent=1), "utf-8")
    print(json.dumps(report["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
