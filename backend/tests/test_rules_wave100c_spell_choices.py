"""Wave 100C: choices made as a spell resolves, modal spells and the stack (app/rules/static_spell100c.py), real Oracle text
(tests/fixtures/wave100c_static_spells_cards.json; CR 2026-09-25). Every scenario checks the replay and a save and a load.

* 608.2c: "the creature type / color of your choice" is chosen as the spell resolves, then the instruction reads it.
* 514.3a: a delayed trigger "at the beginning of the next cleanup step" (the tokens survive the end step).
* 502.3: "Creatures don't untap during target player's next untap step": that player's creatures, in that untap step only.
* 701.6a / 113.1a: "Counter all other spells" counters spells only; "Exile all other spells and counter all abilities" exiles even a spell that
  can't be countered, then counters the activated and triggered abilities on the stack.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, check
from tests.wave100c_kit import cast, move, named, open_repo, pt_of, put_on, settle, start_cast, to_phase, zone

PROMOTED = ["Extinction", "Wash Out", "Din of the Fireherd", "Waylay", "Blinding Beam", "Reverse the Polarity", "Summary Dismissal"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", PROMOTED)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_extinction_destroys_every_creature_of_the_chosen_type(cards):
    """Extinction: "Destroy all creatures of the creature type of your choice." Bears of both players go; a Goblin stays."""
    s = build(cards, ["Extinction", "Grizzly Bears", "Mardu Scout"], ["Grizzly Bears"])
    bear, goblin, theirs = put_on(s, "Grizzly Bears"), put_on(s, "Mardu Scout"), put_on(s, "Grizzly Bears", "p2")
    cast(s, "Extinction", prefer=["Bear"], B=1, C=4)
    assert zone(s, bear) == "p1:graveyard" and zone(s, theirs) == "p2:graveyard" and zone(s, goblin) == "p1:battlefield"
    check(s)


def test_wash_out_returns_every_permanent_of_the_chosen_color(cards):
    """Wash Out: "Return all permanents of the color of your choice to their owners' hands." Green chosen: the white creature stays."""
    s = build(cards, ["Wash Out", "Grizzly Bears", "Benalish Hero"], ["Llanowar Elves"])
    bear, hero, elves = put_on(s, "Grizzly Bears"), put_on(s, "Benalish Hero"), put_on(s, "Llanowar Elves", "p2")
    cast(s, "Wash Out", prefer=["G", "green", "Green"], U=1, C=3)
    assert zone(s, bear) == "p1:hand" and zone(s, elves) == "p2:hand" and zone(s, hero) == "p1:battlefield"
    check(s)


def test_din_of_the_fireherd_counts_the_new_token_for_both_sacrifices(cards):
    """Din of the Fireherd: the 5/5 black and red token comes first; Alice then controls two black creatures (with Twisted Abomination) and
    two red ones (with Hulking Cyclops): Bob sacrifices two creatures, then two lands."""
    s = build(cards, ["Din of the Fireherd", "Twisted Abomination", "Hulking Cyclops"], ["Grizzly Bears", "Llanowar Elves", "Benalish Hero"])
    put_on(s, "Twisted Abomination"), put_on(s, "Hulking Cyclops")
    creatures = [put_on(s, n, "p2") for n in ("Grizzly Bears", "Llanowar Elves", "Benalish Hero")]
    lands = [move(s, c, "battlefield") for c in named(s, "Island", "p2")[:3]]
    cast(s, "Din of the Fireherd", targets=["p2"], B=3, C=5)
    assert sum(zone(s, c) == "p2:graveyard" for c in creatures) == 2
    assert sum(zone(s, c) == "p2:graveyard" for c in lands) == 2
    check(s)


def test_waylay_knights_survive_the_end_step_and_are_exiled_in_the_cleanup_step(cards):
    """Waylay: "Create three 2/2 white Knight creature tokens. Exile them at the beginning of the next cleanup step." """
    s = build(cards, ["Waylay"], [])
    act(s, "p1", type="set_stops", own=["end"], others=["main1"], smart_pass=False)
    cast(s, "Waylay", W=1, C=2)
    knights = [c for c in s.state.cards.values() if c.name == "Knight" and c.zone == "p1:battlefield"]
    assert len(knights) == 3
    to_phase(s, "end", turn=1)
    assert all(s.state.cards[k.id].zone == "p1:battlefield" for k in knights if k.id in s.state.cards)
    to_phase(s, "main1", turn=2)
    assert not [c for c in s.state.cards.values() if c.name == "Knight" and c.zone.endswith(":battlefield")]
    check(s)


def test_blinding_beam_entwined_taps_two_and_keeps_that_players_creatures_tapped_once(cards):
    """Blinding Beam with entwine: "Tap two target creatures." and "Creatures don't untap during target player's next untap step." Bob's
    creatures stay tapped in his next untap step (turn 2) and untap in the one after (turn 4)."""
    s = build(cards, ["Blinding Beam"], ["Grizzly Bears", "Llanowar Elves"])
    bear, elves = put_on(s, "Grizzly Bears", "p2"), put_on(s, "Llanowar Elves", "p2")
    act(s, "p1", type="set_stops", own=[], others=["main1"], smart_pass=False)
    cast(s, "Blinding Beam", targets=[bear.id, elves.id, "p2"], target_counts=[2, 1], modes=[0, 1], kicker=1, W=1, C=3)
    assert s.state.cards[bear.id].tapped and s.state.cards[elves.id].tapped
    to_phase(s, "main1", turn=2)
    assert s.state.cards[bear.id].tapped and s.state.cards[elves.id].tapped
    to_phase(s, "main1", turn=4)
    assert not s.state.cards[bear.id].tapped and not s.state.cards[elves.id].tapped
    check(s)


def test_reverse_the_polarity_counters_the_other_spells(cards):
    """Reverse the Polarity, mode 1: "Counter all other spells." Alice's Opt below it is countered."""
    s = build(cards, ["Reverse the Polarity", "Opt"], [])
    act(s, "p1", type="set_prefs", hold_priority=True)
    opt = start_cast(s, "Opt", U=1)
    start_cast(s, "Reverse the Polarity", modes=[0], U=2, C=1)
    settle(s)
    assert zone(s, opt) == "p1:graveyard" and len(s.state.zones["p1:hand"]) == 0  # (Opt never resolved: no card drawn)
    check(s)


def test_reverse_the_polarity_switches_power_and_toughness(cards):
    """Reverse the Polarity, mode 2: "Switch each creature's power and toughness until end of turn." A 0/8 Wall becomes 8/0 and dies."""
    s = build(cards, ["Reverse the Polarity", "Grizzly Bears"], ["Wall of Stone"])
    bear, wall = put_on(s, "Grizzly Bears"), put_on(s, "Wall of Stone", "p2")
    cast(s, "Reverse the Polarity", modes=[1], U=2, C=1)
    assert zone(s, wall) == "p2:graveyard" and pt_of(s, bear) == (2, 2)
    check(s)


def test_summary_dismissal_exiles_even_an_uncounterable_spell_and_counters_a_trigger(cards):
    """Summary Dismissal: "Exile all other spells and counter all abilities." Under it: Merfolk Looter's activated ability (countered: no card
    drawn or discarded), Opt and Abrupt Decay ("This spell can't be countered.": exiled all the same)."""
    s = build(cards, ["Summary Dismissal", "Merfolk Looter", "Opt", "Abrupt Decay"], ["Sol Ring"])
    looter, ring = put_on(s, "Merfolk Looter"), put_on(s, "Sol Ring", "p2")
    to_phase(s, "main1", turn=3)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=looter.id, ability=0)
    assert any(s.state.cards[c].ability is not None for c in s.state.zones["stack"])
    opt = start_cast(s, "Opt", U=1)
    decay = start_cast(s, "Abrupt Decay", targets=[ring.id], B=1, G=1)
    hand = len(s.state.zones["p1:hand"])
    start_cast(s, "Summary Dismissal", U=2, C=2)
    settle(s)
    assert zone(s, opt) == "p1:exile" and zone(s, decay) == "p1:exile" and zone(s, ring) == "p2:battlefield"
    assert len(s.state.zones["p1:hand"]) == hand - 1 and not s.state.zones.get("stack")  # (Summary Dismissal left the hand; the loot never happened)
    check(s)
