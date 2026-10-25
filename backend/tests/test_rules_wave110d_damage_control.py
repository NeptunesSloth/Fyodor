"""Wave 110D: Call Damage Control, real Oracle text.

* 700.2: "Choose up to two." with the common instruction "Return those cards from your graveyard to your hand." and a targeted card per mode.
* 601.2c: one target per chosen mode; 608.2b: only the legal ones are returned.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave110d_kit import build, card_db, check, cost, full, grave_new, hand_new, mana, settle  # noqa: F401

NAME = "Call Damage Control"


def test_full():
    assert full(NAME)


@pytest.mark.parametrize("modes, back", [([1, 3], ["Grizzly Bears", "Forest"]), ([1], ["Grizzly Bears"])])
def test_up_to_two_cards_come_back(cards, modes, back):
    s = build(cards, [NAME, "Grizzly Bears", "Forest"])
    bear, land = grave_new(s, "Grizzly Bears"), grave_new(s, "Forest")
    picks = {"Grizzly Bears": bear, "Forest": land}
    spell = hand_new(s, NAME)
    mana(s, "p1", **cost(NAME))
    act(s, "p1", type="cast_spell", card_id=spell.id, modes=modes, targets=[picks[n].id for n in back])
    settle(s)
    assert {n: s.state.cards[c.id].zone for n, c in picks.items()} == {n: "p1:hand" if n in back else "p1:graveyard" for n in picks}
    check(s)
