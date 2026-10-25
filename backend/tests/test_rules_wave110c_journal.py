"""Wave 110C: The Tomb of Aclazotz (back of Tarrian's Journal): one creature spell from the graveyard this turn (601.3), it enters with a finality counter (122.6) and is a Vampire in addition to its other types (205.1b, 613.1d)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, ch, check, make_db, mana, put, to_graveyard

NAME = "Tarrian's Journal // The Tomb of Aclazotz"
DATA = json.loads((Path(__file__).parent / "fixtures" / "wave110c_journal_cards.json").read_text("utf-8"))  # real DB row, both faces
EXTRA = [card(c["name"], set_code="w110c", number="J001", **{k: v for k, v in c.items() if k != "name"}) for c in DATA]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


def _go(cards):
    s = build(cards, [NAME, "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"])
    tomb = put(s, NAME)
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=tomb.id, ability=1)  # {2},{T},discard your hand: transform
    answer(s)
    act(s, "p1", type="tap", card_ids=[tomb.id], tapped=False)  # transformed permanent is the same object (712.8)
    to_graveyard(s, 2, "Grizzly Bears")
    act(s, "p1", type="activate_ability", card_id=tomb.id, ability=1)
    answer(s)
    return s


def test_one_creature_spell_enters_with_finality_and_is_a_vampire(cards):
    s = _go(cards)
    bears = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:graveyard"]
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=bears[0].id)
    answer(s)
    now = [c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.zone == "p1:battlefield"]
    assert len(now) == 1 and now[0].counters.get("finality") == 1
    assert "Vampire" in ch(s, now[0]).subtypes and "Bear" in ch(s, now[0]).subtypes
    with pytest.raises(Exception, match="You can cast spells from your hand"):  # only one spell
        act(s, "p1", type="cast_spell", card_id=bears[1].id)
    check(s)
