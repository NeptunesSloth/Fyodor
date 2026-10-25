"""Wave 110A (session 7): real Oracle text cards (tests/fixtures/wave110a_cards.json), each scenario checks replay and save/load.

* Cut Short - "Destroy target planeswalker that was activated this turn or tapped creature." (606: a loyalty ability of it was activated).
* Bioshift - "Move any number of +1/+1 counters from target creature onto another target creature with the same controller." (115.7e-style
  relation: the second target is a creature its controller controls, bound from the first; 122.6 counters moved).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110a_kit import *

CUT, SHIFT = "Cut Short", "Bioshift"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([CUT, SHIFT])


@pytest.mark.parametrize("used", [True, False])
def test_cut_short_planeswalker_only_if_activated(cards, used):
    s = build(cards, [CUT, "Xenagos, the Reveler"])
    xen = put(s, "Xenagos, the Reveler")
    if used:
        act(s, "p1", type="activate_ability", card_id=xen.id, ability=0)
        answer(s)
        cast(s, CUT, [xen.id])
        answer(s)
        assert zone_of(s, "Xenagos, the Reveler") == "p1:graveyard"
        check(s)
    else:
        with pytest.raises(ActionError):
            cast(s, CUT, [xen.id])


@pytest.mark.parametrize("tapped", [True, False])
def test_cut_short_creature_only_if_tapped(cards, tapped):
    s = build(cards, [CUT, "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    if tapped:
        s.state.cards[bears.id].tapped = True
        cast(s, CUT, [bears.id])
        answer(s)
        assert zone_of(s, "Grizzly Bears") == "p1:graveyard"
        check(s)
    else:
        with pytest.raises(ActionError):
            cast(s, CUT, [bears.id])


def counters(s, c):
    return s.state.cards[c.id].counters.get("+1/+1", 0)


@pytest.mark.parametrize("theirs", [False, True])
def test_bioshift_same_controller_only(cards, theirs):
    s = build(cards, [SHIFT, "Grizzly Bears", "Hill Giant"], theirs=["Hill Giant"])
    a, b = put(s, "Grizzly Bears"), put(s, "Hill Giant", "p2" if theirs else "p1")
    act(s, "p1", type="counter", card_ids=[a.id], kind="+1/+1", delta=3)
    mana(s, G=1)
    if theirs:
        with pytest.raises(ActionError):
            cast(s, SHIFT, [a.id, b.id], pay=False, target_counts=[1, 1])
        return
    cast(s, SHIFT, [a.id, b.id], pay=False, target_counts=[1, 1])
    answer(s)
    check(s)
    assert counters(s, a) + counters(s, b) == 3
