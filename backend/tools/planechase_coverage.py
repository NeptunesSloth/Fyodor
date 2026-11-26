"""-- planechase automation -- coverage of every plane and phenomenon, by wording family (development tool).

    python -m tools.planechase_coverage --db ../data/cards.sqlite --out ../docs/research

Writes ``planechase-coverage.md`` (one line per card, family counts) and ``planechase-coverage.json`` (per card: Oracle text, level,
each ability line with its family and whether the engine runs it). Planes are no Commander cards (commander.NON_DECK_TYPES), so
tools.card_check / gap_rank skip them: this reads the same rows (tools.commander_coverage.rows) and ``coverage.of_card_data``.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path
from typing import Any

from app.config import load_settings
from app.rules import coverage
from app.rules import scripts as templates
from app.rules.characteristics import printed_from_data
from tools.commander_coverage import rows

_CHAOS = re.compile(r"^(?:Whenever|When) [Cc]haos ensues,? (?P<body>.+)|^Chaos: (?P<body2>.+)|^\{CHAOS\}.*?(?P<body3>.+)", re.S)
_TO = re.compile(r"^(?:Whenever|When) you planeswalk (?:to |here)")
_FROM = re.compile(r"^(?:Whenever|When) you planeswalk away from ")
_ENCOUNTER = re.compile(r"^When you encounter ")
_TRIG = re.compile(r"^(?:Whenever|When|At the beginning of|At the end of) ")

# the shape of a chaos ability's effect, by its first words (for the wave agents' grouping; not a parser)
_SHAPES = [
    ("draw / discard / mill", r"^(?:draw|each player draws|discard|target player mills|you may draw|mill|each player discards)"),
    ("create tokens", r"^(?:create|you may create|for each opponent, you create|each player creates|each player may create)"),
    ("counters", r"^(?:put (?:a|an|X|two|three|one) .*counters?|you may put a .*counter|distribute)"),
    ("destroy / exile / bounce", r"^(?:destroy|you may destroy|exile|return target creature you control|each other player sacrifices|you may sacrifice)"),
    ("return from graveyard", r"^(?:return target|you may return|each player may return|for each opponent, exile)"),
    ("damage / life", r"^(?:~|[A-Z][\w' ]+ deals|you (?:may )?gain|target player loses|you may have your life|each player loses|you lose)"),
    ("pump / grant until end of turn", r"^(?:target creature|creatures you control|each creature|untap|tap|target land|until end of turn|Slivers you control)"),
    ("reveal / look / search", r"^(?:reveal|look at|search|exile cards from the top|exile the top|choose)"),
    ("lasting effect (until a player planeswalks / rest of game)", r"until a player planeswalks|for the rest of the game|until your next turn"),
]


def family(line: str, name: str) -> tuple[str, str]:
    """(family, sub-family) of one ability line of a plane or phenomenon."""
    text = line.replace(name, "~").strip()
    if text.startswith("•"):  # a mode of a modal ability ("Whenever chaos ensues, choose one —")
        return "chaos", "mode bullet"
    text = re.sub(r"^[^—.]{1,40} ?— ?", "", text)  # an ability word or flavor word (207.2c)
    m = _CHAOS.match(text)
    if m:
        body = (m["body"] or m["body2"] or m["body3"] or "").strip()
        for label, rx in _SHAPES[-1:] + _SHAPES[:-1]:
            if re.search(rx, body):
                return "chaos", label
        return "chaos", "other"
    if _ENCOUNTER.match(text):
        return "encounter", ""
    if _FROM.match(text):
        return "planeswalk away", ""
    if _TO.match(text):
        return "planeswalk to", "and upkeep" if "at the beginning of your upkeep" in text else ""
    if re.search(r"\bplaneswalk\b", text) and not text.startswith(("Whenever", "When", "At ")):
        return "static", "planar rules (die / planeswalk)"
    if _TRIG.match(text):
        return "trigger", "upkeep / step" if text.startswith("At ") else "event"
    if re.match(r"^If .* would .*(?:instead|additional time)", text):
        return "static", "replacement"
    if text.startswith("Prevent "):
        return "static", "prevention"
    if re.match(r"^(?:No more than|You may play|During your turn|Any time you could|If you (?:attacked|cast)|Change the text|The top card|The first spell)", text):
        return "static", "rules change"
    if re.search(r"(?:ha(?:ve|s) [a-z]+(?: \{| [a-z]+\.|\.)|are [a-z]+s in addition)", text):
        return "static", "keyword / type grant"
    if re.search(r"cost[s]? \{?\d|cost .* less|cost .* more", text):
        return "static", "cost change"
    if re.match(r"^(?:All |Each |Creatures |Players |Nonbasic |Cards |Spells |Lands |Artifact|Red |Green |Blue |Black |White |Modified |Permanents |Tokens )", text):
        return "static", "grant / rule for all"
    return "other", ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    data = [d for d in rows(args.db or load_settings().cards_db_path)[0]
            if re.match(r"(?i)^(plane\b(?!swalker)|phenomenon)", d.get("type_line") or "")]
    data.sort(key=lambda d: d["name"])
    cards: list[dict[str, Any]] = []
    fam_lines: dict[tuple[str, str], list[int]] = collections.defaultdict(lambda: [0, 0])  # (supported, total)
    levels: collections.Counter[str] = collections.Counter()
    gaps: dict[tuple[str, str], collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for d in data:
        cov = coverage.of_card_data(d)
        levels[cov.level] += 1
        lines = []
        defs = templates.definitions(printed_from_data(d, 0))
        for f in cov.features:
            if not f.id.startswith(("text:", "keyword:", "mana:", "script:")):
                continue
            fam, sub = family(f.label, d["name"]) if f.id.startswith("text:") else ("keyword", f.label)
            fam_lines[(fam, sub)][0] += f.supported
            fam_lines[(fam, sub)][1] += 1
            gap = None
            if not f.supported:  # what's missing: the wording (grammar) or only a collector reading it on the planar object
                dd = defs.get(int(f.id.split(":")[1])) if f.id.startswith("text:") else None
                gap = "grammar" if dd is None or not coverage.definition_supported(dd) else                     f"collector ({dd.get('kind')} {dd.get('static') or dd.get('trigger')})"
                gaps[(fam, sub)][gap.split(" ")[0]] += 1
            lines.append({"text": f.label, "family": fam, "shape": sub, "supported": f.supported, "gap": gap})
        cards.append({"name": d["name"], "type_line": d.get("type_line"), "phenomenon": (d.get("type_line") or "").lower().startswith("phenomenon"),
                      "set": d.get("set_code"), "oracle_text": d.get("oracle_text"), "level": cov.level, "lines": lines})
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "planechase-coverage.json").write_text(json.dumps({"levels": dict(levels), "cards": cards}, indent=1, ensure_ascii=False), "utf-8")
    md = ["# Planechase coverage (planes and phenomena)", "",
          f"{len(cards)} cards: " + ", ".join(f"{k} {v}" for k, v in sorted(levels.items())) + ". Generated by `python -m tools.planechase_coverage`; "
          "details per line in `planechase-coverage.json`. A line counts as supported only when the planar object's collectors read it "
          "(`app/rules/planar.py` ``ability_ok``).", "",
          "## Families (ability lines: supported / total; a missing line needs new grammar, or is read already but no collector",
          "reads it on the planar object yet)", "",
          "| Family | Shape | Supported | Lines | Missing: grammar | Missing: collector only |", "|---|---|---|---|---|---|"]
    for (fam, sub), (ok, n) in sorted(fam_lines.items(), key=lambda x: (x[0][0], -x[1][1])):
        g = gaps[(fam, sub)]
        md.append(f"| {fam} | {sub} | {ok} | {n} | {g['grammar']} | {g['collector']} |")
    md += ["", "## Cards", "", "| Card | Kind | Level | Missing lines (family) |", "|---|---|---|---|"]
    for c in cards:
        miss = "; ".join(f"{ln['family']}{'/' + ln['shape'] if ln['shape'] else ''} [{ln['gap']}]: {ln['text'][:90]}" for ln in c["lines"] if not ln["supported"])
        md.append(f"| {c['name']} | {'Phenomenon' if c['phenomenon'] else 'Plane'} | {c['level']} | {miss.replace('|', '/')} |")
    (args.out / "planechase-coverage.md").write_text("\n".join(md) + "\n", "utf-8")
    print(dict(levels), len(cards))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
