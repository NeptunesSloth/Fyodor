"""Wave 100E: total power, counters and villainous damage (app/rules/xdamage100e.py; CR 2026-09-25). Real Oracle text
(tests/fixtures/wave100e_xdamage_cards.json); every scenario checks the replay and a save and a load.

* Angrath −11: total power as the creatures last existed (608.2h), an indestructible one counted as it is (the 2018-01-19 rulings).
* Consuming Ferocity: an intervening count of +1/+0 counters, then the creature bites its own controller and is destroyed (no regeneration).
* Blazing Effigy: 3 plus the damage other Effigies dealt it this turn (the damage log, 120.3).
* Sycorax Commander: a villainous choice (701.55), each opponent in turn order.
"""

from __future__ import annotations

import pytest

from tests import wave100e_kit as kit
from tests.game_helpers import act
from tests.test_rules_wave7b_activation import ability_index
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand
from tests.wave100e_kit import answer, hand, loyal, pick, set_hand, zone_of


@pytest.fixture()
def cards(settings):
    yield from kit.repo(settings)


# -- Angrath, Minotaur Pirate −11 -----------------------------------------------------------------------------------------------------------------
def test_angrath_destroys_their_creatures_and_deals_their_total_power(cards):
    """Bob's 5/3 (with a +1/+1 counter: 6), 2/2 and an indestructible 0/1 Myr (stays, counted at 0): 8 damage; Alice's Bears are untouched."""
    s = build(cards, ["Angrath, Minotaur Pirate", "Grizzly Bears"], ["Twisted Abomination", "Grizzly Bears", "Darksteel Myr"])
    angrath = loyal(s, "Angrath, Minotaur Pirate", loyalty=11)
    mine = put(s, "Grizzly Bears")
    big, bears, myr = put(s, "Twisted Abomination", "p2"), put(s, "Grizzly Bears", "p2"), put(s, "Darksteel Myr", "p2")
    act(s, "p2", type="counter", card_ids=[big.id], kind="+1/+1", delta=1)
    act(s, "p1", type="activate_ability", card_id=angrath.id, ability=ability_index(s, angrath, "Destroy all creatures"), targets=["p2"])
    answer(s)
    assert zone_of(s, big) == "p2:graveyard" and zone_of(s, bears) == "p2:graveyard" and zone_of(s, myr) == "p2:battlefield"
    assert life(s, "p2") == 40 - 8 and zone_of(s, mine) == "p1:battlefield"
    check(s)


# -- Consuming Ferocity ---------------------------------------------------------------------------------------------------------------------------
def test_consuming_ferocity_bites_its_controller_on_the_third_counter(cards):
    """Bob's 5/3 enchanted (+1/+0): Alice's upkeeps add +1/+0 counters; with the third, it deals its power (5 + 1 + 3 = 9) to Bob and is
    destroyed."""
    s = build(cards, ["Consuming Ferocity"], ["Twisted Abomination"])
    big = put(s, "Twisted Abomination", "p2")
    aura = to_hand(s, "Consuming Ferocity")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=aura.id, targets=[big.id])
    answer(s)
    act(s, "p1", type="counter", card_ids=[big.id], kind="+1/+0", delta=1)
    for _ in range(2):
        kit.to_phase(s, "main1", turn=2)
        answer(s)
        if _ == 0:
            assert zone_of(s, big) == "p2:battlefield" and s.state.cards[big.id].counters.get("+1/+0") == 2 and life(s, "p2") == 40
    assert zone_of(s, big) == "p2:graveyard" and life(s, "p2") == 40 - 9
    check(s)


# -- Blazing Effigy -------------------------------------------------------------------------------------------------------------------------------
def test_blazing_effigy_chain_adds_the_damage_from_other_effigies(cards):
    """The first Effigy is destroyed and deals 3 to the second (a 0/3: it dies too); the second deals 3 + the 3 another Effigy dealt it this
    turn = 6 to the 0/6 Wall, which dies."""
    s = build(cards, ["Blazing Effigy", "Blazing Effigy", "Murder"], ["Probe Wall"])
    first, second = [c for c in s.state.cards.values() if c.name == "Blazing Effigy" and c.owner == "p1"]
    for c in (first, second):
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    wall = put(s, "Probe Wall", "p2")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[first.id])
    pick(s, "choose_one", second.id)  # (the first Effigy's dies trigger)
    pick(s, "choose_one", wall.id)  # (the second's)
    answer(s)
    assert zone_of(s, first) == "p1:graveyard" and zone_of(s, second) == "p1:graveyard" and zone_of(s, wall) == "p2:graveyard"
    check(s)


def test_blazing_effigy_alone_deals_three(cards):
    s = build(cards, ["Blazing Effigy", "Murder"], ["Probe Wall"])
    effigy = put(s, "Blazing Effigy")
    wall = put(s, "Probe Wall", "p2")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Murder").id, targets=[effigy.id])
    answer(s, wall.id)
    assert s.state.cards[wall.id].damage == 3
    check(s)


# -- Sycorax Commander ----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("wheel", [True, False])
def test_sycorax_commander_villainous_choice_wheel_or_burn(cards, wheel):
    """Bob holds four cards: discard them all and draw three, or be dealt 4."""
    s = build(cards, ["Sycorax Commander"], islands=20)
    set_hand(s, "p2", 4)
    held = list(s.state.zones["p2:hand"])
    commander = to_hand(s, "Sycorax Commander")
    mana(s, B=1, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=commander.id)
    d = pick(s, "choose_one", "a" if wheel else "b")
    assert d.player == "p2"
    answer(s)
    if wheel:
        assert hand(s, "p2") == 3 and all(s.state.cards[c].zone == "p2:graveyard" for c in held) and life(s, "p2") == 40
    else:
        assert hand(s, "p2") == 4 and life(s, "p2") == 36
    assert card_named(s, "Sycorax Commander").zone == "p1:battlefield"
    check(s)
