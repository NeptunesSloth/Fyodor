"""Wave 45A: "If the gift wasn't promised, ..." and "any number of target players/opponents" on cards the two grammar pieces newly unlock (CR 2026-09-25), real Oracle text
(tests/fixtures/wave45a_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 702.174k, 702.33e: Parting Gust [1644] (tests/test_rules_wave45a_wipes.py), Kitnap [10823] ("When this Aura enters, tap enchanted creature. If the gift wasn't promised,
  put three stun counters on it."), Nocturnal Hunger [13009] ("Destroy target creature. If the gift wasn't promised, you lose 2 life.").
* 115.1, 608.2b: Singularity Rupture [2261] ("... then any number of target players each mill half their library, rounded down."), Will of the Abzan [2550] (its first
  mode, "Any number of target opponents each sacrifice a creature with the greatest power among creatures that player controls and lose 3 life.").
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of
from tests.wave45a_kit import FULL, cast, life, open_cards


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


@pytest.mark.parametrize("name", FULL)
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("gift", [False, True])
def test_nocturnal_hunger_costs_2_life_only_when_the_gift_was_not_promised(cards, gift):
    s = build(cards, ["Nocturnal Hunger"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    c = to_hand(s, "Nocturnal Hunger")
    mana(s, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bears.id], optional_costs=[f"{c.id}:gift"] if gift else [])
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    assert life(s, "p1") == (40 if gift else 38)
    assert any(x.is_token and x.name == "Food" and x.controller == "p2" for x in s.state.cards.values()) is gift  # 702.174: the promised gift, a Food token for Bob
    check(s)


@pytest.mark.parametrize("gift", [False, True])
def test_kitnap_puts_three_stun_counters_only_when_the_gift_was_not_promised(cards, gift):
    s = build(cards, ["Kitnap"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    c = to_hand(s, "Kitnap")
    mana(s, U=2, C=2)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[bears.id], optional_costs=[f"{c.id}:gift"] if gift else [])
    settle(s)
    now = s.state.cards[bears.id]
    assert now.controller == "p1" and now.tapped
    assert now.counters.get("stun", 0) == (0 if gift else 3)
    check(s)


def test_singularity_rupture_destroys_every_creature_and_the_chosen_players_mill_half(cards):
    s = build(cards, ["Singularity Rupture", "Hill Giant"], ["Grizzly Bears"])
    put(s, "Hill Giant")
    put(s, "Grizzly Bears", "p2")
    to_hand(s, "Singularity Rupture")
    library = len(s.state.zones["p2:library"])
    mana(s, U=1, B=2, C=3)
    cast(s, "Singularity Rupture", targets=["p2"], target_counts=[1])
    assert zone_of(s, "Hill Giant") == "p1:graveyard" and zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    assert len(s.state.zones["p2:library"]) == library - library // 2  # half, rounded down, milled
    check(s)


def test_will_of_the_abzan_makes_the_chosen_opponent_sacrifice_the_biggest_creature_and_lose_3(cards):
    s = build(cards, ["Will of the Abzan"], ["Shivan Dragon", "Goblin Piker"])
    put(s, "Shivan Dragon", "p2")
    put(s, "Goblin Piker", "p2")
    to_hand(s, "Will of the Abzan")
    mana(s, B=1, C=3)
    cast(s, "Will of the Abzan", modes=[0], targets=["p2"], target_counts=[1])
    assert zone_of(s, "Shivan Dragon", "p2") == "p2:graveyard" and zone_of(s, "Goblin Piker", "p2") == "p2:battlefield"
    assert life(s, "p2") == 37
    assert card_named(s, "Will of the Abzan").zone == "p1:graveyard"
    check(s)
