"""Wave 110C: Valentin, Dean of the Vein (614.1a, 603.12): the exile replacement with a reflexive "you may pay {2}. If you do, create a Pest"."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, put, real

TEXT = ("Menace, lifelink\nIf a nontoken creature an opponent controls would die, exile it instead. When you do, you may pay {2}. If you do, create a 1/1 "
        "black and green Pest creature token with \"When this token dies, you gain 1 life.\"")
EXTRA = [real("Valentin, Dean of the Vein", "{1}{B}", 2, "Legendary Creature — Human Warlock", TEXT, ("2", "2"), "B")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Valentin, Dean of the Vein")).level == "FULL"


@pytest.mark.parametrize("pay", [True, False])
def test_opponent_creature_exiled_then_optional_pest(cards, pay):
    s = build(cards, ["Valentin, Dean of the Vein", "Lightning Bolt"], ["Grizzly Bears"])
    put(s, "Valentin, Dean of the Vein")
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, R=1, C=2 if pay else 0)
    cast(s, "Lightning Bolt", [bears.id])
    answer(s, *(["pay"] if pay else ["decline"]))
    assert s.state.cards[bears.id].zone == "p2:exile"
    pests = [c for c in s.state.cards.values() if c.name == "Pest" and c.zone == "p1:battlefield"]
    assert len(pests) == (1 if pay else 0)
    check(s)
