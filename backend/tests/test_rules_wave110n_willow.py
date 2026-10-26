"""Wave 110N: Autumn Willow (609.4, 702.18a: the chosen player's spells and abilities may target it this turn although it has shroud)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import build, cast, check, make_db, mana, put, real

WILLOW = "Autumn Willow"
EXTRA = [real(WILLOW, "{3}{G}{G}", 5, "Legendary Creature — Avatar",
              "Shroud (This creature can't be the target of spells or abilities.)\n{G}: Until end of turn, Autumn Willow can be the target of spells and abilities controlled by target player as though it didn't have shroud.",
              ("4", "4"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(WILLOW)).level == "FULL"


def setup(cards):
    s = build(cards, ["Lightning Bolt", "Grizzly Bears"], [WILLOW])
    willow = put(s, WILLOW, "p2")
    mana(s, "p1", R=2, G=1, C=1)
    mana(s, "p2", G=2)
    cast(s, "Grizzly Bears")
    return s, willow


def activate(s, willow, target):
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    act(s, "p2", type="activate_ability", card_id=willow.id, ability=1, targets=[target])
    while s.state.rules.priority != "p1" or any(c.ability for c in (s.state.cards[i] for i in s.state.zones.get("stack", []))):
        act(s, s.state.rules.priority, type="pass_priority")  # the ability resolves; Alice has priority again


def test_cant_be_targeted_without_the_ability(cards):
    s, willow = setup(cards)
    act(s, "p2", type="pass_priority")  # the Bears resolve: Alice has priority again
    assert s.state.rules.priority == "p1"
    with pytest.raises(ActionError, match="target"):
        cast(s, "Lightning Bolt", [willow.id])


@pytest.mark.parametrize(("chosen", "can"), [("p1", True), ("p2", False)])
def test_only_the_chosen_player_may_target_it(cards, chosen, can):
    s, willow = setup(cards)
    activate(s, willow, chosen)
    if can:
        cast(s, "Lightning Bolt", [willow.id])
        assert s.state.zones.get("stack")
    else:
        with pytest.raises(ActionError, match="target"):
            cast(s, "Lightning Bolt", [willow.id])
    check(s)
