"""Wave 100E: X values (app/rules/xdamage100e.py; CR 2026-09-25). Real Oracle text (tests/fixtures/wave100e_xdamage_cards.json); every
scenario checks the replay and a save and a load.

* 701.21a + 608.2h: "its controller sacrifices it, then creates X … where X is that creature's power" (Mercy Killing).
* X read as the instruction is reached: the milled card's mana value (Infernal Genesis), opponents' hands (Wolfcaller's Howl), 7 minus the
  hand of the creature's controller (Flunk), the Plains you control (Quarry Colossus).
* 401.4 "just beneath the top X cards" (Unexpectedly Absent, Quarry Colossus); 903.8 the commander tax count (Commander's Insight); 701.10b
  doubling X times (Exponential Growth); 601.2i "as you cast this spell" (Faerie Fencing); a keyword checked on resolution (Winter Blast).
"""

from __future__ import annotations

import pytest

from tests import wave100e_kit as kit
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, pt, put, to_hand
from tests.wave100e_kit import answer, full_control, hand, library, set_hand, to_phase, tokens, zone_of


@pytest.fixture()
def cards(settings):
    yield from kit.repo(settings)


def on_top(s, name, pid):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return c


# -- Mercy Killing ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("theirs", [True, False])
def test_mercy_killing_its_controller_sacrifices_it_and_gets_its_power_in_elves(cards, theirs):
    """701.21a + 608.2h: Grizzly Bears with a +1/+1 counter (power 3) is sacrificed by whoever controls it, who gets three Elf Warriors."""
    owner, other = ("p2", "p1") if theirs else ("p1", "p2")
    s = build(cards, ["Mercy Killing", *([] if theirs else ["Grizzly Bears"])], ["Grizzly Bears"] if theirs else [])
    bears = put(s, "Grizzly Bears", owner)
    act(s, owner, type="counter", card_ids=[bears.id], kind="+1/+1", delta=1)
    spell = to_hand(s, "Mercy Killing")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id])
    answer(s)
    assert zone_of(s, bears) == f"{owner}:graveyard" and len(tokens(s, "Elf Warrior", owner)) == 3 and not tokens(s, "Elf Warrior", other)
    check(s)


# -- Infernal Genesis / Wolfcaller's Howl: upkeep triggers sized as they resolve -----------------------------------------------------------------
def test_infernal_genesis_each_upkeep_player_mills_and_makes_that_many_minions(cards):
    """Bob's upkeep: Bob mills Twisted Abomination (mana value 6): six Minions for Bob; Alice's next upkeep mills a land: none (the 2008-08-01
    ruling)."""
    s = build(cards, ["Infernal Genesis"], ["Twisted Abomination"])
    put(s, "Infernal Genesis")
    big = on_top(s, "Twisted Abomination", "p2")
    to_phase(s, "main1", turn=1)
    answer(s)
    assert zone_of(s, big) == "p2:graveyard" and len(tokens(s, "Minion", "p2")) == 6 and not tokens(s, "Minion", "p1")
    land = s.state.cards[library(s, "p1")[0]]
    to_phase(s, "main1", turn=1)
    answer(s)
    assert s.state.cards[land.id].zone == "p1:graveyard"
    assert not tokens(s, "Minion", "p1") and len(tokens(s, "Minion", "p2")) == 6
    check(s)


@pytest.mark.parametrize(("bob_keeps", "wolves"), [(7, 1), (3, 0)])
def test_wolfcallers_howl_counts_opponents_with_four_or_more_cards(cards, bob_keeps, wolves):
    s = build(cards, ["Wolfcaller's Howl"], islands=20)
    put(s, "Wolfcaller's Howl")
    to_phase(s, "main1", turn=1)
    set_hand(s, "p2", bob_keeps)
    to_phase(s, "main1", turn=1)
    answer(s)
    assert len(tokens(s, "Wolf", "p1")) == wolves
    check(s)


# -- Unexpectedly Absent / Quarry Colossus: "just beneath the top X cards" ----------------------------------------------------------------------
@pytest.mark.parametrize("x", [0, 2])
def test_unexpectedly_absent_puts_it_beneath_the_top_x_cards(cards, x):
    """X 0: on top (the 2016-06-08 ruling); X 2: third from the top of its owner's library."""
    s = build(cards, ["Unexpectedly Absent"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    spell = to_hand(s, "Unexpectedly Absent")
    mana(s, W=2, C=x)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id], x_value=x)
    answer(s)
    assert library(s, "p2").index(bears.id) == x
    check(s)


def test_unexpectedly_absent_a_short_library_puts_it_on_the_bottom(cards):
    s = build(cards, ["Unexpectedly Absent"], ["Grizzly Bears"], islands=2)
    bears = put(s, "Grizzly Bears", "p2")
    for cid in library(s, "p2")[2:]:
        act(s, "p2", type="move", card_ids=[cid], to={"player": "p2", "zone": "exile"})
    spell = to_hand(s, "Unexpectedly Absent")
    mana(s, W=2, C=5)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id], x_value=5)
    answer(s)
    assert library(s, "p2")[-1] == bears.id and len(library(s, "p2")) == 3
    check(s)


@pytest.mark.parametrize("plains", [0, 2])
def test_quarry_colossus_counts_the_plains_as_it_resolves(cards, plains):
    s = build(cards, ["Quarry Colossus", "Probe Plains", "Probe Plains"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    for c in [c for c in s.state.cards.values() if c.name == "Probe Plains"][:plains]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    colossus = to_hand(s, "Quarry Colossus")
    mana(s, W=2, C=5)
    act(s, "p1", type="cast_spell", card_id=colossus.id)
    answer(s, bears.id)
    assert library(s, "p2").index(bears.id) == plains
    check(s)


# -- Commander's Insight: 903.8 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("casts", [0, 1])
def test_commanders_insight_draws_x_plus_the_targets_commander_casts(cards, casts):
    s = build(cards, ["Commander's Insight"])
    if casts:
        krenko = card_named(s, "Krenko, Mob Boss")
        mana(s, R=2, C=2)
        act(s, "p1", type="cast_spell", card_id=krenko.id)
        answer(s)
        assert s.state.cards[krenko.id].zone == "p1:battlefield"
    spell = to_hand(s, "Commander's Insight")
    before = hand(s)
    mana(s, U=3, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p1"], x_value=2)
    answer(s)
    assert hand(s) == before - 1 + 2 + casts
    check(s)


def test_commanders_insight_counts_the_target_players_casts_not_yours(cards):
    s = build(cards, ["Commander's Insight"])
    mana(s, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Krenko, Mob Boss").id)
    answer(s)
    spell = to_hand(s, "Commander's Insight")
    before = hand(s, "p2")
    mana(s, U=3, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=["p2"], x_value=1)
    answer(s)
    assert hand(s, "p2") == before + 1  # (Bob has cast no commander)
    check(s)


# -- Exponential Growth: 701.10b ----------------------------------------------------------------------------------------------------------------
def test_exponential_growth_doubles_the_power_x_times_in_turn(cards):
    """The 2021-04-16 ruling: X 3 on a 2/2: 4, 8, then 16 — a 16/2 until end of turn."""
    s = build(cards, ["Exponential Growth", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    spell = to_hand(s, "Exponential Growth")
    mana(s, G=2, C=6)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[bears.id], x_value=3)
    answer(s)
    assert pt(s, "Grizzly Bears") == (16, 2)
    check(s)


# -- Faerie Fencing: 601.2i ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("faerie", "gone", "toughness"), [(False, False, 4), (True, False, 1), (True, True, 1)])
def test_faerie_fencing_an_additional_minus_three_for_a_faerie_controlled_as_it_was_cast(cards, faerie, gone, toughness):
    """X 2 on a 0/6: -2/-2, and -3/-3 more if a Faerie was controlled as casting finished — even if it's gone by resolution (the ruling)."""
    s = build(cards, ["Faerie Fencing", "Probe Faerie"], ["Probe Wall"])
    wall = put(s, "Probe Wall", "p2")
    fae = put(s, "Probe Faerie") if faerie else None
    spell = to_hand(s, "Faerie Fencing")
    mana(s, B=1, C=2)
    full_control(s)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[wall.id], x_value=2)
    if gone and fae is not None:
        act(s, "p1", type="move", card_ids=[fae.id], to={"player": "p1", "zone": "graveyard"})
    answer(s)
    assert pt(s, "Probe Wall", "p2")[1] == toughness and zone_of(s, wall) == "p2:battlefield"
    check(s)


# -- Flunk ------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("keeps", "toughness"), [(7, 6), (4, 3), (0, -1)])
def test_flunk_shrinks_by_seven_minus_the_controllers_hand(cards, keeps, toughness):
    """X is 7 minus the cards in the creature's controller's hand as it resolves, never below 0 (the 2021-04-16 rulings): -0/-0, -3/-3, -7/-7
    on a 0/6 (the last one dies, so its toughness isn't read: it's in the graveyard)."""
    s = build(cards, ["Flunk"], ["Probe Wall"])
    wall = put(s, "Probe Wall", "p2")
    set_hand(s, "p2", keeps)
    spell = to_hand(s, "Flunk")
    mana(s, B=1, C=1)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[wall.id])
    answer(s)
    if toughness > 0:
        assert zone_of(s, wall) == "p2:battlefield" and pt(s, "Probe Wall", "p2")[1] == toughness
    else:
        assert zone_of(s, wall) == "p2:graveyard"
    check(s)


# -- Winter Blast ----------------------------------------------------------------------------------------------------------------------------------
def test_winter_blast_taps_x_targets_and_damages_the_flyers_among_them(cards):
    s = build(cards, ["Winter Blast"], ["Mesa Pegasus", "Grizzly Bears"])
    pegasus, bears = put(s, "Mesa Pegasus", "p2"), put(s, "Grizzly Bears", "p2")
    spell = to_hand(s, "Winter Blast")
    mana(s, G=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[pegasus.id, bears.id], target_counts=[2], x_value=2)
    answer(s)
    assert zone_of(s, pegasus) == "p2:graveyard" and s.state.cards[bears.id].tapped and s.state.cards[bears.id].damage == 0
    check(s)
