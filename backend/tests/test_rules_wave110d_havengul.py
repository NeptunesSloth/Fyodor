"""Wave 110D: Havengul Laboratory // Havengul Mystery, real Oracle text (tests/fixtures/wave110d_cards.json).

* 701.28 transform at the end step after three Clues were sacrificed; the Mystery's transform trigger returns a creature card from the graveyard.
* 603.7a, 400.7: when that very creature leaves the battlefield the Mystery transforms (back to the Laboratory, 712.3).
"""

from __future__ import annotations

from tests.wave110d_kit import activate, build, card_db, cast_on, check, full, grave_new, mana, now, put_new, settle, to_phase  # noqa: F401

NAME = "Havengul Laboratory // Havengul Mystery"


def test_full():
    assert full(NAME)


def _mystery(cards, clues):
    s = build(cards, [NAME, "Thraben Inspector", "Thraben Inspector", "Thraben Inspector", "Grizzly Bears"], ["Murder"])
    lab = put_new(s, NAME)
    bears = grave_new(s, "Grizzly Bears")
    for _ in range(3):
        cast_on(s, "Thraben Inspector")
    for clue in [c for c in s.state.cards.values() if c.token and c.name == "Clue"][:clues]:
        mana(s, "p1", C=2)
        activate(s, clue, "{2}")
    to_phase(s, "end", turn=s.state.turn.number)
    settle(s)
    return s, lab, bears


def test_three_clues_transform_and_return_then_back(cards):
    s, lab, bears = _mystery(cards, 3)
    assert now(s, lab).face == 1 and now(s, bears).zone == "p1:battlefield"
    cast_on(s, "Murder", bears, pid="p2")
    assert now(s, bears).zone == "p1:graveyard" and now(s, lab).face == 0
    check(s)


def test_two_clues_do_nothing(cards):
    s, lab, bears = _mystery(cards, 2)
    assert now(s, lab).face == 0 and now(s, bears).zone == "p1:graveyard"
    check(s)
