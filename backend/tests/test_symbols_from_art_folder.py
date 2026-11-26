"""A portable build's art pack (seed/images) carries the mana symbols and the card back: an offline computer draws the real
ones from the start, and the cache wins once it has its own (app/cards/images.py)."""

from __future__ import annotations

import json
from pathlib import Path

from app.cards.art_roots import ArtRoot
from app.cards.images import CARD_BACK_ID, SYMBOL_INDEX, ImageStore

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="5"/></svg>'


def _pack(base: Path, english: str) -> None:
    (base / "symbols").mkdir(parents=True)
    (base / "symbols" / SYMBOL_INDEX).write_text(json.dumps({"W": {"svg": "W", "english": english}}))
    (base / "symbols" / "W.svg").write_bytes(SVG)
    (base / "backs").mkdir()
    (base / "backs" / f"{CARD_BACK_ID}-normal.jpg").write_bytes(b"\xff\xd8\xff back")


def test_symbols_and_back_come_from_an_art_folder_until_the_cache_has_them(tmp_path):
    cache, seed = tmp_path / "cache", tmp_path / "seed"
    cache.mkdir()
    _pack(seed, "one white mana (pack)")
    store = ImageStore(cache, seed)
    assert store.symbol_index()["W"]["english"] == "one white mana (pack)"
    assert store.symbol("W") == seed / "symbols" / "W.svg"
    assert store.symbol("../W") is None and store.symbol("U") is None
    assert store.card_back() == seed / "backs" / f"{CARD_BACK_ID}-normal.jpg"
    _pack(cache, "one white mana (cache)")
    assert store.symbol_index()["W"]["english"] == "one white mana (cache)"
    assert store.symbol("W") == cache / "symbols" / "W.svg"
    assert store.card_back() == cache / "backs" / f"{CARD_BACK_ID}-normal.jpg"


def test_a_loose_art_folder_is_not_read_for_symbols(tmp_path):
    cache, loose = tmp_path / "cache", tmp_path / "loose"
    cache.mkdir()
    _pack(loose, "x")
    store = ImageStore(cache, roots=[ArtRoot(loose, "added", "loose")])
    assert store.symbol_index() == {} and store.card_back() is None
