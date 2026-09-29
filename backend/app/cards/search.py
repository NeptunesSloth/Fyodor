"""A small Scryfall-flavoured query language compiled to SQL over the card database.

Supported terms (combined with AND)::

    sol ring            name words (prefix match)
    "sol ring"          exact phrase in the name
    t:creature          type line contains
    o:flying            oracle text contains (full-text)
    c:ug / c=ug         colors include / exactly
    id:wubrg            color identity within
    mv=3  mv<=2 cmc>4   mana value comparison
    s:cmm set:cmm       set code
    is:token            tokens only (is:card for non-tokens)
    is:commander        legendary creatures / "can be your commander"
    -t:land             negate any prefixed term
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

COLORS = set("wubrgc")
_CMP = re.compile(r"^(mv|cmc)(<=|>=|=|<|>|:)(\d+(?:\.\d+)?)$")
_COLOR_TERM = re.compile(r"^(c|color|id|ci|identity)(<=|>=|=|:)([wubrgc]+)$")


@dataclass
class CompiledQuery:
    where: list[str] = field(default_factory=list)
    params: list[object] = field(default_factory=list)
    name_terms: list[str] = field(default_factory=list)
    exact_name: str | None = None
    tokens: bool | None = None


def fts_quote(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^\w']+", text.lower()) if w.strip("'")]


def compile_query(query: str) -> CompiledQuery:
    out = CompiledQuery()
    try:
        parts = shlex.split(query)
    except ValueError:
        parts = query.split()
    for raw in parts:
        negate = raw.startswith("-") and len(raw) > 1 and (":" in raw or "=" in raw or "<" in raw or ">" in raw)
        term = raw[1:] if negate else raw
        lowered = term.lower()
        clause: str | None = None
        params: list[object] = []

        cmp_match = _CMP.match(lowered)
        color_match = _COLOR_TERM.match(lowered)
        if cmp_match:
            op = "=" if cmp_match.group(2) == ":" else cmp_match.group(2)
            clause, params = f"p.cmc {op} ?", [float(cmp_match.group(3))]
        elif color_match:
            clause, params = _color_clause(color_match.group(1), color_match.group(2), color_match.group(3))
        elif ":" in term:
            key, _, value = term.partition(":")
            key = key.lower()
            if key in ("t", "type"):
                clause, params = "p.type_line LIKE ?", [f"%{value}%"]
            elif key in ("o", "oracle", "text"):
                words = _words(value)
                if words:
                    expr = " ".join(fts_quote(w) + "*" for w in words)
                    clause, params = "p.rowid IN (SELECT rowid FROM oracle_fts WHERE oracle_fts MATCH ?)", [
                        f"oracle_text : ({expr})"
                    ]
            elif key in ("s", "set", "e"):
                clause, params = "p.set_code = ?", [value.lower()]
            elif key == "is":
                v = value.lower()
                if v == "token":
                    out.tokens = not negate
                    continue
                if v == "card":
                    out.tokens = negate
                    continue
                if v == "commander":
                    clause = "((p.type_line LIKE '%Legendary%' AND p.type_line LIKE '%Creature%') OR p.oracle_text LIKE '%can be your commander%')"
            if clause is None:
                out.name_terms.extend(_words(term))
                continue
        else:
            if " " in term:
                out.exact_name = term
            out.name_terms.extend(_words(term))
            continue
        if clause:
            out.where.append(f"NOT ({clause})" if negate else clause)
            out.params.extend(params)
    return out


def _color_clause(key: str, op: str, letters: str) -> tuple[str, list[object]]:
    column = "p.colors" if key in ("c", "color") else "p.color_identity"
    wanted = {ch.upper() for ch in letters if ch != "c"}
    colorless = "c" in letters
    clauses: list[str] = []
    if colorless and not wanted:
        return f"{column} = '[]'", []
    if key in ("id", "ci", "identity") and op in (":", "<="):
        # identity within: no color outside the wanted set
        for color in "WUBRG":
            if color not in wanted:
                clauses.append(f"{column} NOT LIKE '%\"{color}\"%'")
        return " AND ".join(clauses) or "1", []
    for color in "WUBRG":
        if color in wanted:
            clauses.append(f"{column} LIKE '%\"{color}\"%'")
        elif op == "=":
            clauses.append(f"{column} NOT LIKE '%\"{color}\"%'")
    return " AND ".join(clauses) or "1", []
