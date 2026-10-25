"""Wave 110B session 10: single cards read from an exact wording (real Oracle text in tests/fixtures/wave110b_cards.json).

* Equal Treatment: 614.1a, 611.2a "any source would deal 1 or more damage ... this turn, 2 instead": 3 becomes 2, 1 becomes 2 (Flameblade ping), then draw.
* Archfiend of Spite: 118.12a, 120.3 "loses that much life unless they sacrifice that many permanents": the damage dealt is the count, the source's controller chooses.
* Elderscale Wurm: 119.1 "life total is less than 7" as it enters, and 120.3a/614.1a "damage that would reduce your life total to less than 7 reduces it to 7" while at 7+.
* Soulfire Grand Master: 608.2n, 614.1a "the next time you cast an instant or sorcery spell from your hand this turn, put that card into your hand instead of into your graveyard": used by one cast, only from hand, not when countered.
* Flameblade Angel: 120.3 / 603.2 damage from an opponent's source to you or to a permanent you control triggers once; 603.7-free "may" 1 damage to that source's controller.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110b_kit import build, cast, check, drive, mana, put, repository, to_hand


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Flameblade Angel", "Equal Treatment", "Archfiend of Spite", "Elderscale Wurm", "Soulfire Grand Master", "Taii Wakeen, Perfect Shot"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("aim, pings", [("player", 1), ("bears", 1), ("p2bears", 0)])
def test_flameblade_angel_pings_the_controller_of_a_source_that_hit_you_or_yours(cards, aim, pings):
    s = build(cards, ["Flameblade Angel", "Grizzly Bears", "Lightning Bolt"], ["Lightning Bolt", "Grizzly Bears"])
    put(s, "Flameblade Angel")
    bears = put(s, "Grizzly Bears")
    p2bears = put(s, "Grizzly Bears", "p2")
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p1", type="set_prefs", response="on")
    mana(s, "p2", R=1)
    s.state.rules.priority = "p2"
    target = {"player": "p1", "bears": bears.id, "p2bears": p2bears.id}[aim]
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=[target])
    drive(s)
    assert s.state.players["p2"].life == 40 - pings
    check(s)


def test_equal_treatment_sets_every_damage_to_2_this_turn(cards):
    s = build(cards, ["Equal Treatment", "Flameblade Angel", "Lightning Bolt", "Forest"], ["Lightning Bolt"])
    put(s, "Flameblade Angel")
    mana(s, "p1", W=1, C=1)
    hand = len(s.state.zones["p1:hand"])
    cast(s, "Equal Treatment")
    assert len(s.state.zones["p1:hand"]) == hand + 1  # drew a card (the spell left the hand, the draw came in)  # noqa: E501
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p1", type="set_prefs", response="on")
    mana(s, "p2", R=1)
    s.state.rules.priority = "p2"
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=["p1"])
    drive(s)
    assert s.state.players["p1"].life == 38  # 3 -> 2
    assert s.state.players["p2"].life == 38  # Angel's 1 -> 2
    check(s)


@pytest.mark.parametrize("pays", [False, True])
def test_archfiend_of_spite_makes_the_source_controller_lose_life_or_sacrifice_that_many(cards, pays):
    s = build(cards, ["Archfiend of Spite", "Elderscale Wurm", "Soulfire Grand Master"], ["Lightning Bolt", "Grizzly Bears", "Shivan Dragon", "Forest"])
    archfiend = put(s, "Archfiend of Spite")
    kept = [put(s, n, "p2") for n in ("Grizzly Bears", "Shivan Dragon", "Forest")]
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p1", type="set_prefs", response="on")
    mana(s, "p2", R=1)
    s.state.rules.priority = "p2"
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=[archfiend.id])
    drive(s, lambda d: [next((o.id for o in d.options if o.label.startswith("Pay") == pays), d.options[0].id)])
    assert s.state.players["p2"].life == (40 if pays else 37)
    assert [s.state.cards[c.id].zone for c in kept] == (["p2:graveyard"] * 3 if pays else ["p2:battlefield"] * 3)
    check(s)


@pytest.mark.parametrize("start, after", [(3, 7), (7, 7), (20, 20)])
def test_elderscale_wurm_raises_a_low_life_total_to_7_as_it_enters(cards, start, after):
    s = build(cards, ["Elderscale Wurm"], [])
    act(s, "p1", type="set_life", player="p1", value=start)
    mana(s, "p1", G=3, C=4)
    cast(s, "Elderscale Wurm")
    assert s.state.players["p1"].life == after
    check(s)


@pytest.mark.parametrize("start, after", [(10, 7), (8, 7), (7, 7), (5, 2)])
def test_elderscale_wurm_keeps_you_at_7_against_damage_only_from_7_or_more(cards, start, after):
    s = build(cards, ["Elderscale Wurm"], ["Lightning Bolt"])
    put(s, "Elderscale Wurm")
    act(s, "p1", type="set_life", player="p1", value=start)
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p1", type="set_prefs", response="on")
    mana(s, "p2", R=1)
    s.state.rules.priority = "p2"
    act(s, "p2", type="cast_spell", card_id=to_hand(s, "Lightning Bolt", "p2").id, targets=["p1"])
    drive(s)
    assert s.state.players["p1"].life == after
    check(s)


def test_soulfire_grand_master_returns_only_the_next_spell_cast_from_hand(cards):
    s = build(cards, ["Soulfire Grand Master", "Lightning Bolt"], [])
    master = put(s, "Soulfire Grand Master")
    mana(s, "p1", U=1, R=1, C=2)
    act(s, "p1", type="activate_ability", card_id=master.id, ability=2)
    drive(s)
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=2)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    drive(s)
    assert s.state.players["p2"].life == 37
    assert s.state.cards[bolt.id].zone == "p1:hand"  # not the graveyard
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])  # the grant is used up
    drive(s)
    assert s.state.players["p2"].life == 34
    assert s.state.cards[bolt.id].zone == "p1:graveyard"
    check(s)


@pytest.mark.parametrize("pick, zone", [("hand", "p1:hand"), ("rebound", "p1:exile")])
def test_soulfire_on_a_rebound_spell_controller_picks_616_1(cards, pick, zone):
    """616.1: rebound and Soulfire's hand replacement both change where the resolving spell goes: its controller chooses."""
    s = build(cards, ["Soulfire Grand Master", "Staggershock"], [])
    master = put(s, "Soulfire Grand Master")
    mana(s, "p1", U=1, R=1, C=2)
    act(s, "p1", type="activate_ability", card_id=master.id, ability=2)
    drive(s)
    shock = to_hand(s, "Staggershock")
    mana(s, "p1", R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=shock.id, targets=["p2"])
    drive(s, lambda d: [pick] if {o.id for o in d.options} == {"rebound", "hand"} else None)
    assert s.state.players["p2"].life == 38
    assert s.state.cards[shock.id].zone == zone
    check(s)


def test_taii_wakeen_draws_on_exact_toughness_and_adds_x(cards):
    """120.3, 614.1a: draw only when noncombat damage to a creature equals its toughness; {X},{T}: damage plus X this turn."""
    s = build(cards, ["Taii Wakeen, Perfect Shot", "Lightning Bolt"], ["Grizzly Bears", "Shivan Dragon"])
    taii = put(s, "Taii Wakeen, Perfect Shot")
    bears, dragon = put(s, "Grizzly Bears", "p2"), put(s, "Shivan Dragon", "p2")
    to_phase(s, "main1", turn=3)

    def bolt(target):
        bolt_card = to_hand(s, "Lightning Bolt")
        mana(s, "p1", R=1)
        before = len(s.state.zones["p1:hand"])
        act(s, "p1", type="cast_spell", card_id=bolt_card.id, targets=[target])
        drive(s)
        return len(s.state.zones["p1:hand"]) - before + 1  # cards drawn

    assert bolt(dragon.id) == 0  # 3 damage to 5 toughness
    assert bolt(bears.id) == 0  # 3 damage to 2 toughness
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=taii.id, ability=1, x_value=2)
    drive(s)
    assert bolt(dragon.id) == 1  # 3 + 2 = 5 = its toughness
    check(s)


def test_taii_wakeen_x_adds_to_noncombat_damage(cards):
    s = build(cards, ["Taii Wakeen, Perfect Shot", "Lightning Bolt"], [])
    taii = put(s, "Taii Wakeen, Perfect Shot")
    to_phase(s, "main1", turn=3)
    mana(s, "p1", C=2)
    act(s, "p1", type="activate_ability", card_id=taii.id, ability=1, x_value=2)
    drive(s)
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=["p2"])
    drive(s)
    assert s.state.players["p2"].life == 35  # 3 + X(2)
    check(s)
