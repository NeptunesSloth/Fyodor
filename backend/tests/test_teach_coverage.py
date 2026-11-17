"""-- Teach Fyodor -- the expressiveness sweep stays true (tests/teach_coverage.py, docs/TEACH_FYODOR_COVERAGE.md): every keyword
action, keyword ability and ability word of the Comprehensive Rules has a row; every row taught with pieces reads FULL (a check only,
no table: tests/test_teach_playtests.py plays the representative ones); the play-tested ones are teachable; the doc is current."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.rules import taught
from app.rules.taught_vocab import PIECE
from tests import teach_coverage as tc

ROOT = Path(__file__).resolve().parent.parent
TAUGHT = [r for r in tc.ROWS if r.abilities is not None]


@pytest.mark.parametrize("row", TAUGHT, ids=[f"{r.cr} {r.name}" for r in TAUGHT])
def test_every_taught_mechanic_reads_full(row):
    result = taught.check(row.entry())
    assert result["ok"], (result["problems"], result["lines"])


def test_rows_are_well_formed():
    assert len({r.made_up for r in tc.ROWS}) == len(tc.ROWS), "made-up names are unique"
    for r in tc.ROWS:
        assert (r.abilities is None) == bool(r.why or r.status == "piece"), f"{r.name}: an entry, or why not"
        assert not (r.partial and r.abilities is None), r.name
        assert all(p in PIECE for p in r.pieces), r.name
        if r.status == "piece":
            assert r.pieces, r.name
    assert set(PIECE) >= tc.NEW_PIECES, "every piece the sweep added still exists"


def test_every_mechanic_of_the_comprehensive_rules_has_a_row():
    files = sorted((ROOT.parent / "data" / "rules" / "comprehensive_rules").glob("*/comprehensive_rules.txt"))
    if not files:
        pytest.skip("no Comprehensive Rules text in this checkout")
    text = files[-1].read_text("utf-8")
    headings = {m[1]: m[2] for m in re.finditer(r"^(70[12]\.\d+)\. (.+)$", text, re.M) if m[1] not in ("701.1", "702.1")}
    rows = {r.cr: r.name for r in tc.ROWS if r.kind != "word"}
    assert set(headings) == set(rows), (sorted(set(headings) - set(rows)), sorted(set(rows) - set(headings)))
    for cr, name in headings.items():
        assert rows[cr].lower() == name.strip().lower(), (cr, name, rows[cr])
    words = re.search(r"^207\.2c .*? The ability words are (.+?)\.\s*$", text, re.M | re.S)
    assert words is not None
    listed = [re.sub(r"^and ", "", w.strip()).replace("’", "'") for w in words[1].split(",")]
    assert sorted(listed) == sorted(r.name for r in tc.ROWS if r.kind == "word")


def test_play_tested_mechanics_are_teachable():
    from tests.test_teach_playtests import PLAYED

    rows = {r.name: r for r in tc.ROWS}
    for name in PLAYED:
        assert tc.status(rows[name]) in ("full", "partial", "piece"), name


def test_coverage_doc_is_current():
    path = (ROOT / tc.DOC).resolve()
    assert path.is_file(), "run: python -m tests.teach_coverage"
    assert path.read_text("utf-8") == tc.doc(), "docs/TEACH_FYODOR_COVERAGE.md is stale: run python -m tests.teach_coverage"
