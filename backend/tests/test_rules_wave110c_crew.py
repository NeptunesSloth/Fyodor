"""Wave 110C: Reckless Crew (111.1, 701.3a): X tokens by Vehicles plus Equipment; each token may get an Equipment attached."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, real

TEXT = "Create X 2/1 red Dwarf Berserker creature tokens, where X is the number of Vehicles you control plus the number of Equipment you control. For each of those tokens, you may attach an Equipment you control to it."
EXTRA = [real("Reckless Crew", "{3}{R}", 4, "Sorcery", TEXT, None, "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Reckless Crew")).level == "FULL"


@pytest.mark.parametrize("attach", [True, False])
def test_one_equipment_makes_one_token_that_may_carry_it(cards, attach):
    s = build(cards, ["Reckless Crew", "Bonesplitter"], [])
    sword = put(s, "Bonesplitter")
    mana(s, R=1, C=3)
    cast(s, "Reckless Crew")
    answer(s, sword.id if attach else [])
    toks = [c for c in s.state.cards.values() if c.token is not None and c.zone == "p1:battlefield"]
    assert len(toks) == 1 and toks[0].name == "Dwarf Berserker"
    assert (s.state.cards[sword.id].attached_to == toks[0].id) == attach
    check(s)
