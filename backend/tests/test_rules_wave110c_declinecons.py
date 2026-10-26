"""Wave 110C: the Decline candidate (614.1a, 616.1) in the other zone_candidates consumers: mill (701.17) and a sacrifice cost (118.3, 701.21)."""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.test_rules_wave110c_discard import ACADEMY, LENG, SLIVER, _settle
from tests.wave110c_kit import build, mana, put, real, to_hand

EXTRA = [real("Library of Leng", "{1}", 1, "Artifact", LENG, None, ""),
         real("Nephalia Academy", "", 0, "Land", ACADEMY, None, ""),
         real("Pulmonic Sliver", "{3}{W}{W}", 5, "Creature — Sliver", SLIVER, ("3", "3"), "W"),
         real("Slag Idol", "{1}", 1, "Artifact", "Sacrifice a creature: You gain 2 life.", None, ""),
         real("Mill Three", "{U}", 1, "Sorcery", "Target player mills three cards.", None, "U")]


@pytest.fixture()
def card_db(settings):
    from tests.wave110c_kit import make_db

    return make_db(settings, EXTRA)


def test_mill_ignores_optional_replacements(cards):
    s = build(cards, ["Library of Leng", "Pulmonic Sliver", "Mill Three", "Forest", "Forest", "Forest", "Forest"])
    put(s, "Library of Leng"), put(s, "Pulmonic Sliver")
    c = to_hand(s, "Mill Three")
    mana(s, U=1)
    before = len(s.state.zones["p1:graveyard"])
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p1"])
    assert _settle(s, True) == 0
    assert len(s.state.zones["p1:graveyard"]) == before + 4  # three milled + the spell


@pytest.mark.parametrize("take", [True, False])
def test_sacrifice_cost_with_optional_replacement(cards, take):
    s = build(cards, ["Slag Idol", "Pulmonic Sliver"])
    idol, sl = put(s, "Slag Idol"), put(s, "Pulmonic Sliver")
    act(s, "p1", type="activate_ability", card_id=idol.id, ability=0)
    assert _settle(s, take) == 1
    assert s.state.cards[sl.id].zone == ("p1:library" if take else "p1:graveyard")
