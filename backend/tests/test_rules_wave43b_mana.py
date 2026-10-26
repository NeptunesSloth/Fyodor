"""Wave 43B (mana and lands): the most-played mana cards one line short of FULL (CR 2026-09-25), real Oracle text (tests/fixtures/wave43b_cards.json). Every scenario
checks the replay and a save and a load.

* 605.1b, 605.4a, 106.12, 614.12a: "Whenever enchanted Forest is tapped for mana, its controller adds an additional one mana of the chosen color." (Utopia Sprawl [349]),
  "Whenever a land's ability causes you to add one or more mana of the chosen color, add an additional one mana of that color." (Caged Sun [945]) and "Whenever a basic land
  is tapped for mana of the chosen color, its controller adds an additional one mana of that color." (Gauntlet of Power [2606]): a triggered mana ability (no stack), added with
  the land's own mana; the color is the one the permanent chose as it entered - none chosen, nothing; the extra mana is the controller's of the land, whoever controls the
  permanent that makes it.
* 500.7: "This land enters tapped unless it's your first, second, or third turn of the game." (Starting Town [704]) - your own turn, one of the first three you began.
"""

from __future__ import annotations

import pytest

from app.rules.mana_units import visible_pool
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import ask, next_turn, settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand, zone_of
from tests.wave43b_kit import ch, open_cards, tapped


@pytest.fixture()
def cards(settings):
    yield from open_cards(settings)


def choose_color(s, color, pid="p1"):
    d = ask(s)
    assert d.player == pid and color in [o.id for o in d.options], [o.id for o in d.options]
    act(s, pid, type="choose", decision_id=d.id, option_ids=[color])
    settle(s)


def tap_for_mana(s, c, pid="p1"):
    act(s, pid, type="activate_ability", card_id=c.id, ability=next(a.index for a in ch(s, c).abilities if a.kind == "mana"))


def another(s, name, pid="p1"):
    """A second copy of this card (the first one not already on the battlefield), put onto the battlefield."""
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and c.zone != f"{pid}:battlefield")
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def pool(s, pid="p1"):
    return {k: v for k, v in visible_pool(s.state, pid).items() if v}


# ---- Utopia Sprawl [349] ---------------------------------------------------------------------------------------------------------------------------------
def sprawl(cards, color="Red"):
    s = build(cards, ["Utopia Sprawl", "Grizzly Bears"], forests=4)
    forest = put(s, "Forest")
    to_hand(s, "Utopia Sprawl")
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Utopia Sprawl").id, targets=[forest.id])
    choose_color(s, color)
    return s, forest


def test_utopia_sprawl_adds_one_mana_of_the_chosen_color_with_the_forests_own(cards):
    s, forest = sprawl(cards)
    assert pool(s) == {}
    tap_for_mana(s, forest)
    assert pool(s) == {"G": 1, "R": 1}  # 605.4a: right after the Forest's {G}, with no stack
    assert not s.state.zones.get("stack")
    check(s)


def test_utopia_sprawl_does_nothing_for_a_forest_it_is_not_on(cards):
    s, forest = sprawl(cards, "Blue")
    other = another(s, "Forest")
    tap_for_mana(s, other)
    assert pool(s) == {"G": 1}
    tap_for_mana(s, forest)
    assert pool(s) == {"G": 2, "U": 1}
    check(s)


def test_utopia_sprawl_pays_for_a_spell_with_the_extra_mana(cards):
    s, forest = sprawl(cards, "Red")
    to_hand(s, "Grizzly Bears")  # {1}{G}: the Forest's {G} and the Aura's {R} pay it
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Grizzly Bears").id)
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and tapped(s, forest) and pool(s) == {}
    check(s)


# ---- Caged Sun [945] -------------------------------------------------------------------------------------------------------------------------------------
def caged_sun(cards, color="Green"):
    s = build(cards, ["Caged Sun", "Elvish Mystic", "Mountain"], forests=4)
    forest, mountain, mystic = put(s, "Forest"), put(s, "Mountain"), put(s, "Elvish Mystic")
    to_hand(s, "Caged Sun")
    mana(s, C=6)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Caged Sun").id)
    choose_color(s, color)
    return s, forest, mountain, mystic


def test_caged_sun_adds_one_more_mana_of_the_chosen_color_when_a_land_makes_it(cards):
    s, forest, mountain, mystic = caged_sun(cards)
    tap_for_mana(s, forest)
    assert pool(s) == {"G": 2}
    tap_for_mana(s, mountain)
    assert pool(s) == {"G": 2, "R": 1}  # not the chosen color: no extra
    check(s)


def test_caged_sun_is_for_a_lands_ability_only_not_a_creatures(cards):
    s, forest, mountain, mystic = caged_sun(cards)
    next_turn(s)  # Elvish Mystic has been here since the turn began
    tap_for_mana(s, mystic)
    assert pool(s) == {"G": 1}  # "a land's ability", and a creature isn't one
    check(s)


# ---- Gauntlet of Power [2606] ----------------------------------------------------------------------------------------------------------------------------
def gauntlet(cards, color="Green"):
    s = build(cards, ["Gauntlet of Power"], ["Forest", "Island"], forests=2, islands=4)
    mine = put(s, "Forest")
    to_hand(s, "Gauntlet of Power")
    mana(s, C=5)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Gauntlet of Power").id)
    choose_color(s, color)
    return s, mine


def to_bobs_main(s):
    for _ in range(60):
        if s.state.turn.active_player == "p2" and s.state.turn.phase == "main1" and s.state.rules.decision is None:
            return
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached Bob's main phase")


def test_gauntlet_of_power_gives_the_extra_mana_to_the_controller_of_any_basic_land_tapped_for_the_chosen_color(cards):
    s, mine = gauntlet(cards, "Green")
    tap_for_mana(s, mine)
    assert pool(s) == {"G": 2}  # Alice's own Forest
    to_bobs_main(s)
    forest, island = put(s, "Forest", "p2"), put(s, "Island", "p2")
    tap_for_mana(s, forest, "p2")
    assert pool(s, "p2") == {"G": 2}  # Bob's Forest: HIS extra mana, though Alice's Gauntlet makes it (its controller adds it)
    tap_for_mana(s, island, "p2")
    assert pool(s, "p2") == {"G": 2, "U": 1}  # not green: no extra
    check(s)


def test_gauntlet_of_power_no_color_chosen_means_no_extra_mana(cards):
    s = build(cards, ["Gauntlet of Power"], forests=2)
    forest = put(s, "Forest")
    put(s, "Gauntlet of Power")  # put there by hand: nothing chose a color
    tap_for_mana(s, forest)
    assert pool(s) == {"G": 1}  # the ruling (2022-12-08): its last ability never triggers
    check(s)


# ---- Starting Town [704] ---------------------------------------------------------------------------------------------------------------------------------
def test_starting_town_enters_untapped_on_the_first_turn_you_take(cards):
    s = build(cards, ["Starting Town"])
    to_hand(s, "Starting Town")
    act(s, "p1", type="play_land", card_id=card_named(s, "Starting Town").id)
    assert not tapped(s, card_named(s, "Starting Town"))
    check(s)


def test_starting_town_enters_untapped_on_your_third_turn(cards):
    s = build(cards, ["Starting Town"])
    to_hand(s, "Starting Town")
    next_turn(s)
    next_turn(s)  # Alice's third turn (turn 5)
    assert s.state.turn.number == 5
    act(s, "p1", type="play_land", card_id=card_named(s, "Starting Town").id)
    assert not tapped(s, card_named(s, "Starting Town"))
    check(s)


def test_starting_town_enters_tapped_on_your_fourth_turn(cards):
    s = build(cards, ["Starting Town"])
    to_hand(s, "Starting Town")
    for _ in range(3):
        next_turn(s)  # Alice's second, third and fourth turns (turns 3, 5 and 7)
    assert s.state.turn.number == 7 and s.state.turn.active_player == "p1"
    act(s, "p1", type="play_land", card_id=card_named(s, "Starting Town").id)
    assert tapped(s, card_named(s, "Starting Town"))  # the fourth: not one of "first, second, or third"
    check(s)


def test_starting_town_counts_each_players_own_turns(cards):
    s = build(cards, [], ["Starting Town"])
    to_bobs_main(s)
    assert s.state.turn.number == 2
    to_hand(s, "Starting Town", "p2")
    act(s, "p2", type="play_land", card_id=card_named(s, "Starting Town", "p2").id)
    assert not tapped(s, card_named(s, "Starting Town", "p2"))  # Bob's first turn of the game, though it is turn 2 of the table
    check(s)
