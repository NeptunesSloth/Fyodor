"""Wave 110J: single-card wordings, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario checks the replay and a save and a load.

* 613.4c, 107.1a: Aspect of Wolf gives +X/+Y, X half the Forests its controller has (rounded down), Y half of them (rounded up).
* 611.2a, 305.7, 502.3: Orcish Farmer makes a land a Swamp until its controller's next untap step — the land's controller, not the Farmer's.
"""

from __future__ import annotations

import pytest

from tests.wave9c_kit import build
from tests.wave110j_kit import EXTRA, activate, card_db, cast_on, ch, check, full, put, put_new, to_phase  # noqa: F401


@pytest.mark.parametrize("name", ["Aspect of Wolf", "Orcish Farmer"])
def test_the_cards_are_full(name):
    assert full(name)


@pytest.mark.parametrize(("forests", "bonus"), [(0, (0, 0)), (1, (0, 1)), (4, (2, 2)), (5, (2, 3))])
def test_aspect_of_wolf_rounds_each_half_its_own_way(cards, forests, bonus):
    s = build(cards, ["Aspect of Wolf", "Templar Knight"])
    knight = put_new(s, "Templar Knight")
    for _ in range(forests):
        put_new(s, "Forest")
    base = ch(s, knight).pt
    cast_on(s, "Aspect of Wolf", knight)
    assert tuple(int(a) - int(b) for a, b in zip(ch(s, knight).pt, base, strict=True)) == bonus
    check(s)


def ready(s, c):
    s.state.rules.controlled_since[c.id].turn = 0


def types(s, c):
    return set(ch(s, c).subtypes)


@pytest.mark.parametrize(("owner", "still_a_swamp_on_turn_2"), [("p2", False), ("p1", True)])
def test_orcish_farmer_lasts_until_the_lands_controllers_next_untap_step(cards, owner, still_a_swamp_on_turn_2):
    s = build(cards, ["Orcish Farmer"])
    farmer = put(s, "Orcish Farmer")
    ready(s, farmer)
    land = put_new(s, "Island" if owner == "p2" else "Forest", owner)
    base = types(s, land)
    activate(s, farmer, "{T}", targets=[land.id])
    assert types(s, land) == {"Swamp"} and base != {"Swamp"}
    to_phase(s, "main1", turn=2)
    assert (types(s, land) == {"Swamp"}) is still_a_swamp_on_turn_2
    to_phase(s, "main1", turn=3)
    assert types(s, land) == base
    check(s)
