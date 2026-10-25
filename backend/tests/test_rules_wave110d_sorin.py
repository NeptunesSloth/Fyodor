"""Wave 110D: Sorin, Ravenous Neonate, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 606.4, 613.1d, 700.9: "−6: Gain control of target creature. It becomes a Vampire in addition to its other types. Put a lifelink counter on it if you control
  a white permanent other than that creature or Sorin." — Sorin is white, so only another white permanent counts, and the stolen creature never does.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110d_kit import activate, card_db, ch, check, full, now, put, put_new, settle  # noqa: F401

SORIN = "Sorin of House Markov // Sorin, Ravenous Neonate"


def test_sorin_is_full():
    assert full(SORIN)


@pytest.mark.parametrize("mine,theirs,lifelink", [("Soul Warden", "Grizzly Bears", True), (None, "Grizzly Bears", False), (None, "Soul Warden", False)])
def test_minus_six_steals_and_gives_lifelink_only_with_another_white_permanent(cards, mine, theirs, lifelink):
    s = build(cards, [SORIN, *([mine] if mine else [])], [theirs])
    sorin = put(s, SORIN)
    act(s, "p1", type="set_face", card_id=sorin.id, face=1)
    act(s, "p1", type="counter", card_ids=[sorin.id], kind="loyalty", delta=6)
    if mine:
        put(s, mine)
    target = put(s, theirs, "p2")
    activate(s, sorin, "−6", targets=[target.id])
    settle(s)
    stolen = now(s, target)
    assert stolen.controller == "p1" and "Vampire" in ch(s, target).subtypes
    assert (stolen.counters.get("lifelink", 0) == 1) is lifelink
    check(s)
