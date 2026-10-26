"""Wave 110J session 7: single-card wordings, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* 500.1, 603.4, 122.1: Rasputin Dreamweaver gets a dream counter at the upkeep only if it was untapped as the turn began (before the untap step).
* 614.17: Rasputin Dreamweaver can't have more than seven dream counters, however many are put.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110j_kit import EXTRA, card_db, check, full, now, put_new, to_phase  # noqa: F401

RASPUTIN = "Rasputin Dreamweaver"


def test_the_cards_are_full():
    assert full(RASPUTIN)


@pytest.mark.parametrize(("before", "tap_on_turn_2", "after"), [(5, False, 6), (5, True, 5), (7, False, 7)])
def test_rasputin_upkeep_counter(cards, before, tap_on_turn_2, after):
    """Untapped as the turn began: +1 dream counter, capped at seven; tapped as it began (it untaps afterwards): none."""
    s = build(cards, [RASPUTIN])
    r = put_new(s, RASPUTIN)
    act(s, "p1", type="counter", card_ids=[r.id], kind="dream", delta=before - now(s, r).counters.get("dream", 0))
    to_phase(s, "main1", turn=2)
    if tap_on_turn_2:
        act(s, "p1", type="tap", card_ids=[r.id])
    to_phase(s, "main1", turn=3)
    assert now(s, r).counters.get("dream", 0) == after and not now(s, r).tapped
    check(s)

