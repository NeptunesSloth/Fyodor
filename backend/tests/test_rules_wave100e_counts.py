"""Wave 100E: damage sized by a count (app/rules/xdamage100e.py; CR 2026-09-25). Real Oracle text (tests/fixtures/wave100e_xdamage_cards.json);
every scenario checks the replay and a save and a load.

* Counts read as the instruction is carried out (608.2h): attacking creatures (Lightmine Field), hands (Khorvath's Fury's foes), the land gap
  (Spiteful Repossession: then Treasures for the damage dealt this way), tapped artifacts (Yotia Declares War's reflexive "that much").
* Amounts from X: "X plus 2" (Let the Galaxy Burn), half X rounded down / up (Banshee); a cast spell's mana value (Rage Extractor).
* "unless that player sacrifices it" (Enchanter's Bane): its controller's choice as it resolves.
"""

from __future__ import annotations

import pytest

from tests import wave100e_kit as kit
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand
from tests.wave100e_kit import answer, hand, pick, set_hand, tokens, zone_of


@pytest.fixture()
def cards(settings):
    yield from kit.repo(settings)


def ready(s, *cs):
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0


def lands(s, pid, name, n):
    for c in [c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone == f"{pid}:library"][:n]:
        act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})


# -- Let the Galaxy Burn --------------------------------------------------------------------------------------------------------------------------
def test_let_the_galaxy_burn_spares_the_creatures_that_entered_this_turn(cards):
    """X 1: 3 damage to each creature that didn't enter this turn — Bob's Abomination (there since an earlier turn) dies, the Bears Alice just
    put onto the battlefield are untouched."""
    s = build(cards, ["Let the Galaxy Burn", "Grizzly Bears"], ["Twisted Abomination"])
    big = put(s, "Twisted Abomination", "p2")
    kit.to_phase(s, "main1", turn=2)
    bears = put(s, "Grizzly Bears")
    spell = to_hand(s, "Let the Galaxy Burn")
    mana(s, R=1, C=6)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=1)
    answer(s)
    assert zone_of(s, big) == "p2:graveyard" and zone_of(s, bears) == "p1:battlefield" and s.state.cards[bears.id].damage == 0
    check(s)


# -- Banshee --------------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("x", "them", "me"), [(5, 2, 3), (4, 2, 2), (1, 0, 1)])
def test_banshee_halves_x_rounded_down_to_the_target_and_up_to_you(cards, x, them, me):
    s = build(cards, ["Banshee"])
    banshee = put(s, "Banshee")
    ready(s, banshee)
    mana(s, C=x)
    act(s, "p1", type="activate_ability", card_id=banshee.id, ability=0, targets=["p2"], x_value=x)
    answer(s)
    assert life(s, "p2") == 40 - them and life(s, "p1") == 40 - me
    check(s)


# -- Yotia Declares War: chapter II ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("tapped", [2, 0])
def test_yotia_declares_war_deals_as_much_as_the_artifacts_tapped(cards, tapped):
    """The 2022-09-09 rulings: the reflexive ability triggers even with no artifact tapped (then it deals no damage)."""
    s = build(cards, ["Yotia Declares War", "Sol Ring", "Arcane Signet"], ["Probe Wall"])
    rocks = [put(s, "Sol Ring"), put(s, "Arcane Signet")]
    wall = put(s, "Probe Wall", "p2")
    saga = to_hand(s, "Yotia Declares War")
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=saga.id)
    d = pick(s, "choose_one", "2")  # (read ahead: start with chapter II)
    assert d is not None
    pick(s, "choose_cards", *[r.id for r in rocks][:tapped])
    answer(s, wall.id)
    assert s.state.cards[wall.id].damage == tapped and sum(s.state.cards[r.id].tapped for r in rocks) == tapped
    check(s)


# -- Lightmine Field ------------------------------------------------------------------------------------------------------------------------------
def test_lightmine_field_damages_each_attacker_by_the_number_attacking(cards):
    s = build(cards, ["Lightmine Field", "Grizzly Bears", "Twisted Abomination"])
    put(s, "Lightmine Field")
    bears, big = put(s, "Grizzly Bears"), put(s, "Twisted Abomination")
    ready(s, bears, big)
    act(s, "p1", type="pass_priority")  # -> declare attackers
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}, {"card_id": big.id, "target": "p2"}])
    answer(s)
    assert zone_of(s, bears) == "p1:graveyard" and s.state.cards[big.id].damage == 2
    check(s)


# -- Spiteful Repossession ------------------------------------------------------------------------------------------------------------------------
def test_spiteful_repossession_punishes_the_land_lead_and_makes_that_many_treasures(cards):
    s = build(cards, ["Spiteful Repossession"])
    lands(s, "p1", "Forest", 1)
    lands(s, "p2", "Island", 4)
    spell = to_hand(s, "Spiteful Repossession")
    mana(s, R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    assert life(s, "p2") == 37 and len(tokens(s, "Treasure", "p1")) == 3
    check(s)


def test_spiteful_repossession_no_opponent_ahead_no_damage_no_treasure(cards):
    s = build(cards, ["Spiteful Repossession"])
    lands(s, "p1", "Forest", 2)
    lands(s, "p2", "Island", 2)
    spell = to_hand(s, "Spiteful Repossession")
    mana(s, R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    assert life(s, "p2") == 40 and not tokens(s, "Treasure", "p1")
    check(s)


# -- Khorvath's Fury ------------------------------------------------------------------------------------------------------------------------------
def test_khorvaths_fury_friends_wheel_and_foes_burn_by_their_hand(cards):
    """Alice is a friend (three cards: discards them, draws four), Bob a foe (five cards: 5 damage)."""
    s = build(cards, ["Khorvath's Fury"], islands=20)
    spell = to_hand(s, "Khorvath's Fury")
    set_hand(s, "p1", 4)  # (the Fury and three more)
    set_hand(s, "p2", 5)
    mana(s, R=1, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    pick(s, "choose_one", "friend")  # Alice
    pick(s, "choose_one", "foe")  # Bob
    answer(s)
    assert hand(s, "p1") == 4 and len(s.state.zones["p1:graveyard"]) >= 3 and life(s, "p2") == 35 and hand(s, "p2") == 5
    check(s)


# -- Rage Extractor -------------------------------------------------------------------------------------------------------------------------------
def test_rage_extractor_triggers_only_for_phyrexian_mana_costs(cards):
    s = build(cards, ["Rage Extractor", "Gitaxian Probe", "Opt"])
    put(s, "Rage Extractor")
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Gitaxian Probe").id, targets=["p2"])
    answer(s, "p2")
    assert life(s, "p2") == 39
    mana(s, U=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Opt").id)
    answer(s)
    assert life(s, "p2") == 39
    check(s)


# -- Enchanter's Bane -----------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("sacrifice", [True, False])
def test_enchanters_bane_its_controller_sacrifices_it_or_takes_its_mana_value(cards, sacrifice):
    s = build(cards, ["Enchanter's Bane"], ["Wolfcaller's Howl"])
    put(s, "Enchanter's Bane")
    howl = put(s, "Wolfcaller's Howl", "p2")
    kit.to_phase(s, "end")
    pick(s, "choose_one", howl.id)  # (the target, as it is put on the stack)
    d = pick(s, "confirm", "yes" if sacrifice else "no")
    assert d.player == "p2"
    answer(s)
    if sacrifice:
        assert zone_of(s, howl) == "p2:graveyard" and life(s, "p2") == 40
    else:
        assert zone_of(s, howl) == "p2:battlefield" and life(s, "p2") == 36
    check(s)


def test_enchanters_bane_with_no_other_enchantment_targets_itself(cards):
    """The 2018-07-13 ruling: it must target an enchantment — itself if there is no other (its MV 2: Alice takes 2 or sacrifices it)."""
    s = build(cards, ["Enchanter's Bane"])
    bane = put(s, "Enchanter's Bane")
    kit.to_phase(s, "end")
    answer(s, bane.id, "no")
    assert zone_of(s, bane) == "p1:battlefield" and life(s, "p1") == 38
    assert card_named(s, "Enchanter's Bane").zone == "p1:battlefield"
    check(s)
