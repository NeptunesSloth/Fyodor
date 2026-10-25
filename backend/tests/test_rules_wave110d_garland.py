"""Wave 110D: Garland, Royal Kidnapper, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 725.2, 611.2b, 613.1b: "Whenever an opponent becomes the monarch, gain control of target creature that player controls for as long as they're the monarch."
  — control lasts exactly while that opponent is the monarch; it reverts when another player takes the crown.
"""

from __future__ import annotations

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import card_db, check, full, mana, now, put_new, settle, to_hand, to_phase  # noqa: F401


def test_garland_is_full():
    assert full("Garland, Royal Kidnapper")


def opponent_crowned(cards):
    s = build(cards, ["Garland, Royal Kidnapper", "Thorn of the Black Rose"], ["Thorn of the Black Rose", "Grizzly Bears"] + ["Forest"] * 12)
    put_new(s, "Garland, Royal Kidnapper")
    bears = put_new(s, "Grizzly Bears", "p2")
    to_phase(s, "main1", turn=2)
    thorn = to_hand(s, "Thorn of the Black Rose", "p2")
    mana(s, "p2", B=1, C=3)
    act(s, "p2", type="cast_spell", card_id=thorn.id)
    settle(s, answers=[bears.id])  # (the target: Bob's Bears, not the Thorn)
    return s, bears


def test_steals_while_they_are_monarch_then_returns(cards):
    s, bears = opponent_crowned(cards)
    assert s.state.table.monarch == "p2" and now(s, bears).controller == "p1"
    to_phase(s, "main1", turn=3)
    thorn = to_hand(s, "Thorn of the Black Rose")
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=thorn.id)
    settle(s)
    assert s.state.table.monarch == "p1" and now(s, bears).controller == "p2"
    check(s)


def test_still_stolen_while_monarch(cards):
    s, bears = opponent_crowned(cards)
    assert s.state.table.monarch == "p2" and now(s, bears).controller == "p1"
    check(s)
