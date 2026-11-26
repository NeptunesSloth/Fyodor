"""The card data the rules engine reads (CardRepository.rules_card): the printing's fields read once per database, without the
image-file checks CardRepository.get makes on every call (the rules never look at images; on a big board the engine reads
card data tens of thousands of times in one action). A game session reads through it; everything else is unchanged."""

from __future__ import annotations

from pathlib import Path

from app.cards.importer import build_database
from app.game.session import GameSession
from tests.fixtures.cards import card
from tests.game_helpers import make_session


def test_rules_card_is_get_without_the_image_flag(cards):
    sol = cards.resolve("Sol Ring")
    full = cards.get(sol["id"])
    rules = cards.rules_card(sol["id"])
    assert "has_image" in full and "has_image" not in rules
    assert {k: v for k, v in full.items() if k not in ("has_image", "own_image", "art_from")} == rules
    assert cards.rules_card("no-such-printing") is None


def test_rules_card_reads_the_database_once_per_printing(cards, monkeypatch):
    sol = cards.resolve("Sol Ring")
    cards.rules_card(sol["id"])
    calls = []
    monkeypatch.setattr(cards.images, "has", lambda *a, **k: calls.append(a) or False)
    real = cards._query
    monkeypatch.setattr(cards, "_query", lambda *a, **k: calls.append(a) or real(*a, **k))
    for _ in range(50):
        assert cards.rules_card(sol["id"])["name"] == "Sol Ring"
    assert calls == []


def test_a_new_card_database_empties_the_cache(cards, tmp_path: Path):
    sol = cards.resolve("Sol Ring")
    assert cards.rules_card(sol["id"]) is not None
    fresh = tmp_path / "fresh.sqlite"
    build_database([card("Brand New Card", set_code="new", number="7")], fresh, meta={"bulk_type": "default_cards"})
    cards.replace_with(fresh)
    assert cards.rules_card(sol["id"]) is None  # not in the new database
    new = cards.resolve("Brand New Card")
    assert cards.rules_card(new["id"])["name"] == "Brand New Card"


def test_a_game_session_reads_rules_data_through_the_cache(cards):
    s = make_session(cards)
    assert isinstance(s, GameSession)
    any_card = next(iter(s.state.cards.values()))
    assert s.cards.get(any_card.card_id) == cards.rules_card(any_card.card_id)
    assert "has_image" not in s.cards.get(any_card.card_id)
    # every other repository method is the repository's own
    assert s.cards.resolve("Sol Ring")["name"] == "Sol Ring" and s.cards.search("Sol Ring")
