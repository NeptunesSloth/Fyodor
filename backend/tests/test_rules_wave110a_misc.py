"""Wave 110A (session 7): real Oracle text cards (tests/fixtures/wave110a_cards.json), each scenario checks replay and save/load.

* Cut Short - "Destroy target planeswalker that was activated this turn or tapped creature." (606: a loyalty ability of it was activated).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110a_kit import *

CUT = "Cut Short"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([CUT])


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
        setattr(s.state.cards[bears.id], "tapped", True)
        cast(s, CUT, [bears.id])
        answer(s)
        assert zone_of(s, "Grizzly Bears") == "p1:graveyard"
        check(s)
    else:
        with pytest.raises(ActionError):
            cast(s, CUT, [bears.id])
