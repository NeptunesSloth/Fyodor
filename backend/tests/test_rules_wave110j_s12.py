"""Wave 110J session 12, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* Paliano, the High City: 905.2 / 103.6 and the 2014-05-29 ruling: without a draft no color was chosen, so its mana ability taps for no mana (not even colorless).
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110j_kit import EXTRA, card_db, check, now, put_new, settle  # noqa: F401

PALIANO = "Paliano, the High City"


def test_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(PALIANO)).level == "FULL"


def test_paliano_taps_for_no_mana(cards):
    s = build(cards, [PALIANO])
    p = put_new(s, PALIANO)
    act(s, "p1", type="activate_ability", card_id=p.id, ability=1)
    settle(s)
    assert now(s, p).tapped and s.state.players["p1"].mana == {} and not s.state.players["p1"].mana_units
    check(s)
