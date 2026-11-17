"""-- Teach Fyodor -- every piece of the vocabulary, in every choice of its main setting, makes a sentence the engine reads as FULL
(tests/teach_matrix.py lists the cases), and the shared sentence fixture the page's tests read is current."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rules import taught
from app.rules.taught_vocab import CATEGORIES, OPTIONS, PIECE, PIECES, vocabulary
from tests.teach_matrix import FIXTURE, VOCABULARY_FIXTURE, matrix, sentences

CASES = matrix()


@pytest.mark.parametrize("entry", [c[1] for c in CASES], ids=[c[0] for c in CASES])
def test_every_piece_reads_full(entry):
    result = taught.check(entry)
    assert result["ok"], (result["problems"], result["lines"])
    assert all(a["understood"] for a in result["abilities"]), result["abilities"]  # (a bare keyword or mana ability has no definition dict)


def test_vocabulary_is_consistent():
    cats = {c["id"] for c in CATEGORIES}
    assert len(PIECE) == len(PIECES), "piece ids are unique"
    for p in PIECES:
        assert p["cat"] in cats, p["id"]
        for key, slot in (p.get("slots") or {}).items():
            assert f"{{{key}" in p["text"] or p.get("bare"), (p["id"], key)
            if slot["kind"] == "choice":
                assert slot["default"] in slot["options"] and all(o in OPTIONS for o in slot["options"]), (p["id"], key)
        if p.get("after"):
            assert p["after"] in PIECE
    voc = vocabulary()
    assert json.loads(json.dumps(voc)) == voc, "the vocabulary is plain JSON"


def test_sentence_fixture_is_current():
    path = Path(__file__).resolve().parent.parent / FIXTURE
    assert path.is_file(), "run: python -m tests.teach_matrix"
    assert json.loads(path.read_text("utf-8")) == sentences(), "the sentence fixture is stale: run python -m tests.teach_matrix"
    voc = Path(__file__).resolve().parent.parent / VOCABULARY_FIXTURE
    assert json.loads(voc.read_text("utf-8")) == vocabulary(), "the vocabulary fixture is stale: run python -m tests.teach_matrix"
