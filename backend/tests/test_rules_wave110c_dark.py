"""Wave 110C: Dark Intimations. 701.21 (edict, their choice), 701.9 (discard), 603.3 / 601.2i (a graveyard cast trigger), 614.1c / 122.1 (enters with an
additional loyalty counter), 113.6k-style functioning only from the graveyard."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, card_named, cast, check, make_db, mana, put, real, zone

DARK = ("Each opponent sacrifices a creature or planeswalker of their choice, then discards a card. You return a creature or planeswalker card from "
        "your graveyard to your hand, then draw a card.\nWhen you cast a Bolas planeswalker spell, exile this card from your graveyard. That planeswalker "
        "enters with an additional loyalty counter on it.")
EXTRA = [real("Dark Intimations", "{2}{U}{B}{R}", 5, "Sorcery", DARK, None, "UBR"),
         card("Test Bolas", set_code="tst", number="110C-B", mana_cost="{1}", cmc=1.0, type_line="Legendary Planeswalker — Bolas", oracle_text="", loyalty="3",
              colors=["B"], color_identity=["B"], keywords=[]),
         card("Test Jace", set_code="tst", number="110C-J", mana_cost="{1}", cmc=1.0, type_line="Legendary Planeswalker — Jace", oracle_text="", loyalty="3",
              colors=["U"], color_identity=["U"], keywords=[]),
         real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
         real("Test Victim", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Dark Intimations")).level == "FULL"


def _grave(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "graveyard"})
    return c


def test_spell_edict_discard_return_draw(cards):
    s = build(cards, ["Dark Intimations", "Test Bear"], ["Test Victim", "Test Victim"])
    bear = _grave(s, "Test Bear")
    put(s, "Test Victim", "p2")
    spare = next(c for c in s.state.cards.values() if c.name == "Test Victim" and c.zone == "p2:library")
    act(s, "p2", type="move", card_ids=[spare.id], to={"zone": "hand"})
    mana(s, U=1, B=1, R=1, C=2)
    cast(s, "Dark Intimations")
    answer(s)
    assert zone(s, bear) == "p1:hand"
    assert not any(c.name == "Test Victim" and c.zone == "p2:battlefield" for c in s.state.cards.values())
    assert not any(c.name == "Test Victim" and c.zone == "p2:hand" for c in s.state.cards.values())
    check(s)


def test_bolas_spell_gets_extra_loyalty_and_card_is_exiled(cards):
    s = build(cards, ["Dark Intimations", "Test Bolas"])
    dark = _grave(s, "Dark Intimations")
    mana(s, C=1)
    cast(s, "Test Bolas")
    answer(s)
    assert zone(s, dark) == "p1:exile"
    assert card_named(s, "Test Bolas").counters.get("loyalty") == 4
    check(s)


def test_other_planeswalker_does_nothing(cards):
    s = build(cards, ["Dark Intimations", "Test Jace"])
    dark = _grave(s, "Dark Intimations")
    mana(s, C=1)
    cast(s, "Test Jace")
    answer(s)
    assert zone(s, dark) == "p1:graveyard"
    assert card_named(s, "Test Jace").counters.get("loyalty") == 3


def test_in_hand_it_does_not_trigger(cards):
    s = build(cards, ["Dark Intimations", "Test Bolas"])
    mana(s, C=1)
    cast(s, "Test Bolas")
    answer(s)
    assert card_named(s, "Test Bolas").counters.get("loyalty") == 3
