"""Wave 110N: Happily Ever After, real Oracle text. Every scenario checks the replay and a save and a load."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

HEA = "Happily Ever After"
EXTRA = [
    real(HEA, "{3}{W}{W}", 5, "Enchantment",
         "When this enchantment enters, each player gains 5 life and draws a card.\nAt the beginning of your upkeep, if there are five colors among permanents you control, "
         "there are six or more card types among permanents you control and/or cards in your graveyard, and your life total is greater than or equal to your starting life total, you win the game.", None, "W"),
    real("Rainbow Golem", "{5}", 5, "Artifact Creature — Golem", "", ("1", "1"), "WUBRG"),
    real("Plain Bolt", "{R}", 1, "Instant", "Plain Bolt deals 1 damage to any target.", None, "R"),
    real("Plain Pact", "{B}", 1, "Sorcery", "You gain 1 life.", None, "B"),
]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([HEA])


@pytest.mark.parametrize(("golem", "grave", "life_now", "wins"), [
    (True, 2, 40, True),    # Land, Artifact, Creature, Enchantment, Instant, Sorcery: six card types, five colors, life = the starting 40 (903.7)
    (True, 2, 39, False),   # life total below the starting life total
    (False, 2, 40, False),  # only one color among the permanents
    (True, 1, 40, False),   # five card types: the Sorcery is not in the graveyard
    (True, 0, 40, False),   # four card types among the permanents alone
])
def test_wins_only_if_all_three_hold(cards, golem, grave, life_now, wins):
    s = build(cards, [HEA, "Rainbow Golem", "Plain Bolt", "Plain Pact"])
    put(s, "Forest")
    put(s, HEA)
    answer(s)
    if golem:
        put(s, "Rainbow Golem")
    for name in ["Plain Bolt", "Plain Pact"][:grave]:
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="set_life", player="p1", value=life_now)
    try:
        next_turn(s)
        answer(s)
    except ActionError:  # the game ended at the upkeep trigger
        assert wins
    assert (s.state.rules.winner == "p1") == wins
    check(s)
