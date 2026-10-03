"""Rank the remaining rules gaps by reusable family (development tool).

    python -m tools.gap_rank --db ../data/cards.sqlite [--out gaps.md] [--top 25] [--family NAME]

Loads the Commander-legal cards, asks ``coverage`` which ability lines are unsupported, and buckets
those lines into regex families. A line goes to the first family that matches. "Missing" counts
unsupported lines; "sole" counts non-FULL cards whose every unsupported line falls in that family
(an upper bound on what fixing the family would promote to FULL). ``--family`` lists that family's
sole-blocker cards (by EDHREC rank) with their unsupported lines.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from app.config import load_settings
from app.rules import commander, coverage
from tools.commander_coverage import rows

# (name, regex). Order matters: the first match wins, so put narrow families before broad ones.
FAMILIES: list[tuple[str, str]] = [
    ("unless_pays", r"unless (?:that player|its controller|they|you|an opponent|any player|that spell's controller|he or she)[^.]*\bpays?\b"),
    ("cost_alt", r"rather than pay|without paying [^.]*mana cost[^.]*\bif\b|you may pay [^.]* rather"),
    ("cost_self_reduction", r"(?:this spell|~) costs? \{[^}]+\} less to cast for each|costs \{X\} less|costs? \{\d+\} less to cast if"),
    ("cost_changer", r"costs? \{[^}]+\} (?:less|more) to (?:cast|activate)|cost \{[^}]+\} (?:less|more)|costs? (?:less|more) to cast"),
    ("kicked_instead", r"\bif (?:this spell was|~ was|it was) kicked\b|\bkicker\b|\bmultikicker\b"),
    ("this_turn_state", r"\bif (?:you|an opponent|a creature|another creature|a player)[^.]*this turn\b|\braid\b|\bmorbid\b|\brevolt\b|\bthis turn\b,"),
    ("ability_word", r"^(?:metalcraft|delirium|threshold|hellbent|ferocious|formidable|spell mastery|coven|domain|landfall|fateful hour|corrupted|descend \d+|max speed|bloodrush|imprint|kinship|council's dilemma|will of the council|parley|join forces|tempting offer|grandeur|radiance|channel|undergrowth|addendum|alliance|battalion|constellation|converge|enrage|eminence|lieutenant|magecraft|pack tactics|valiant|eerie|survival|flurry|celebration|fathomless descent|void|paradox|start your engines!|renew|exhaust)\b"),
    ("damage_sized", r"deals? (?:damage equal to|x damage|that much damage|damage to [^.]* equal to)"),
    ("as_long_as_static", r"\bas long as\b|\bif you control\b[^.]*,\s*(?:~|it|this|creatures)"),
    ("if_you_do", r"\bif you do\b|\bthis way\b|\bif you don't\b|\bif they do\b|\bif no\b"),
    ("instead", r"\binstead\b"),
    ("activation_cost", r"^[^:\"]*(?:pay [^:]*life|sacrifice (?:x|two|three)|exert|remove [^:]*counters?|exile [^:]*from your graveyard|discard)[^:]*:"),
    ("reanimation", r"(?:return|put) [^.]*(?:from (?:your|a|their) graveyard|graveyard) (?:to|onto) (?:the battlefield|your hand|its owner's hand)"),
    ("face_down", r"face down|face-down"),
    ("tutor", r"search (?:your|their) library"),
    ("free_cast", r"without paying (?:its|their|that card's) mana cost|you may (?:cast|play) [^.]*(?:from|exiled)"),
    ("saga", r"^(?:i|ii|iii|iv|v|vi)(?:, (?:i|ii|iii|iv|v|vi))* —"),
    ("look_top", r"look at the top"),
    ("token_copy", r"token that's a copy|\bpopulate\b"),
    ("attached_events", r"enchanted (?:land|creature|permanent|player)|equipped creature"),
    ("attach_on_entry", r"attach (?:it|~) to"),
    ("control_change", r"gain control|exchange control"),
    ("transform", r"\btransform|\bmeld\b|\bconvert\b"),
    ("cant_restrictions", r"can't be (?:countered|sacrificed|the target)|can't be targeted|hexproof from"),
    ("copy_keywords", r"\b(?:myriad|encore|squad|casualty|replicate|offspring)\b"),
    ("player_counters", r"poison|energy|experience counters?|\brad\b"),
    ("chosen_type", r"chosen (?:type|name|color|player)|of the chosen"),
    ("x_value", r"\bx\b"),
    ("counters", r"counters? on"),
    ("trigger_other", r"^(?:when|whenever|at)\b"),
    ("activated_other", r"^[^\"]*\{[^}]+\}[^\"]*:"),
    ("static_other", r"."),
]
_COMPILED = [(n, re.compile(r, re.I)) for n, r in FAMILIES]


def family_of(line: str) -> str:
    text = line.strip()
    for name, rx in _COMPILED:
        if rx.search(text):
            return name
    return "static_other"


def _card(data: dict[str, Any]) -> tuple[str, int, str, bool, list[tuple[str, str]]] | None:
    if commander.legality(data) != "legal":
        return None
    cov = coverage.of_card_data(data)
    name = str(data.get("name"))
    rank = int(data.get("edhrec_rank") or 10**9)
    missing = [(f.id, f.label) for f in cov.features if not f.supported]
    return name, rank, cov.level, commander.can_be_commander(data), missing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--top", type=int, default=32)
    ap.add_argument("--family", action="append", default=[])
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("-j", type=int, default=8)
    args = ap.parse_args(argv)
    cards, _ = rows(args.db or load_settings().cards_db_path)
    with ProcessPoolExecutor(args.j) as pool:
        results = [r for r in pool.map(_card, cards, chunksize=256) if r is not None]
    lines_by: Counter[str] = Counter()
    sole: Counter[str] = Counter()
    sole_cmdr: Counter[str] = Counter()
    examples: dict[str, list[tuple[int, str]]] = defaultdict(list)
    detail: dict[str, list[tuple[int, str, list[str]]]] = defaultdict(list)
    levels: Counter[str] = Counter()
    cmdr_full = 0
    for name, rank, level, is_cmdr, missing in results:
        levels[level] += 1
        if level == "FULL" and is_cmdr:
            cmdr_full += 1
        if not missing:
            continue
        fams = []
        for fid, label in missing:
            fam = family_of(label) if fid.startswith(("text:", "script:", "mana:")) else f"feature:{fid.split(':')[0]}"
            if fid.startswith("keyword:"):
                fam = f"keyword:{label.lower()}"
            fams.append(fam)
            lines_by[fam] += 1
        if len(set(fams)) == 1:
            sole[fams[0]] += 1
            if is_cmdr:
                sole_cmdr[fams[0]] += 1
            examples[fams[0]].append((rank, name))
            detail[fams[0]].append((rank, name, [lab for _, lab in missing]))
    out = [f"Commander-legal: {sum(levels.values())} — " + ", ".join(f"{k} {v}" for k, v in sorted(levels.items()))
           + f"; commanders FULL {cmdr_full}", "",
           "| # | Family | Missing lines | Sole | Sole commanders | Examples (by EDHREC rank) |", "|---|---|---|---|---|---|"]
    ranked = sorted(lines_by, key=lambda f: (-sole[f], -lines_by[f]))
    for i, fam in enumerate(ranked[: args.top], 1):
        ex = ", ".join(n for _, n in sorted(examples[fam])[:4])
        out.append(f"| {i} | {fam} | {lines_by[fam]} | {sole[fam]} | {sole_cmdr[fam]} | {ex} |")
    for fam in args.family:
        out += ["", f"## {fam} (sole blockers)", ""]
        for rank, name, labs in sorted(detail[fam])[: args.limit]:
            out.append(f"- **{name}** ({rank}): " + " / ".join(lab.replace("\n", " ") for lab in labs))
    text = "\n".join(out) + "\n"
    if args.out:
        args.out.write_text(text, "utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
