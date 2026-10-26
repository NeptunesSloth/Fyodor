"""Wave 110I (session 8): real Oracle text; scenarios check replay and save/load.

* Arsenal Thresher: reveals other artifact cards from hand as it enters (701.20a), a +1/+1 counter for each (614.12); the cards stay in hand.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named, mana, put, to_hand
from tests.wave110a_kit import answer
from tests.wave110c_kit import check, make_db

THRESHER = ("As this creature enters, you may reveal any number of other artifact cards from your hand. "
            "This creature enters with a +1/+1 counter on it for each card revealed this way.")
EXTRA = [real("Arsenal Thresher", "{2}{W/B}{U}", 4, "Artifact Creature — Construct", THRESHER, ("2", "2"), "BUW"),
         real("Probe Gem1", "{1}", 1, "Artifact", "", None, ""), real("Probe Gem2", "{2}", 2, "Artifact", "", None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


@pytest.mark.parametrize("name", ["Arsenal Thresher"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("reveal", [2, 1, 0])
def test_thresher_counters_per_revealed_artifact(cards, reveal):
    s = build(cards, ["Arsenal Thresher", "Probe Gem1", "Probe Gem2", "Forest"])
    gems = [to_hand(s, "Probe Gem1"), to_hand(s, "Probe Gem2")]
    forest = to_hand(s, "Forest")
    mana(s, W=1, U=1, C=2)
    t = to_hand(s, "Arsenal Thresher")
    act(s, "p1", type="cast_spell", card_id=t.id)
    d = None
    for _ in range(6):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and {o.card_id for o in d.options} >= {g.id for g in gems} and forest.id not in {o.card_id for o in d.options}
    for g in gems[:reveal]:
        act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=[next(o.id for o in s.state.rules.decision.options if o.card_id == g.id)])
    if reveal < 2:
        act(s, "p1", type="choose", decision_id=s.state.rules.decision.id, option_ids=["done"])
    answer(s)
    got = s.state.cards[t.id]
    assert got.zone == "p1:battlefield" and got.counters.get("+1/+1", 0) == reveal
    assert all(s.state.cards[g.id].zone == "p1:hand" for g in gems)
    check(s)
