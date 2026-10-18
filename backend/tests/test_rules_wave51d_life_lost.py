"""Wave 51D: "If you lost life this way, draw that many cards." after an exchange of life totals (CR 2026-09-25), real Oracle text (tests/fixtures/wave51d_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 701.12c / 119.3: Mister Negative - "you may exchange life totals with target opponent. If you lost life this way, draw that many cards." The player with the higher total
  loses the difference; the cards are what the controller really lost (none when they gained, or when they declined).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, check, life, mana, reloaded, to_hand
from tests.wave51d_kit import open_repo

NEGATIVE = "Mister Negative"

@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def test_the_card_is_full(cards):
    assert coverage.of_card_data(cards.resolve(NEGATIVE)).level == "FULL"


def hand(s):
    return len([c for c in s.state.cards.values() if c.zone == "p1:hand"])


def enter(cards, mine, theirs, answer):
    s = build(cards, [NEGATIVE], forests=30)
    act(s, "p1", type="set_life", player="p1", value=mine)
    act(s, "p1", type="set_life", player="p2", value=theirs)
    to_hand(s, NEGATIVE)
    mana(s, "p1", W=1, B=1, G=5)
    before = hand(s)
    act(s, "p1", type="cast_spell", card_id=next(c.id for c in s.state.cards.values() if c.name == NEGATIVE and c.zone == "p1:hand"))
    for _ in range(30):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
            continue
        ids = [o.id for o in d.options]
        pick = [answer] if answer in ids else [i for i in ids if i == "p2"][:1] or ids[:1]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
    return s, before


def test_mister_negative_draws_as_many_cards_as_the_life_it_lost(cards):
    s, before = enter(cards, 25, 20, "yes")
    assert (life(s, "p1"), life(s, "p2")) == (20, 25)
    assert hand(s) == before - 1 + 5  # the spell left the hand; the exchange cost 5 life: five cards
    check(s)
    assert life(reloaded(s), "p1") == 20


def test_mister_negative_draws_nothing_when_it_gains_life(cards):
    s, before = enter(cards, 20, 25, "yes")
    assert (life(s, "p1"), life(s, "p2")) == (25, 20)
    assert hand(s) == before - 1
    check(s)


def test_mister_negative_declined_changes_nothing(cards):
    s, before = enter(cards, 25, 20, "no")
    assert (life(s, "p1"), life(s, "p2")) == (25, 20) and hand(s) == before - 1
    check(s)
