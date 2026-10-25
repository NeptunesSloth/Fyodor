"""Wave 110D: Shallow Grave, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 404.1, 400.7, 603.7: "Return the top creature card of your graveyard to the battlefield. That creature gains haste until end of turn. Exile it at the
  beginning of the next end step." — the last creature card put into the graveyard (not a target), exiled at the next end step.
"""

from __future__ import annotations

from tests.wave9c_kit import build
from tests.wave110d_kit import card_db, cast_on, ch, check, full, grave_new, now, settle, to_phase  # noqa: F401


def test_shallow_grave_is_full():
    assert full("Shallow Grave")


def test_top_creature_returns_with_haste_then_exiled(cards):
    s = build(cards, ["Shallow Grave", "Grizzly Bears", "Llanowar Elves", "Forest"] + ["Forest"] * 12, ["Forest"] * 12)
    old, top = grave_new(s, "Grizzly Bears"), grave_new(s, "Llanowar Elves")
    grave_new(s, "Forest")  # (a land on top is skipped: only a creature card counts)
    cast_on(s, "Shallow Grave")
    settle(s)
    assert now(s, top).zone == "p1:battlefield" and now(s, old).zone == "p1:graveyard"
    assert "haste" in ch(s, top).keywords
    to_phase(s, "main1", turn=2)
    assert now(s, top).zone == "p1:exile"
    check(s)


def test_no_creature_nothing(cards):
    s = build(cards, ["Shallow Grave", "Forest"])
    land = grave_new(s, "Forest")
    cast_on(s, "Shallow Grave")
    settle(s)
    assert now(s, land).zone == "p1:graveyard"
    check(s)
