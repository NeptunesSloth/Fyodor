"""Wave 45A: "Any number of target players each ..." / "Two target players each ..." (CR 2026-09-25), real Oracle text
(tests/fixtures/wave45a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 115.1, 601.2c, 608.2b: one target group of players (any number, up to two, exactly two); each player chosen does the instruction. Hunters' Feast [27666],
  Reward the Faithful [23342], Jace, Memory Adept's -7 [5858], Tinybones Joins Up [4138], Gleaming Splendor [2117], Huddle Up [22974], Donatello's Science Lesson [25888].
* Gleaming Splendor's ruling 2026-06-29: its activated ability requires two different target players (you can't target the same player twice).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.test_rules_wave34b_activated import activate, settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand
from tests.wave45a_kit import FULL, cast, life, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("targets, alice, bob", [(["p1", "p2"], 46, 46), (["p2"], 40, 46), ([], 40, 40)])
def test_hunters_feast_gives_6_life_to_each_player_chosen(cards, targets, alice, bob):
    s = build(cards, ["Hunters' Feast"], [])
    to_hand(s, "Hunters' Feast")
    mana(s, G=1, C=3)
    cast(s, "Hunters' Feast", targets=targets, target_counts=[len(targets)])
    assert (life(s, "p1"), life(s, "p2")) == (alice, bob)
    check(s)


def test_gleaming_splendor_has_two_different_target_players_each_draw_a_card(cards):
    s = build(cards, ["Gleaming Splendor"], [])
    splendor = put(s, "Gleaming Splendor")
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    mana(s, W=1, C=2)
    activate(s, "p1", splendor, "Two target players", targets=["p1", "p2"], target_counts=[2])
    settle(s)
    assert {p: len(s.state.zones[f"{p}:hand"]) - n for p, n in hands.items()} == {"p1": 1, "p2": 1}
    check(s)


def test_gleaming_splendor_cannot_target_one_player_twice(cards):
    s = build(cards, ["Gleaming Splendor"], [])
    splendor = put(s, "Gleaming Splendor")
    mana(s, W=1, C=2)
    with pytest.raises(ActionError):
        activate(s, "p1", splendor, "Two target players", targets=["p2", "p2"], target_counts=[2])  # 115.3: the same player can't be both targets of one group
    check(s)


def test_huddle_up_has_two_target_players_each_draw(cards):
    s = build(cards, ["Huddle Up"], [])
    to_hand(s, "Huddle Up")
    hands = {p: len(s.state.zones[f"{p}:hand"]) for p in ("p1", "p2")}
    mana(s, U=1, C=2)
    cast(s, "Huddle Up", targets=["p1", "p2"], target_counts=[2])
    assert {p: len(s.state.zones[f"{p}:hand"]) - n for p, n in hands.items()} == {"p1": 0, "p2": 1}  # (Huddle Up itself left Alice's hand: she drew one for it)
    check(s)


def test_reward_the_faithful_gains_the_greatest_mana_value_among_your_permanents(cards):
    s = build(cards, ["Reward the Faithful", "Gleaming Splendor"], [])
    put(s, "Gleaming Splendor")  # mana value 2
    to_hand(s, "Reward the Faithful")
    mana(s, W=1)
    cast(s, "Reward the Faithful", targets=["p1", "p2"], target_counts=[2])
    assert (life(s, "p1"), life(s, "p2")) == (42, 42)  # each target gains 2: the number is the caster's own permanents' (the card says "among permanents you control")
    assert card_named(s, "Reward the Faithful").zone == "p1:graveyard"
    check(s)
