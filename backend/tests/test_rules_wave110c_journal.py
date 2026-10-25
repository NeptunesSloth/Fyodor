"""Wave 110C: The Tomb of Aclazotz (back of Tarrian's Journal): one creature spell from the graveyard this turn (601.3), it enters with a finality counter (122.6) and is a Vampire in addition to its other types (205.1b, 613.1d)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, ch, check, make_db, mana, put, real, to_graveyard

TEXT = ("{T}: Add {B}.\n{T}: You may cast a creature spell from your graveyard this turn. If you do, it enters with a finality counter on it and is a Vampire in addition "
        "to its other types. (If a creature with a finality counter on it would die, exile it instead.)")
EXTRA = [real("The Tomb of Aclazotz", "", 0, "Legendary Land", TEXT)]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("The Tomb of Aclazotz")).level == "FULL"


def _go(cards):
    s = build(cards, ["The Tomb of Aclazotz", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"])
    tomb = put(s, "The Tomb of Aclazotz")
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
