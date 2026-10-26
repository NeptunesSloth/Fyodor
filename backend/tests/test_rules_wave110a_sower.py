"""Wave 110A: Sower of Discord: choose two players as it enters (614.12a); damage to either makes the other also lose that much life (120.1, 119.3)."""

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, cast, check, life, make_db, mana, real

EXTRA = [real("Sower of Discord", "{4}{B}{B}", 6, "Creature — Demon",
              "Flying\nAs this creature enters, choose two players.\nWhenever damage is dealt to one of the chosen players, the other chosen player also loses that much life.",
              ("6", "6"), "B"),
         real("Lightning Bolt", "{R}", 1, "Instant", "Lightning Bolt deals 3 damage to any target.", None, "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Sower of Discord")).level == "FULL"


def _sower(cards, pair):
    s = build(cards, ["Sower of Discord", "Lightning Bolt"])
    mana(s, "p1", B=2, C=4)
    cast(s, "Sower of Discord")
    answer(s, pair)
    return s


def _bolt(s, target):
    mana(s, "p1", R=1)
    cast(s, "Lightning Bolt", [target])
    answer(s)


def test_damage_to_one_chosen_player_drains_the_other(cards):
    s = _sower(cards, "p1,p2")
    _bolt(s, "p2")
    assert life(s, "p2") == 37 and life(s, "p1") == 37
    check(s)


def test_damage_to_the_other_chosen_player_too(cards):
    s = _sower(cards, "p1,p2")
    _bolt(s, "p1")
    assert life(s, "p1") == 37 and life(s, "p2") == 37
    check(s)


def _three(cards):
    from app.game.factory import PlayerSetup, new_game
    from app.game.session import GameSession
    from tests.game_helpers import deck, enable

    mine = [(1, "Sower of Discord"), (1, "Lightning Bolt"), (9, "Forest")]
    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", mine)), PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])),
              PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(10, "Forest")]))]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def test_three_players_only_the_chosen_pair_counts(cards):
    s = _three(cards)
    mana(s, "p1", B=2, C=4)
    cast(s, "Sower of Discord")
    answer(s, "p2,p3")  # Alice is not one of the chosen players
    _bolt(s, "p1")
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (37, 40, 40)  # (no one is drained)
    _bolt(s, "p3")
    assert (life(s, "p1"), life(s, "p2"), life(s, "p3")) == (37, 37, 37)
    check(s)
