"""Wave 110N: Robber of the Rich (508.1 attack trigger with an intervening if, 601.3 the cast only in a turn a Rogue attacked, 106.8 mana of any color)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

ROBBER = "Robber of the Rich"


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, [])


test_full = full_test([ROBBER])


def start(cards, bob_hand):
    s = build(cards, [ROBBER], ["Lightning Bolt"])
    robber = put(s, ROBBER)
    for c in [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][:bob_hand]:
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "hand"})
    next_turn(s)  # (each player has drawn one card by now)
    act(s, "p2", type="move", card_ids=[card_named(s, "Lightning Bolt", "p2").id], to={"player": "p2", "zone": "library"}, position="top")
    return s, robber


def attack(s, robber):
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": robber.id, "target": "p2"}])
    answer(s)


@pytest.mark.parametrize(("bob_hand", "exiled"), [(2, True), (1, False)])  # (Bob drew the Bolt, which goes back on top: his hand is these Islands)
def test_exiles_the_top_card_only_if_the_defender_has_more_cards_in_hand(cards, bob_hand, exiled):
    s, robber = start(cards, bob_hand)
    stops(s)
    attack(s, robber)
    assert (zone_of(s, "Lightning Bolt", "p2") == "p2:exile") is exiled
    check(s)


def test_the_exiled_card_can_be_cast_with_any_color_mana_in_a_turn_a_rogue_attacked(cards):
    s, robber = start(cards, 2)
    stops(s)
    attack(s, robber)
    bolt = card_named(s, "Lightning Bolt", "p2")
    mana(s, "p1", G=1)  # green mana for {R}
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"], free=False)
    answer(s)
    assert zone_of(s, "Lightning Bolt", "p2") == "p2:graveyard" and life(s, "p2") == 37
    check(s)


def test_it_cannot_be_cast_in_a_turn_no_rogue_attacked(cards):
    s, robber = start(cards, 2)
    stops(s)
    attack(s, robber)
    to_phase(s, "main1", turn=s.state.turn.number + 2)
    mana(s, "p1", R=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt", "p2").id, targets=["p2"])
    check(s)
