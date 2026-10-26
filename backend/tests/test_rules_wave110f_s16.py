"""Wave 110F session 16, on real Oracle text. Every scenario checks the replay and a save and a load.

* 702.159a, 611.2a, 706.2: Drop Tower: "Visit — Target creature gains flying until end of turn, or until any player rolls a 1, whichever comes first."
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real, rolls
from tests.test_rules_wave100k_instead import keywords
from tests.test_rules_wave100l_attractions import EXTRA, card_db, game, settle, to_main  # noqa: F401  (fixture DB with EXTRA)
from tests.wave9c_kit import card_named, check, mana, put, to_hand

EXTRA.append(card("Drop Tower", set_code="unf", number="209a", mana_cost="", cmc=0.0, type_line="Artifact — Attraction",
                  oracle_text="Visit — Target creature gains flying until end of turn, or until any player rolls a 1, whichever comes first.",
                  colors=[], color_identity=[], keywords=[]))
EXTRA.append(real("Test Roller 110F", "{1}", 1, "Sorcery", "Roll a six-sided die.", None, ""))


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Drop Tower")).level == "FULL"


def _tower(cards, monkeypatch, *dice):
    rolls(monkeypatch, *dice)
    s = game(cards, ["Grizzly Bears", "Test Roller 110F"], ["Drop Tower"])  # 209a: 2, 3 and 6 lit
    bears = put(s, "Grizzly Bears")
    put(s, "Drop Tower")
    to_main(s, 3)
    return s, bears


def test_the_visit_grants_flying(cards, monkeypatch):
    s, bears = _tower(cards, monkeypatch, 3)
    assert "Flying" in keywords(s, bears) or "flying" in keywords(s, bears)
    check(s)


@pytest.mark.parametrize(("die", "flies"), [(1, False), (2, True)])
def test_a_roll_of_1_ends_the_flying_any_other_roll_does_not(cards, monkeypatch, die, flies):
    s, bears = _tower(cards, monkeypatch, 3, die)
    to_hand(s, "Test Roller 110F")
    mana(s, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Test Roller 110F").id)
    settle(s)
    assert ("flying" in {k.lower() for k in keywords(s, bears)}) is flies
    check(s)


def test_the_flying_ends_with_the_turn(cards, monkeypatch):
    s, bears = _tower(cards, monkeypatch, 3)
    to_main(s, 4)
    assert "flying" not in {k.lower() for k in keywords(s, bears)}
    check(s)
