"""Review of wave 26C (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load.

* 304.5 / 602.5e: "Activate only as an instant" needs priority, which a player paying a cost (601.2g-h) or a resolving payment doesn't
  have: Lion's Eye Diamond can't be activated mid-payment. A mana ability whose cost chooses objects (Ashnod's Altar's
  sacrifice) is paid through its own choice, never as plain mana (it was free mana: the chosen cost was skipped); wave 28D nests
  that choice in the payment prompt (tests/test_rules_wave28d_nested_mana.py).
* 608.2h / 400.7: "the power of the creature tapped this way" is that creature as it last existed once it has left.
* 118.3: "Remove X +1/+1 counters from among creatures you control" can't be paid with more counters than there are.
* 113.6m: Bookwurm's "Put this card from your graveyard …" works only in the graveyard.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules.mana_units import visible_pool
from tests.game_helpers import act
from tests.test_rules_conditionals import creature, pick, until_asked
from tests.test_rules_wave12a_counters_keywords import answer
from tests.test_rules_wave26c_if_you_do import (  # noqa: F401
    activate,
    card_db,
    chars_of,
    chars_of_id,
    hand_size,
)
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of


def self_payment(s):
    for prefs in s.state.rules.prefs.values():
        prefs.payment = "self"  # (players tap their own mana: the "tap your mana" prompt)


def test_lions_eye_diamond_cannot_be_activated_while_paying_for_a_spell(cards):
    s = build(cards, ["Lion's Eye Diamond", "Giant Opportunity", "Rent Is Due"])
    self_payment(s)
    led = put(s, "Lion's Eye Diamond")
    spell = to_hand(s, "Giant Opportunity")
    to_hand(s, "Rent Is Due")
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = s.state.rules.decision
    assert d is not None and d.resume["step"] == "pay_mana"
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=led.id, ability=0, mana_choice="G")
    assert zone_of(s, "Lion's Eye Diamond") == "p1:battlefield" and zone_of(s, "Rent Is Due") == "p1:hand"
    assert visible_pool(s.state, "p1").get("G", 0) == 0
    check(s)


def test_a_sacrifice_mana_ability_pays_its_cost_while_paying(cards):  # (wave 28D: nested in the payment, 605.3a; it was refused in 26C)
    s = build(cards, ["Giant Opportunity"])
    self_payment(s)
    act(s, "p1", type="create_token", player="p1", token={"name": "Altar", "type_line": "Token Artifact",
                                                          "text": "Sacrifice a creature: Add {C}{C}."})  # (Ashnod's Altar's ability)
    bear = creature(s, "p1", "Bear")
    altar = card_named(s, "Altar")
    spell = to_hand(s, "Giant Opportunity")
    act(s, "p1", type="cast_spell", card_id=spell.id)
    act(s, "p1", type="activate_ability", card_id=altar.id, ability=0)
    assert bear.id not in s.state.cards  # (the creature was sacrificed as the cost: not free mana)
    assert visible_pool(s.state, "p1").get("C", 0) == 2
    check(s)


def test_lions_eye_diamond_with_priority_discards_the_hand(cards):
    s = build(cards, ["Lion's Eye Diamond", "Rent Is Due"])
    self_payment(s)
    put(s, "Lion's Eye Diamond")
    to_hand(s, "Rent Is Due")
    activate(s, "Lion's Eye Diamond", "Discard your hand")
    pick(s, "4")  # (G)
    assert hand_size(s) == 0 and visible_pool(s.state, "p1").get("G") == 3
    check(s)


def test_keldon_battlewagon_reads_the_tapped_creature_as_it_last_existed(cards):
    s = build(cards, ["Keldon Battlewagon"], ["Lightning Bolt"])
    for prefs in s.state.rules.prefs.values():
        prefs.response = "on"  # (the ability waits on the stack)
    put(s, "Keldon Battlewagon")
    bear = creature(s, "p1", "Bear", pt="1/1")
    act(s, "p1", type="counter", card_ids=[bear.id], kind="+1/+1", delta=2)  # (a 3/3)
    activate(s, "Keldon Battlewagon", "Tap an untapped creature")
    until_asked(s)
    pick(s, bear.id)
    assert s.state.zones.get("stack")  # (the ability waits)
    assert s.state.rules.priority == "p2"
    bolt = to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=bolt.id, targets=[bear.id])  # (the tapped creature dies before the ability resolves)
    answer(s)
    assert bear.id not in s.state.cards or not s.state.cards[bear.id].zone.endswith(":battlefield")
    assert chars_of(s, "Keldon Battlewagon").pt == (3, 3)  # (608.2h: its power as it last existed, counters included)
    check(s)


def test_among_x_cost_needs_that_many_counters(cards):
    s = build(cards, ["Retribution of the Ancients"])
    put(s, "Retribution of the Ancients")
    mine = creature(s, "p1", "Mine", pt="1/1")
    ogre = creature(s, "p2", "Ogre", pt="3/3")
    act(s, "p1", type="counter", card_ids=[mine.id], kind="+1/+1", delta=2)
    mana(s, B=1)
    with pytest.raises(ActionError):
        activate(s, "Retribution of the Ancients", "{B}", targets=[ogre.id], x_value=3)  # 118.3
    assert s.state.cards[mine.id].counters.get("+1/+1") == 2 and chars_of_id(s, ogre.id).pt == (3, 3)
    check(s)


def test_bookwurm_ability_does_nothing_from_the_battlefield(cards):
    s = build(cards, ["Bookwurm"])
    put(s, "Bookwurm")
    mana(s, G=1, C=2)
    with pytest.raises(ActionError):
        activate(s, "Bookwurm", "{2}{G}")  # 113.6m
    assert zone_of(s, "Bookwurm") == "p1:battlefield"
    check(s)


def test_spirit_token_selector_is_non_spirit(cards):
    s = build(cards, ["Lost in the Spirit World"])
    spell = to_hand(s, "Lost in the Spirit World")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=spell.id, targets=[])
    answer(s)
    token = next(c for c in s.state.cards.values() if c.name == "Spirit" and c.zone == "p1:battlefield")
    imposed = chars_of_id(s, token.id).imposed
    assert all('"not_subtypes":["Spirit"]' in r for r in imposed if r.startswith(("cant_be_blocked_by", "cant_block_sel")))
    check(s)
