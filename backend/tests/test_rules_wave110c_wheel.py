"""Wave 110C: Wheel of Sun and Moon (614.1a, 303.4): a card that would go to the enchanted player's graveyard is revealed and put on the bottom of their library."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, cast, check, make_db, mana, real

EXTRA = [real("Wheel of Sun and Moon", "{G}{W}", 2, "Enchantment — Aura", "Enchant player\nIf a card would be put into enchanted player's graveyard from anywhere, instead that card is revealed and put on the bottom of that player's library.", None, "GW")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Wheel of Sun and Moon")).level == "FULL"


@pytest.mark.parametrize("enchant, where", [("p2", "p2:library"), ("p1", "p2:graveyard")])
def test_dying_card_goes_to_bottom_of_library_only_for_the_enchanted_player(cards, enchant, where):
    s = build(cards, ["Wheel of Sun and Moon", "Lightning Bolt"], ["Grizzly Bears"])
    bears = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears")
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, G=1, W=1)
    cast(s, "Wheel of Sun and Moon", [enchant])
    answer(s)
    mana(s, R=1)
    cast(s, "Lightning Bolt", [bears.id])
    answer(s)
    assert s.state.cards[bears.id].zone == where
    if where == "p2:library":
        assert s.state.zones["p2:library"][-1] == bears.id
    check(s)
