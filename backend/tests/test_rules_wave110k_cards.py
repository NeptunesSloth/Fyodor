"""Wave 110K: single-card wordings, real Oracle text (tests/fixtures/wave110k_cards.json). Every scenario checks the replay and a save and a load.

* 602.2b, 118.3: Bullseye, Death Dealer's activation cost is a choice announced with the activation: sacrifice an artifact or discard a nonland card.
"""

from __future__ import annotations

import pytest

from tests.game_helpers import act
from tests.wave9c_kit import build, life
from tests.wave110k_kit import (  # noqa: F401
    EXTRA,
    activate,
    card_db,
    check,
    full,
    hand_new,
    mana,
    now,
    put_new,
    refused,
    settle,
)


def test_bullseye_is_full():
    assert full("Bullseye, Death Dealer")


def _ready(cards):
    """Bullseye in play (its enter trigger declined), a Sol Ring and a Grizzly Bears (a nonland card) as the cost's two sides."""
    s = build(cards, ["Bullseye, Death Dealer", "Sol Ring", "Grizzly Bears"])
    bull = put_new(s, "Bullseye, Death Dealer")
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    s.state.rules.controlled_since[bull.id].turn = 0
    return s, bull, put_new(s, "Sol Ring"), hand_new(s, "Grizzly Bears")


@pytest.mark.parametrize(("side", "zone_of_paid"), [(0, "ring"), (1, "bears")])
def test_bullseye_activation_cost_is_either_side(cards, side, zone_of_paid):
    s, bull, ring, bears = _ready(cards)
    mana(s, C=3)
    before = life(s, "p2")
    act(s, "p1", type="activate_ability", card_id=bull.id, ability=1, targets=["p2"],
        cost_choices=[{"component": 20, "cards": [f"either:{side}"]}])
    settle(s)
    assert life(s, "p2") == before - 2
    assert now(s, bull).tapped
    paid = {"ring": ring, "bears": bears}[zone_of_paid]
    kept = {"ring": bears, "bears": ring}[zone_of_paid]
    assert now(s, paid).zone.endswith(("graveyard",)) and not now(s, kept).zone.endswith("graveyard")
    check(s)


def test_bullseye_cannot_activate_without_either_side(cards):
    s, bull, ring, bears = _ready(cards)
    act(s, "p1", type="move", card_ids=[ring.id, bears.id], to={"zone": "exile"})
    mana(s, C=3)
    refused(s, "activation cost", bull, "{3}", targets=["p2"])
