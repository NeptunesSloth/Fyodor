"""Wave 52C: the Wishes, cards from outside the game (CR 701.20a, 608.2d, 400.1), real Oracle text (tests/fixtures/wave52c_cards.json, from data/cards.sqlite). Every scenario checks the
replay and a save and a load.

* The cards a player owns outside the game are their sideboard's (hidden from the other players): the player may choose a matching one, it is revealed ("reveal … and put it into your
  hand") and goes to their hand; "put a card you own from outside the game into your hand" (Death Wish) reveals nothing. Karn and Coax may also choose a face-up card in exile.
* The question is asked even when nothing matches: that it appears must tell the other players nothing about the sideboard.
"""

from __future__ import annotations

import json

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand, zone_of
from tests.wave52c_kit import move, open_repo

WISHES = ["Burning Wish", "Living Wish", "Cunning Wish", "Glittering Wish", "Golden Wish", "Death Wish"]
OTHERS = ["Coax from the Blind Eternities", "Karn, the Great Creator", "Vivien, Arkbow Ranger", "North Wind Avatar", "Fae of Wishes // Granted"]
BURNING, DEATH, KARN, COAX = "Burning Wish", "Death Wish", "Karn, the Great Creator", "Coax from the Blind Eternities"
GROWTH, BOLT = "Rampant Growth", "Lightning Bolt"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [*WISHES, *OTHERS])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def ask(s):
    d = s.state.rules.decision
    assert d is not None, "no question"
    return d


def test_burning_wish_fetches_a_sorcery_from_the_sideboard_and_reveals_it(cards):
    s = build(cards, [BURNING, GROWTH, BOLT], [])
    move(s, GROWTH, "sideboard")
    move(s, BOLT, "sideboard")
    to_hand(s, BURNING)
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, BURNING).id)
    d = ask(s)
    assert d.player == "p1" and [s.state.cards[o.id].name for o in d.options] == [GROWTH]  # (the instant isn't a sorcery card)
    assert GROWTH not in json.dumps(s.view("p2"), default=str)  # a sideboard is hidden from the other players
    check(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert zone_of(s, GROWTH) == "p1:hand" and zone_of(s, BOLT) == "p1:sideboard"
    assert zone_of(s, BURNING) == "p1:exile"  # "Exile Burning Wish."
    assert s.state.rules.decision is None
    check(s)


def test_the_question_is_asked_with_nothing_to_choose_and_none_is_allowed(cards):
    s = build(cards, [BURNING], [])
    to_hand(s, BURNING)
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, BURNING).id)
    d = ask(s)  # (it is asked either way: whether it appears says nothing about the sideboard)
    assert d.player == "p1" and d.options == [] and d.min_choices == 0
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    assert zone_of(s, BURNING) == "p1:exile" and s.state.rules.decision is None
    check(s)


def test_death_wish_takes_any_card_without_revealing_it_and_costs_half_the_life(cards):
    s = build(cards, [DEATH, BOLT], [])
    move(s, BOLT, "sideboard")
    to_hand(s, DEATH)
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, DEATH).id)
    d = ask(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert zone_of(s, BOLT) == "p1:hand" and life(s) == 20 and zone_of(s, DEATH) == "p1:exile"  # (half of 40, rounded up)
    assert BOLT not in json.dumps(s.view("p2"), default=str)  # (not revealed: neither the log nor the hand shows it)
    check(s)


def test_karn_may_choose_a_face_up_artifact_in_exile(cards):
    s = build(cards, [KARN, "Sol Ring", "Arcane Signet"], [])
    karn = put(s, KARN)
    act(s, "p1", type="counter", card_ids=[karn.id], kind="loyalty", delta=3)
    move(s, "Sol Ring", "exile")
    move(s, "Arcane Signet", "sideboard")
    act(s, "p1", type="activate_ability", card_id=card_named(s, KARN).id, ability=2)
    d = ask(s)
    assert {s.state.cards[o.id].name for o in d.options} == {"Sol Ring", "Arcane Signet"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if s.state.cards[o.id].name == "Sol Ring")])
    assert zone_of(s, "Sol Ring") == "p1:hand"
    check(s)


def test_a_wish_never_reaches_for_the_opponents_sideboard(cards):
    s = build(cards, [BURNING], [GROWTH])
    move(s, GROWTH, "sideboard", pid="p2")
    to_hand(s, BURNING)
    mana(s, R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, BURNING).id)
    assert ask(s).options == []
    check(s)
