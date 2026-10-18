"""Wave 52A: "that player" of a card put into a graveyard (CR 2026-09-25), real Oracle text (tests/fixtures/wave52a_cards.json, from data/cards.sqlite). Every scenario checks the
replay and a save and a load.

* 603.4 / 118.12 / 608.2c: Bloodchief Ascension - "Whenever a card is put into an opponent's graveyard from anywhere, if this enchantment has three or more quest counters on it,
  you may have that player lose 2 life. If you do, you gain 2 life." (that player: the owner of the graveyard, 400.3; "if you do" reads that she chose to, 118.12).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import activate, settle
from tests.wave9c_kit import build, card_named, check, life, mana, put, to_hand
from tests.wave52a_kit import open_repo

ASCENSION, SORIN = "Bloodchief Ascension", "Sorin, Lord of Innistrad"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [ASCENSION, SORIN])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def ascension(cards, counters):
    s = build(cards, [ASCENSION, "Grizzly Bears", "Lightning Bolt"], ["Hill Giant"])
    a = put(s, ASCENSION)
    put(s, "Hill Giant", "p2")
    put(s, "Grizzly Bears")
    if counters:
        act(s, "p1", type="counter", card_ids=[a.id], kind="quest", delta=counters)
    return s


def to_graveyard(s, name, pid):
    """Lightning Bolt (the Bolt itself goes to Alice's graveyard when it resolves) kills the creature: it dies into its owner's graveyard."""
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[card_named(s, name, pid).id])


def answer(s, option):
    d = s.state.rules.decision
    assert d is not None and d.player == "p1"  # "you may": Alice chooses
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[option])
    settle(s)


def test_an_opponents_card_in_the_graveyard_makes_that_player_lose_life_and_you_gain(cards):
    s = ascension(cards, 3)
    to_graveyard(s, "Hill Giant", "p2")
    answer(s, "yes")
    assert life(s, "p2") == 38 and life(s, "p1") == 42
    check(s)


def test_declined_nobody_loses_or_gains(cards):
    s = ascension(cards, 3)
    to_graveyard(s, "Hill Giant", "p2")
    answer(s, "no")
    assert life(s, "p2") == 40 and life(s, "p1") == 40
    check(s)


def test_fewer_than_three_quest_counters_nothing_happens(cards):
    s = ascension(cards, 2)
    to_graveyard(s, "Hill Giant", "p2")
    settle(s)
    assert s.state.rules.decision is None and life(s, "p2") == 40 and life(s, "p1") == 40
    check(s)


def test_a_card_in_your_own_graveyard_does_not_trigger_it(cards):
    s = ascension(cards, 3)
    to_graveyard(s, "Grizzly Bears", "p1")
    settle(s)
    assert s.state.rules.decision is None and life(s, "p2") == 40
    check(s)


# -- Sorin, Lord of Innistrad ------------------------------------------------------------------------------------------------------------
def test_sorin_ultimate_returns_each_card_destroyed_this_way_under_your_control(cards):
    """-6: "Destroy up to three target creatures and/or other planeswalkers. Return each card put into a graveyard this way to the battlefield under your control." (Sorin is no target: "other")"""
    s = build(cards, [SORIN, "Grizzly Bears"], ["Hill Giant"])
    to_hand(s, SORIN)
    mana(s, "p1", W=1, B=1, C=2)
    act(s, "p1", type="cast_spell", card_id=card_named(s, SORIN).id)
    settle(s)
    sorin = card_named(s, SORIN)
    act(s, "p1", type="counter", card_ids=[sorin.id], kind="loyalty", delta=4)
    bears, giant = put(s, "Grizzly Bears"), put(s, "Hill Giant", "p2")
    activate(s, "p1", sorin, contains="−6", targets=[bears.id, giant.id], target_counts=[2])
    settle(s)
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[giant.id].zone == "p1:battlefield"  # both came back
    assert s.state.cards[giant.id].controller == "p1" and s.state.cards[giant.id].owner == "p2"  # Bob's Giant is Alice's now
    assert s.state.cards[sorin.id].zone == "p1:battlefield"  # (not a target: "other planeswalkers"; 7 - 6 = 1 loyalty left)
    check(s)
