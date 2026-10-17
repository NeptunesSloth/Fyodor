"""Wave 45A: "Lands you control enter untapped" / "Gates you control enter untapped" (CR 2026-09-25), real Oracle text (tests/fixtures/wave45a_cards.json, from
data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 614.1d, 614.12, 616.1: Horizon Explorer [1766], The Wandering Minstrel [5928], Gond Gate [2652] - a replacement effect on the entering of the lands (the Gates) its
  controller controls: they enter untapped. Horizon Explorer's ruling 2025-07-25: a land put onto the battlefield tapped by an instruction (no replacement effect)
  always enters untapped; against a land's own "enters tapped" its controller chooses the order, so can have either. Modelled as the controller always choosing
  untapped (a payoff for entering tapped isn't modelled, ponytail: it is never a land that wants to be tapped here); a shock land asks nothing.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, check, put, to_hand
from tests.wave45a_kit import FULL, cast, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def land(s, name, pid="p1"):
    c = to_hand(s, name, pid)
    act(s, pid, type="play_land", card_id=c.id)
    return s.state.cards[c.id]


@pytest.mark.parametrize("name", ["Blossoming Sands", "Dimir Guildgate", "Steam Vents"])
def test_horizon_explorer_makes_every_land_you_control_enter_untapped(cards, name):
    s = build(cards, ["Horizon Explorer", name], [])
    put(s, "Horizon Explorer")
    assert not land(s, name).tapped  # its own "enters tapped" (614.12), or a shock land's unpaid life: untapped (no question asked)
    check(s)


def test_horizon_explorer_does_not_untap_a_land_an_opponent_controls(cards):
    s = build(cards, ["Horizon Explorer"], ["Blossoming Sands"])
    put(s, "Horizon Explorer")
    act(s, "p1", type="pass_priority")
    c = to_hand(s, "Blossoming Sands", "p2")
    act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    assert s.state.cards[c.id].tapped  # "Lands you control": Bob's lands are his own
    check(s)


def test_horizon_explorer_makes_a_land_an_effect_puts_onto_the_battlefield_tapped_enter_untapped(cards):
    s = build(cards, ["Horizon Explorer", "Cultivate"], [], forests=20)
    put(s, "Horizon Explorer")
    to_hand(s, "Cultivate")
    from tests.wave9c_kit import mana

    mana(s, G=1, C=2)
    cast(s, "Cultivate")
    from tests.test_rules_wave34b_activated import settle

    settle(s)
    lands = [c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Forest"]
    assert len(lands) == 1 and not s.state.cards[lands[0]].tapped  # the ruling: no replacement effect is applied to "put it onto the battlefield tapped"
    check(s)


def test_gond_gate_untaps_only_gates(cards):
    s = build(cards, ["Gond Gate", "Dimir Guildgate", "Blossoming Sands"], [])
    put(s, "Gond Gate")
    assert not land(s, "Dimir Guildgate").tapped
    # one land a turn: the second is the Sands, a land but no Gate - it stays tapped. (A second land drop needs another turn.)
    check(s)


def test_gond_gate_leaves_a_land_that_is_not_a_gate_tapped(cards):
    s = build(cards, ["Gond Gate", "Blossoming Sands"], [])
    put(s, "Gond Gate")
    assert land(s, "Blossoming Sands").tapped
    check(s)


def test_the_wandering_minstrel_makes_lands_enter_untapped(cards):
    s = build(cards, ["The Wandering Minstrel", "Dimir Guildgate"], [])
    put(s, "The Wandering Minstrel")
    assert not land(s, "Dimir Guildgate").tapped
    check(s)
