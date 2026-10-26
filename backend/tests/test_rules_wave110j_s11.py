"""Wave 110J session 11: single-card wordings, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* 608.2h / 700.4: Bound's X is the number of colors the sacrificed creature last had; the spell then exiles itself instead of going to the graveyard.
"""

from __future__ import annotations

import pytest  # noqa: F401

from tests.game_helpers import act
from tests.wave9c_kit import build, mana
from tests.wave110j_kit import EXTRA, card_db, check, grave_new, hand_new, now, put_new, settle  # noqa: F401

BOUND = "Bound // Determined"


def _cast_bound(s, answers):
    c = hand_new(s, BOUND)
    mana(s, "p1", B=1, G=1, C=3)
    act(s, "p1", type="cast_spell", card_id=c.id, face=0)
    settle(s, answers=answers)
    return now(s, c)


def test_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(BOUND)).level == "FULL"


@pytest.mark.parametrize(("creature", "colors"), [("Grizzly Bears", 1), ("Rhox War Monk", 3)])
def test_returns_one_card_per_color_and_exiles_itself(cards, creature, colors):
    s = build(cards, [BOUND, creature, *["Forest"] * 4], [])
    victim = put_new(s, creature)
    back = [grave_new(s, "Forest") for _ in range(4)]
    ids = [b.id for b in back]
    spell = _cast_bound(s, [ids[:colors]])
    assert now(s, victim).zone.endswith(":graveyard")
    assert sum(now(s, b).zone.endswith(":hand") for b in back) == colors
    assert spell.zone == "p1:exile"
    check(s)
