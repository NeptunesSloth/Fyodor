"""Wave 110C: Dragon's Approach / Sphinx's Approach (608.2c: an optional exile of this spell and four other same-name cards in the graveyard, then
"if you do" the search; 614.1a: the resolving spell is exiled instead of going to the graveyard; 100.2a: the deck-building line has no in-game effect)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, check, life, make_db, mana, real, to_graveyard, to_hand, zone

DECK = "A deck can have any number of cards named {0}."
EXTRA = [real("Dragon's Approach", "{3}{R}", 4, "Instant",
              "Dragon's Approach deals 3 damage to each opponent. You may exile this spell and four cards named Dragon's Approach from your graveyard. "
              "If you do, search your library for a Dragon creature card, put it onto the battlefield, then shuffle.\n" + DECK.format("Dragon's Approach"), None, "R"),
         real("Sphinx's Approach", "{3}{U}", 4, "Instant",
              "Draw two cards. Then you may exile this spell and four cards named Sphinx's Approach from your graveyard. If you do, search your library for a "
              "Sphinx creature card, put it onto the battlefield, then shuffle.\n" + DECK.format("Sphinx's Approach"), None, "U"),
         real("Test Dragon", "{4}{R}{R}", 6, "Creature — Dragon", "", ("5", "5"), "R"),
         real("Test Sphinx", "{4}{U}{U}", 6, "Creature — Sphinx", "", ("5", "5"), "U")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["Dragon's Approach", "Sphinx's Approach"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("others", [3, 4])
def test_dragons_approach(cards, others):
    s = build(cards, ["Dragon's Approach"] * 6 + ["Test Dragon", "Forest"])
    spell = to_hand(s, "Dragon's Approach")
    to_graveyard(s, others, "Dragon's Approach")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    assert life(s, "p2") == 37
    dragon = next(c for c in s.state.cards.values() if c.name == "Test Dragon")
    if others == 4:  # exiles itself and the four, fetches the Dragon
        assert zone(s, spell) == "p1:exile" and zone(s, dragon) == "p1:battlefield"
        assert sum(c.zone == "p1:exile" for c in s.state.cards.values() if c.name == "Dragon's Approach") == 5
    else:  # not enough cards: no offer, the spell goes to the graveyard
        assert zone(s, spell) == "p1:graveyard" and zone(s, dragon) == "p1:library"
    check(s)


def test_declining_keeps_everything(cards):
    s = build(cards, ["Forest"] * 6 + ["Sphinx's Approach"] * 6 + ["Test Sphinx"])
    spell = to_hand(s, "Sphinx's Approach")
    to_graveyard(s, 4, "Sphinx's Approach")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Don't")])
    answer(s)
    assert zone(s, spell) == "p1:graveyard"
    assert sum(c.zone == "p1:graveyard" for c in s.state.cards.values() if c.name == "Sphinx's Approach") == 5
    assert next(c for c in s.state.cards.values() if c.name == "Test Sphinx").zone != "p1:battlefield"
    check(s)


def test_sphinx_accepts(cards):
    s = build(cards, ["Forest"] * 6 + ["Sphinx's Approach"] * 6 + ["Test Sphinx"])
    spell = to_hand(s, "Sphinx's Approach")
    to_graveyard(s, 4, "Sphinx's Approach")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    assert zone(s, spell) == "p1:exile"
    assert next(c for c in s.state.cards.values() if c.name == "Test Sphinx").zone == "p1:battlefield"
    check(s)
