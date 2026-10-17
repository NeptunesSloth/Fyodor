"""Wave 45C: control changes as a trigger event (CR 2026-09-25, real Oracle text, tests/fixtures/wave45c_cards.json).
Every scenario checks the replay and a save and a load.

* 603.10d: "Whenever an opponent gains control of a permanent from you" (Zidane) looks back in time: it triggers for each permanent (Zidane's 2025-06-06
  ruling: one trigger for each, including Zidane itself, and you create the Treasure), also when the effect that gave it away ends (Act of Treason's creature
  returns to its owner).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave38a_trailing_ifs import table
from tests.wave9c_kit import card_named, cast, check, mana, put, to_hand
from tests.wave36a_kit import finish_turn, resolve_stack, to_turn_of
from tests.wave45c_kit import make_repo, treasures, zone


@pytest.fixture()
def cards(settings):
    repo = make_repo(settings)
    yield repo
    repo.close()


def test_zidane_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Zidane, Tantalus Thief")).level == "FULL"


def steal(s, pid, spell, target, **pool):
    """``pid`` casts ``spell`` (from their hand) on ``target``."""
    to_hand(s, spell, pid)
    mana(s, pid, **pool)
    act(s, pid, type="cast_spell", card_id=card_named(s, spell, pid).id, targets=[target.id])
    resolve_stack(s)


def test_an_opponent_taking_zidane_itself_gives_its_old_controller_a_treasure(cards):
    """Control Magic on Zidane (603.10d: it looks back in time; the ruling: "Zidane's last ability will trigger and you'll create a Treasure token")."""
    s = table(cards, ["Zidane, Tantalus Thief"], ["Control Magic"])
    zidane = put(s, "Zidane, Tantalus Thief")
    to_turn_of(s, "p2")
    steal(s, "p2", "Control Magic", zidane, U=2, G=2)
    assert s.state.cards[zidane.id].controller == "p2"
    assert treasures(s, "p1") == 1 and treasures(s, "p2") == 0
    check(s)


def test_an_opponent_taking_another_permanent_of_yours_gives_a_treasure_each(cards):
    s = table(cards, ["Zidane, Tantalus Thief", "Grizzly Bears"], ["Control Magic"])
    put(s, "Zidane, Tantalus Thief")
    bears = put(s, "Grizzly Bears")
    to_turn_of(s, "p2")
    steal(s, "p2", "Control Magic", bears, U=2, G=2)
    assert s.state.cards[bears.id].controller == "p2" and treasures(s, "p1") == 1
    check(s)


def test_the_creature_zidane_stole_goes_back_and_that_is_an_opponent_gaining_control_from_you(cards):
    """Zidane's own enter trigger steals a creature until end of turn: you don't gain a Treasure for gaining it, but you do when it goes back."""
    s = table(cards, ["Zidane, Tantalus Thief"], ["Grizzly Bears"])
    bears = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Zidane, Tantalus Thief")
    mana(s, R=1, W=1, G=3)
    cast(s, "Zidane, Tantalus Thief")
    resolve_stack(s)
    assert s.state.cards[bears.id].controller == "p1" and treasures(s) == 0
    finish_turn(s)
    assert s.state.cards[bears.id].controller == "p2" and treasures(s) == 1
    check(s)


def test_a_permanent_that_was_never_yours_is_no_trigger(cards):
    """Bob takes Carol's creature: it isn't from Alice, so her Zidane makes nothing (and Alice taking Bob's creature isn't an opponent gaining control)."""
    s = table(cards, ["Zidane, Tantalus Thief"], ["Grizzly Bears", "Act of Treason"], players=3)
    put(s, "Zidane, Tantalus Thief")
    bears = put(s, "Grizzly Bears", "p3")
    to_turn_of(s, "p2")
    steal(s, "p2", "Act of Treason", bears, R=1, G=2)
    assert s.state.cards[bears.id].controller == "p2"
    finish_turn(s)
    assert s.state.cards[bears.id].controller == "p3" and treasures(s, "p1") == 0
    assert zone(s, "Zidane, Tantalus Thief") == "p1:battlefield"
    check(s)
