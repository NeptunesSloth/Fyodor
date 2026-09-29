"""The Commander card pool: coverage and the missing-feature queue (used by the report tool).

Only cards whose **current** Commander legality is "legal" count. Banned cards are counted as
COMMANDER_BANNED and left out of every statistic and ranking; other non-legal cards (other
formats, Un-sets, digital-only) are ignored. Pod cards and pod commanders come first in the
missing-feature queue, then Commander-legal cards unlocked.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.rules import analysis, commander, coverage

LEVELS = ("FULL", "PARTIAL", "REVIEW", "MANUAL")
MAIN_TYPES = ("Creature", "Planeswalker", "Battle", "Instant", "Sorcery", "Artifact", "Enchantment", "Land")


@dataclass
class Missing:
    """One engine feature not implemented yet, and what it would unlock."""

    key: str  # "keyword:ward", "template:When ~ enters, draw N card(s)."
    kind: str
    cards: set[str] = field(default_factory=set)  # oracle ids that need it
    pod_cards: set[str] = field(default_factory=set)
    pod_commanders: set[str] = field(default_factory=set)
    blocks_alone: int = 0  # cards for which this is the only missing piece
    examples: list[str] = field(default_factory=list)

    def rank(self) -> tuple[int, int, int, int, int]:
        return (-len(self.pod_cards) - 10 * len(self.pod_commanders), -len(self.pod_commanders), -self.blocks_alone,
                -len(self.cards), 0)


@dataclass
class PoolReport:
    total: int = 0
    banned: int = 0
    levels: Counter[str] = field(default_factory=Counter)
    by_type: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    by_keyword: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    by_set: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    commanders: Counter[str] = field(default_factory=Counter)
    commander_rows: list[dict[str, Any]] = field(default_factory=list)
    pod: Counter[str] = field(default_factory=Counter)
    pod_rows: list[dict[str, Any]] = field(default_factory=list)
    kinds: Counter[str] = field(default_factory=Counter)
    missing: dict[str, Missing] = field(default_factory=dict)
    keyword_cards: Counter[str] = field(default_factory=Counter)


def _missing_keys(data: dict[str, Any], cov: coverage.Coverage) -> list[tuple[str, str]]:
    """What a card still needs, as reusable features (keywords by name, other text by template)."""
    by_text = {s.text: s for s in analysis.segments(data)}
    out = []
    for f in cov.features:
        if f.supported:
            continue
        if f.id.startswith("keyword:"):
            out.append((f.id, "keyword"))
        elif f.id.startswith("text:"):
            seg = by_text.get(f.label)
            out.append((f"template:{seg.template if seg else f.label}", seg.kind if seg else "static"))
        else:
            out.append((f.id, "engine"))
    return out


def analyse(cards: Iterable[dict[str, Any]], *, pod_oracle_ids: set[str] | None = None,
            pod_commander_ids: set[str] | None = None, commander_limit: int = 300) -> PoolReport:
    pod_ids = pod_oracle_ids or set()
    pod_cmdrs = pod_commander_ids or set()
    rep = PoolReport()
    commander_candidates: list[tuple[int, dict[str, Any]]] = []
    for data in cards:
        status = commander.legality(data)
        if status == "banned":
            rep.banned += 1
            continue
        if status != "legal":
            continue
        rep.total += 1
        cov = coverage.of_card_data(data)
        level = cov.level
        oid = str(data.get("oracle_id") or data.get("name"))
        rep.levels[level] += 1
        type_line = str(data.get("type_line") or "")
        for t in MAIN_TYPES:
            if re.search(rf"\b{t}\b", type_line):
                rep.by_type[t][level] += 1
        for kw in data.get("keywords") or []:
            rep.by_keyword[str(kw).lower()][level] += 1
            rep.keyword_cards[str(kw).lower()] += 1
        rep.by_set[str(data.get("set_code") or "?")][level] += 1
        for seg in analysis.segments(data):
            rep.kinds[seg.kind] += 1
        is_commander = commander.can_be_commander(data)
        if is_commander:
            rep.commanders[level] += 1
            commander_candidates.append((int(data.get("edhrec_rank") or 10**9), data))
        if oid in pod_ids:
            rep.pod[level] += 1
            rep.pod_rows.append({"name": data.get("name"), "level": level, "manual_parts": cov.manual_parts})
        needs = _missing_keys(data, cov)
        for key, kind in needs:
            m = rep.missing.setdefault(key, Missing(key, kind))
            m.cards.add(oid)
            if oid in pod_ids:
                m.pod_cards.add(oid)
            if oid in pod_cmdrs:
                m.pod_commanders.add(oid)
            if len({k for k, _ in needs}) == 1:
                m.blocks_alone += 1
            if len(m.examples) < 5:
                m.examples.append(str(data.get("name")))
    commander_candidates.sort(key=lambda x: (x[0], str(x[1].get("name"))))
    for _, data in commander_candidates[:commander_limit]:
        cov = coverage.of_card_data(data)
        rep.commander_rows.append({
            "name": data.get("name"), "level": cov.level, "edhrec_rank": data.get("edhrec_rank"),
            "color_identity": "".join(commander.color_identity(data)) or "C",
            "pairing": [p.kind for p in commander.pairings(data)],
            "supported": [f.label for f in cov.features if f.supported],
            "missing": cov.manual_parts,
        })
    return rep


def queue(rep: PoolReport, limit: int = 60) -> list[Missing]:
    return sorted(rep.missing.values(), key=lambda m: (*m.rank(), m.key))[:limit]


def as_json(rep: PoolReport, meta: dict[str, Any]) -> dict[str, Any]:
    def levels(c: Counter[str]) -> dict[str, int]:
        return {lv: c.get(lv, 0) for lv in LEVELS}

    return {
        **meta,
        "commander_legal_cards": rep.total, "commander_banned": rep.banned, "levels": levels(rep.levels),
        "possible_commanders": sum(rep.commanders.values()), "commander_levels": levels(rep.commanders),
        "pod": {"cards": sum(rep.pod.values()), "levels": levels(rep.pod), "rows": rep.pod_rows},
        "by_type": {t: levels(c) for t, c in rep.by_type.items()},
        "by_keyword": {k: levels(c) for k, c in sorted(rep.by_keyword.items(), key=lambda kv: -sum(kv[1].values()))[:150]},
        "by_set": {s: levels(c) for s, c in sorted(rep.by_set.items())},
        "feature_kinds": dict(rep.kinds.most_common()),
        "missing_features": [{"feature": m.key, "kind": m.kind, "commander_cards": len(m.cards), "pod_cards": len(m.pod_cards),
                              "pod_commanders": len(m.pod_commanders), "only_missing_piece_for": m.blocks_alone,
                              "examples": m.examples} for m in queue(rep, 200)],
        "commanders": rep.commander_rows,
    }


def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:.1f}%" if total else "—"


def markdown(data: dict[str, Any]) -> str:
    total = data["commander_legal_cards"]
    lv = data["levels"]
    lines = [
        "# Commander rules coverage", "",
        f"Card data: Scryfall `{data.get('card_data')}` · Comprehensive Rules {data.get('comprehensive_rules')} · "
        f"rules engine v{data.get('rules_engine_version')} · generated {data.get('generated_at')}", "",
        "Only cards that are **legal in Commander today** count. Banned cards "
        f"({data['commander_banned']}) are COMMANDER_BANNED and excluded.", "",
        "## Commander coverage", "",
        f"Commander-legal cards: **{total}**", "",
        "| Level | Cards | Share |", "|---|---|---|",
        *[f"| {k} | {v} | {_pct(v, total)} |" for k, v in lv.items()], "",
        f"Possible commanders (CR 903.3/903.3a, incl. Backgrounds): **{data['possible_commanders']}** — "
        + ", ".join(f"{k} {v}" for k, v in data["commander_levels"].items()), "",
        "## Pod coverage", "",
    ]
    pod = data["pod"]
    if pod["cards"]:
        full = pod["levels"]["FULL"]
        lines += [f"Pod cards: {pod['cards']} · FULL {_pct(full, pod['cards'])}", "",
                  "Unsupported pod cards:", "",
                  *[f"- {r['name']} ({r['level']}): {'; '.join(r['manual_parts'])[:200]}" for r in pod["rows"] if r["level"] != "FULL"][:100], ""]
    else:
        lines += ["No pod decks in the inventory yet (`python -m tools.rules_inventory`); the queue below is ranked by "
                  "Commander-legal cards unlocked.", ""]
    lines += ["## Top Commander features to implement next", "",
              "Ranked by pod cards, pod commanders, cards for which it is the only missing piece, then Commander cards needing it.", "",
              "| # | Feature | Kind | Pod cards | Commander cards | Only missing piece for | Examples |", "|---|---|---|---|---|---|---|"]
    for i, m in enumerate(data["missing_features"][:60], 1):
        lines.append(f"| {i} | {m['feature'].replace('|', '/')} | {m['kind']} | {m['pod_cards']} | {m['commander_cards']} | "
                     f"{m['only_missing_piece_for']} | {', '.join(m['examples'][:3])} |")
    lines += ["", "## Coverage by card type", "", "| Type | FULL | PARTIAL | REVIEW | MANUAL |", "|---|---|---|---|---|"]
    for t, c in data["by_type"].items():
        lines.append(f"| {t} | {c['FULL']} | {c['PARTIAL']} | {c['REVIEW']} | {c['MANUAL']} |")
    lines += ["", "## Rules features in the pool (ability lines)", "",
              ", ".join(f"{k} {v}" for k, v in data["feature_kinds"].items()), ""]
    return "\n".join(lines)


def commander_markdown(data: dict[str, Any]) -> str:
    lines = ["# Commander coverage (possible commanders)", "",
             f"TOTAL POSSIBLE COMMANDERS: **{data['possible_commanders']}** — "
             + " · ".join(f"{k}: {v}" for k, v in data["commander_levels"].items()), "",
             "The most-played commanders first (EDHREC rank from the card data).", ""]
    for row in data["commanders"]:
        pair = f" · pairs via {', '.join(row['pairing'])}" if row["pairing"] else ""
        lines += [f"### {row['name']} — {row['level']}", "",
                  f"Color identity {row['color_identity']}{pair}", ""]
        lines += [f"- ✓ {s}" for s in row["supported"]] + [f"- ✗ {s}" for s in row["missing"]] + [""]
    return "\n".join(lines)
