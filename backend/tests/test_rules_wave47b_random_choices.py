"""Wave 47B: random picks among modes and Indoraptor's bloodthirst X / enrage (CR 2026-09-25), real Oracle text
(tests/fixtures/wave47b_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 700.2b, 603.3c: a triggered modal ability's mode is chosen as it is put on the stack. "Choose one at random" picks among the modes that can be
  chosen, publicly (the Umaro ruling, modal_abilities); Typhoid Mary: "If you discarded a card this turn, you choose one instead." (the table's pick
  is replaced by the player's choice, judged as the trigger goes on the stack).
* 702.54b: "Bloodthirst X": X is the total damage your opponents have been dealt this turn, by any source (Indoraptor ruling 2023-11-10).
* Indoraptor's enrage: "choose an opponent at random. Indoraptor deals damage equal to its power to that player unless they sacrifice a nontoken
  creature of their choice."
"""

from __future__ import annotations

import json

import pytest

from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave34b_activated import ask, settle
from tests.wave9c_kit import card_named, check, mana, put, to_hand
from tests.wave47b_kit import build3, cast, life, open_cards, pin_random


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


def attack(s, attacker, target):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": attacker.id, "target": target}])


def mary_ready(cards):
    s = build3(cards, ["Typhoid Mary, Fractured"])
    mary = put(s, "Typhoid Mary, Fractured")
    until(s, lambda s: s.state.turn.number == 4 and s.state.turn.phase == "main1" and s.state.rules.decision is None)  # (Alice's second turn)
    return s, mary


@pytest.mark.parametrize("index, mode", [(0, "Mary"), (2, "Bloody Mary")])
def test_typhoid_mary_picks_a_mode_at_random_and_says_which(cards, monkeypatch, index, mode):
    pin_random(monkeypatch, index)
    s, mary = mary_ready(cards)
    attack(s, mary, "p2")
    settle(s)
    log = json.dumps(s.view("p3")["log"], ensure_ascii=False)
    assert f"mode chosen at random — {mode}" in log
    if mode == "Mary":
        assert any(c.name == "Treasure" and c.zone == "p1:battlefield" for c in s.state.cards.values())
    else:
        assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (42, 38, 38) or (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (42, 35, 38)  # (Bob loses 2, and takes 3 more if the attack has been through combat damage)
    check(s)


def test_typhoid_mary_lets_its_controller_choose_after_a_discard(cards, monkeypatch):
    pin_random(monkeypatch, 0)
    s, mary = mary_ready(cards)
    act(s, "p1", type="move", card_ids=[s.state.zones["p1:hand"][0]], to={"zone": "graveyard"})  # (a card discarded this turn)
    hand = len(s.state.zones["p1:hand"])
    attack(s, mary, "p2")
    d = ask(s)
    assert d.player == "p1" and len(d.options) == 3  # no random pick: Alice chooses (and the choice is hers alone)
    assert "chosen at random" not in json.dumps(s.view("p2")["log"])
    check(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[1].id])  # "Typhoid Mary — Draw a card."
    settle(s)
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


# -- Indoraptor, the Perfect Hybrid ----------------------------------------------------------------------------------------------------
def indoraptor_table(cards, carol=()):
    s = build3(cards, ["Indoraptor, the Perfect Hybrid", "Lightning Bolt", "Blaze"], carols=carol)
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=["p2"])  # Bob is dealt 3 damage
    to_hand(s, "Indoraptor, the Perfect Hybrid")
    mana(s, G=1, R=1, C=1)
    cast(s, "Indoraptor, the Perfect Hybrid")
    return s, card_named(s, "Indoraptor, the Perfect Hybrid")


def test_bloodthirst_x_counts_the_damage_dealt_to_opponents_this_turn(cards):
    s, indo = indoraptor_table(cards)
    assert s.state.cards[indo.id].counters.get("+1/+1") == 3
    check(s)


def test_bloodthirst_x_sums_the_damage_to_every_opponent_whoever_dealt_it(cards):
    """702.54b: "the total damage your opponents have been dealt this turn" (Petrified Wood-Kin): Bob's 3 and Carol's 2, from sources of any controller."""
    s = build3(cards, ["Petrified Wood-Kin", "Lightning Bolt", "Blaze"])
    to_hand(s, "Lightning Bolt")
    to_hand(s, "Blaze")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=["p2"])
    mana(s, R=3)
    cast(s, "Blaze", targets=["p3"], x_value=2)
    to_hand(s, "Petrified Wood-Kin")
    mana(s, G=1, C=6)
    cast(s, "Petrified Wood-Kin")
    assert s.state.cards[card_named(s, "Petrified Wood-Kin").id].counters.get("+1/+1") == 5
    check(s)


def test_bloodthirst_x_is_zero_when_no_opponent_was_dealt_damage(cards):
    s = build3(cards, ["Indoraptor, the Perfect Hybrid"])
    to_hand(s, "Indoraptor, the Perfect Hybrid")
    mana(s, G=1, R=1, C=1)
    cast(s, "Indoraptor, the Perfect Hybrid")
    assert not s.state.cards[card_named(s, "Indoraptor, the Perfect Hybrid").id].counters.get("+1/+1")
    check(s)


def test_enrage_hits_the_opponent_chosen_at_random_for_its_power(cards, monkeypatch):
    pin_random(monkeypatch)  # Carol
    s, indo = indoraptor_table(cards)
    to_hand(s, "Blaze")
    mana(s, R=3)
    cast(s, "Blaze", targets=[indo.id], x_value=2)  # (Indoraptor is 6/4 with its three counters: it survives)
    assert life(s, "p3") == 40 - 6 and life(s, "p2") == 37
    assert "Carol is chosen at random" in json.dumps(s.view("p2")["log"])
    check(s)


def test_enrage_is_avoided_by_sacrificing_a_nontoken_creature(cards, monkeypatch):
    pin_random(monkeypatch)
    s, indo = indoraptor_table(cards, carol=["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p3")
    to_hand(s, "Blaze")
    mana(s, R=3)
    cast(s, "Blaze", targets=[indo.id], x_value=2)
    assert life(s, "p3") == 40 and s.state.cards[bears.id].zone == "p3:graveyard"
    check(s)
