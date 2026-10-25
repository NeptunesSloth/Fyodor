"""Wave 110C: Power Surge (500.1 the lands counted are the ones untapped as the turn began, before the untap step; 603.2 each player's upkeep)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import to_phase
from tests.wave110c_kit import answer, build, check, life, make_db, put, real

EXTRA = [real("Power Surge", "{R}{R}", 2, "Enchantment",
              "At the beginning of each player's upkeep, this enchantment deals X damage to that player, where X is the number of untapped lands they controlled "
              "at the beginning of this turn.", None, "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Power Surge")).level == "FULL"


def test_counts_lands_untapped_before_the_untap_step(cards):
    s = build(cards, ["Power Surge", "Forest", "Mountain"], ["Forest", "Island", "Swamp"])
    put(s, "Power Surge")
    mine = [put(s, "Forest"), put(s, "Mountain")]
    for n in ("Forest", "Island", "Swamp"):
        put(s, n, "p2")
    act(s, "p1", type="activate_ability", card_id=mine[0].id, ability=0)  # tapped as p1's turn 3 begins: not counted, though it untaps right after
    to_phase(s, "main1", 3)
    answer(s)
    assert (life(s, "p2"), life(s, "p1")) == (40 - 3, 40 - 1)
    check(s)
