"""Wave 49C: "the player with the most …" at an upkeep (CR 2026-09-25), real Oracle text (tests/fixtures/wave49c_most_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 603.4, 611.2a: "At the beginning of your upkeep, if a player has more life than each other player, the player with the most life gains control of this creature." (Wild Dogs,
  Ghazbán Ogre), "… more cards in hand …, the player who has the most cards in hand …" (Sokenzan Renegade), "… controls more creatures …" (Wild Mammoth), "… Wizards …"
  (Thoughtbound Primoc) - nobody triggers it on a tie; the player is picked as the ability resolves, and control lasts for good.
* 603.4: "At the beginning of each player's upkeep, if that player controls more lands than each other player, the player creates a 1/1 green Saproling creature token." (Greener
  Pastures), "… this enchantment deals 2 damage to them." (Rivalry) - "each other player" is the players other than the one whose upkeep it is.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import until
from tests.wave9c_kit import build, card_named, check, life, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49c_most_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49c", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = [c["name"] for c in DATA]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def controller(s, name):
    return s.state.cards[card_named(s, name).id].controller


def to_turn(s, number, phase="main1"):
    """Alice's turn 1 into turn ``number``'s ``phase`` (nobody attacks or blocks)."""
    until(s, lambda s: s.state.turn.number == number and s.state.turn.phase == phase)


def test_the_cards_are_full(cards):
    for name in FULL:
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize(("alice", "bob", "after"), [(40, 50, "p2"), (50, 40, "p1"), (40, 40, "p1")])
def test_wild_dogs_goes_to_the_player_with_the_most_life(cards, alice, bob, after):
    s = build(cards, ["Wild Dogs"])
    put(s, "Wild Dogs")
    act(s, "p1", type="set_life", player="p1", value=alice)
    act(s, "p1", type="set_life", player="p2", value=bob)
    to_turn(s, 3)
    assert controller(s, "Wild Dogs") == after  # (a tie: it does not trigger at all)
    check(s)


def test_a_player_who_stays_the_one_with_the_most_keeps_it_on_a_later_upkeep(cards):
    """Bob has the most life at Alice's upkeep and gets the dogs; at Bob's own upkeep the ability (Alice's, as printed on a permanent Bob now controls) is Bob's to trigger."""
    s = build(cards, ["Ghazbán Ogre"])
    put(s, "Ghazbán Ogre")
    act(s, "p1", type="set_life", player="p2", value=45)
    to_turn(s, 3)
    assert controller(s, "Ghazbán Ogre") == "p2"
    check(s)


def test_sokenzan_renegade_goes_to_the_player_with_the_most_cards_in_hand(cards):
    s = build(cards, ["Sokenzan Renegade"], ["Grizzly Bears"])
    put(s, "Sokenzan Renegade")
    for _ in range(3):
        to_hand(s, "Island", "p2")
    to_turn(s, 3)  # (the upkeep passed: Bob's hand, three and the card he drew, against Alice's none)
    assert controller(s, "Sokenzan Renegade") == "p2"
    check(s)


def test_wild_mammoth_stays_when_you_control_the_most_creatures(cards):
    s = build(cards, ["Wild Mammoth", "Grizzly Bears"], ["Grizzly Bears"])
    put(s, "Wild Mammoth")
    put(s, "Grizzly Bears")
    put(s, "Grizzly Bears", "p2")
    to_turn(s, 3)
    assert controller(s, "Wild Mammoth") == "p1"  # 2 and 1: Alice has the most (she "gains" what she has)
    check(s)


def test_wild_mammoth_goes_to_the_player_with_more_creatures(cards):
    s = build(cards, ["Wild Mammoth"], ["Grizzly Bears", "Llanowar Elves"])
    put(s, "Wild Mammoth")
    put(s, "Grizzly Bears", "p2")
    put(s, "Llanowar Elves", "p2")
    to_turn(s, 3)
    assert controller(s, "Wild Mammoth") == "p2"
    check(s)


def test_thoughtbound_primoc_goes_to_the_player_with_the_most_wizards(cards):
    s = build(cards, ["Thoughtbound Primoc"], ["Prodigal Sorcerer"])
    put(s, "Thoughtbound Primoc")  # (a Bird Beast: Alice has no Wizard)
    put(s, "Prodigal Sorcerer", "p2")  # (Human Wizard Sorcerer)
    to_turn(s, 3)
    assert controller(s, "Thoughtbound Primoc") == "p2"
    check(s)


def test_thoughtbound_primoc_stays_when_nobody_has_more_wizards(cards):
    s = build(cards, ["Thoughtbound Primoc"])
    put(s, "Thoughtbound Primoc")
    to_turn(s, 3)  # no Wizards at all: nobody controls more than each other player
    assert controller(s, "Thoughtbound Primoc") == "p1"
    check(s)


def saprolings(s, pid):
    return [c for c in s.state.cards.values() if c.token is not None and c.name == "Saproling" and c.controller == pid and c.zone == f"{pid}:battlefield"]


def test_greener_pastures_makes_a_saproling_for_the_player_with_the_most_lands(cards):
    s = build(cards, ["Greener Pastures"])
    put(s, "Greener Pastures")
    for _ in range(3):
        put(s, "Forest")  # Alice 3 lands, Bob none
    to_turn(s, 3)
    assert len(saprolings(s, "p1")) == 1 and not saprolings(s, "p2")  # (Bob's upkeep passed first: he has fewer lands)
    check(s)


def test_greener_pastures_does_nothing_for_a_tie(cards):
    s = build(cards, ["Greener Pastures"])
    put(s, "Greener Pastures")
    put(s, "Forest")
    put(s, "Island", "p2")
    to_turn(s, 3)
    assert not saprolings(s, "p1") and not saprolings(s, "p2")
    check(s)


def test_rivalry_hurts_the_player_with_the_most_lands(cards):
    s = build(cards, ["Rivalry"])
    put(s, "Rivalry")
    put(s, "Island", "p2")
    put(s, "Island", "p2")
    to_turn(s, 3)  # Bob's upkeep (turn 2) passed: he has two lands to Alice's none; Alice's own (turn 3) hurts nobody
    assert life(s, "p2") == 38 and life(s, "p1") == 40
    check(s)
