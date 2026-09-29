"""Search the local Comprehensive Rules index.

    python -m tools.rules_research.search "mana ability"
    python -m tools.rules_research.search 903.9
    python -m tools.rules_research.search "leaves a multiplayer game" --limit 5

A deterministic lexical search (term frequency, headings and glossary weighted up). It helps a
developer find the rules that apply; it never decides anything at game time.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter
from pathlib import Path

from tools.rules_research.cr import ComprehensiveRules, parse
from tools.rules_research.store import latest_text

_WORD = re.compile(r"[a-z0-9]+(?:[’'][a-z]+)?")
STOP = frozenset(["a", "an", "the", "of", "to", "in", "on", "or", "and", "is", "are", "be", "it", "its", "that", "this", "with", "for", "as", "by", "if", "any", "each", "from", "at"])


def words(text: str) -> list[str]:
    out = []
    for w in _WORD.findall(text.lower().replace("’", "'")):
        w = w.replace("'s", "")
        if w in STOP:
            continue
        for suffix in ("ies", "es", "s", "ing", "ed"):  # a tiny stemmer: good enough for rules prose
            if w.endswith(suffix) and len(w) - len(suffix) >= 4:
                w = w[: -len(suffix)] + ("y" if suffix == "ies" else "")
                break
        out.append(w)
    return out


class Index:
    def __init__(self, cr: ComprehensiveRules) -> None:
        self.cr = cr
        self.docs: list[tuple[str, str, Counter[str]]] = []  # (id, text, term counts)
        for num, rule in cr.rules.items():
            heading = cr.title(num)
            self.docs.append((num, rule.full_text(), Counter(words(rule.full_text()) + words(heading) * 2)))
        for term, text in cr.glossary.items():
            self.docs.append((f"Glossary: {term}", text, Counter(words(term) * 3 + words(text))))
        df: Counter[str] = Counter()
        for _, _, counts in self.docs:
            df.update(counts.keys())
        n = len(self.docs)
        self.idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}

    def search(self, query: str, limit: int = 10) -> list[tuple[float, str, str]]:
        q = query.strip()
        if re.fullmatch(r"\d{3}(\.\d+[a-z]?)?", q):  # a rule number: that rule and its subrules
            hits = [(1.0, num, r.full_text()) for num, r in self.cr.rules.items()
                    if num == q or num.startswith(q + ".") or (num.startswith(q) and num[len(q):].isalpha())]
            return hits[:limit]
        terms = words(q)
        phrase = q.lower()
        scored = []
        for doc_id, text, counts in self.docs:
            score = sum(self.idf.get(t, 0.0) * (1 + math.log(counts[t])) for t in terms if counts[t])
            if not score:
                continue
            if phrase in text.lower():
                score *= 2  # the exact phrase
            covered = sum(1 for t in set(terms) if counts[t])
            score *= covered / max(1, len(set(terms)))
            scored.append((score, doc_id, text))
        scored.sort(key=lambda s: (-s[0], s[1]))
        return scored[:limit]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--file", type=Path, help="a Comprehensive Rules TXT (default: the latest stored version)")
    args = parser.parse_args(argv)
    text = args.file.read_text("utf-8") if args.file else latest_text()
    if text is None:
        print("No rules stored yet: run python -m tools.rules_research.update", file=sys.stderr)
        return 1
    cr = parse(text)
    print(f"Comprehensive Rules effective {cr.effective}\n")
    for score, doc_id, body in Index(cr).search(args.query, args.limit):
        heading = cr.title(doc_id) if not doc_id.startswith("Glossary") else ""
        first = body.split("\n", 1)[0]
        print(f"{doc_id}{f' ({heading})' if heading else ''}  [{score:.2f}]\n  {first[:300]}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
