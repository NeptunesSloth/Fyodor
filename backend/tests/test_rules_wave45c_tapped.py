"""Wave 45C: tap events know who tapped and whether it was the attack declaration (CR 2026-09-25, real Oracle text, tests/fixtures/wave45c_cards.json).
Every scenario checks the replay and a save and a load.

* 701.26a, 508.1f: "Whenever a creature an opponent controls becomes tapped, if it isn't being declared as an attacker" (Rhoda, Verity Circle): a creature that
  becomes tapped any other way (an effect, a cost, a mana ability) counts; a creature tapped as it is declared an attacker does not.
* 603.2c: "Whenever you tap one or more untapped creatures your opponents control" (Sharae): the player whose effect tapped them; only once each turn.
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.test_rules_wave38a_trailing_ifs import hand, table
from tests.wave9c_kit import card_named, cast, check, mana, put, to_hand
from tests.wave36a_kit import attack_as, ready, resolve_stack, to_turn_of
from tests.wave45c_kit import make_repo, pt_of


@pytest.fixture()
def cards(settings):
    repo = make_repo(settings)
    yield repo
    repo.close()


@pytest.mark.parametrize("name", ["Sharae of Numbing Depths", "Rhoda, Geist Avenger", "Verity Circle"])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def ice(s, target, pid="p1"):
    """``pid`` casts Ice (the second half of Fire // Ice: tap target permanent, draw a card) on ``target``."""
    to_hand(s, "Fire // Ice", pid)
    mana(s, pid, U=1, G=1)
    act(s, pid, type="cast_spell", card_id=card_named(s, "Fire // Ice", pid).id, face=1, targets=[target.id])
    resolve_stack(s)


def test_rhoda_grows_when_an_opponents_creature_becomes_tapped_by_an_effect(cards):
    s = table(cards, ["Rhoda, Geist Avenger", "Fire // Ice"], ["Grizzly Bears"])
    put(s, "Rhoda, Geist Avenger")
    bears = put(s, "Grizzly Bears", "p2")
    ice(s, bears)
    assert s.state.cards[bears.id].tapped and card_named(s, "Rhoda, Geist Avenger").id in s.state.cards
    assert pt_of(s, "Rhoda, Geist Avenger") == (4, 4)
    check(s)


def test_rhoda_ignores_your_own_creatures_and_an_attacker_being_declared(cards):
    s = table(cards, ["Rhoda, Geist Avenger", "Grizzly Bears", "Fire // Ice"], ["Grizzly Bears"])
    put(s, "Rhoda, Geist Avenger")
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", "p2")
    ice(s, mine)  # (a creature you control)
    assert pt_of(s, "Rhoda, Geist Avenger") == (3, 3)
    to_turn_of(s, "p2")
    ready(s, "Grizzly Bears", pid="p2")
    attack_as(s, "p2", [theirs], "p1")  # (tapped as it is declared an attacker, 508.1f)
    until(s, lambda s: s.state.turn.phase == "end_combat")
    assert s.state.cards[theirs.id].tapped and pt_of(s, "Rhoda, Geist Avenger") == (3, 3)
    check(s)


def test_verity_circle_draws_for_a_creature_tapped_otherwise_than_by_attacking(cards):
    s = table(cards, ["Verity Circle", "Fire // Ice"], ["Grizzly Bears"])
    put(s, "Verity Circle")
    bears = put(s, "Grizzly Bears", "p2")
    before = hand(s)
    ice(s, bears)  # (Ice draws one, Verity Circle one more)
    assert hand(s) == before + 2
    check(s)


def lib(s):
    return len(s.state.zones["p1:library"])


def test_sharae_draws_once_each_turn_when_you_tap_an_opponents_creature(cards):
    s = table(cards, ["Sharae of Numbing Depths", "Fire // Ice"], ["Grizzly Bears", "Grizzly Bears"])
    a, b = (c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2")
    act(s, "p2", type="move", card_ids=[a.id, b.id], to={"player": "p2", "zone": "battlefield"})
    to_hand(s, "Sharae of Numbing Depths")
    mana(s, W=1, U=1, G=2)
    before = lib(s)
    cast(s, "Sharae of Numbing Depths")
    resolve_stack(s)  # (its enter trigger taps one of Bob's creatures: you tap an untapped creature an opponent controls)
    assert lib(s) == before - 1 and s.state.cards[a.id].tapped is not s.state.cards[b.id].tapped
    ice(s, b if s.state.cards[a.id].tapped else a)  # (a second one this turn: Ice was drawn by the first; only Ice's own card, no Sharae card: once each turn)
    assert lib(s) == before - 2
    check(s)


def test_sharae_draws_for_an_effect_that_taps_after_it_entered_and_not_for_your_own_creature(cards):
    s = table(cards, ["Sharae of Numbing Depths", "Grizzly Bears", "Fire // Ice"], ["Grizzly Bears"])
    put(s, "Sharae of Numbing Depths")
    mine = put(s, "Grizzly Bears")
    theirs = put(s, "Grizzly Bears", "p2")
    before = lib(s)
    ice(s, mine)  # (a creature you control: the card to the hand and Ice's draw, no Sharae card)
    assert lib(s) == before - 2
    ice(s, theirs)  # (the same Ice from the graveyard, on an opponent's creature: its own card and Sharae's)
    assert lib(s) == before - 4
    check(s)


def test_sharae_ignores_an_opponent_tapping_its_own_attacker(cards):
    s = table(cards, ["Sharae of Numbing Depths"], ["Grizzly Bears"])
    put(s, "Sharae of Numbing Depths")
    theirs = put(s, "Grizzly Bears", "p2")
    to_turn_of(s, "p2")
    ready(s, "Grizzly Bears", pid="p2")
    before = lib(s)
    attack_as(s, "p2", [theirs], "p1")
    until(s, lambda s: s.state.turn.phase == "end_combat")
    assert s.state.cards[theirs.id].tapped and lib(s) == before
    check(s)
