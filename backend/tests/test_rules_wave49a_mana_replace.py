"""Wave 49A: temporary and mapped replacements of the mana a land makes (CR 2026-09-25), real Oracle text (tests/fixtures/wave49a_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 106.12b, 614.1a: "Until end of turn, if you tap a land you control for mana, it produces {U} instead of any other type." (Deep Water) - the type changes, the amount does
  not (ruling 2008-08-01); lands another player controls are untouched; it ends in the cleanup step (514.2).
* "… one mana of a color of your choice instead of any other type and amount." (Harvest Mage) - five options, one mana, for any land tapped this turn.
* "Until end of turn, if a player taps a nonbasic land for mana, it produces colorless mana instead of any other type." (Pale Moon) - any player's nonbasic lands only.
* "If tapped for mana, Plains produce {R}, Islands produce {G}, … instead of any other type." (Naked Singularity, Reality Twist) - the color follows the land's basic land
  types; a land with several mapped types lets the tapper choose either color (rulings 2013-04-15); a land whose types are not listed is untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from app.rules.casting import mana_abilities
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, mana_pool
from tests.test_rules_wave34b_activated import activate, next_turn, settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand
from tests.wave43b_kit import cast

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave49a_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w49a", number=f"A{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]
FULL = ["Deep Water", "Harvest Mage", "Pale Moon", "Naked Singularity", "Reality Twist"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def options(s, name, pid="p1"):
    """What the land's mana abilities can produce now (one tuple per way to tap it)."""
    return sorted({opt for _, ab in mana_abilities(s.state, s.state.cards[card_named(s, name, pid).id], s.cards) for opt in ab.options})


def test_the_cards_are_full(cards):
    for name in FULL:
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


def test_deep_water_makes_your_lands_produce_blue_until_end_of_turn(cards):
    s = build(cards, ["Deep Water", "Mountain"], ["Mountain"])
    water, mountain = put(s, "Deep Water"), put(s, "Mountain")
    put(s, "Mountain", "p2")
    assert options(s, "Mountain") == [("R",)]
    mana(s, U=1)
    activate(s, "p1", water)
    settle(s)
    assert options(s, "Mountain") == [("U",)] and options(s, "Mountain", "p2") == [("R",)]  # only the lands Alice controls
    act(s, "p1", type="activate_ability", card_id=mountain.id, ability=0)
    assert mana_pool(s) == {"U": 1}
    check(s)
    next_turn(s)
    assert options(s, "Mountain") == [("R",)]  # it ended with the turn (514.2)
    check(s)


def test_harvest_mage_lets_a_land_make_one_mana_of_any_color(cards):
    s = build(cards, ["Harvest Mage", "Mountain"])
    mage = put(s, "Harvest Mage")
    put(s, "Mountain")
    to_hand(s, "Forest")  # (the card to discard)
    next_turn(s)  # (summoning sickness)
    mana(s, G=1)
    activate(s, "p1", mage)
    settle(s)
    assert options(s, "Mountain") == [("B",), ("G",), ("R",), ("U",), ("W",)]
    check(s)


def test_pale_moon_makes_nonbasic_lands_of_any_player_colorless(cards):
    s = build(cards, ["Pale Moon", "Tundra", "Mountain"], ["Tundra"])
    to_hand(s, "Pale Moon")
    for name, pid in (("Tundra", "p1"), ("Mountain", "p1"), ("Tundra", "p2")):
        put(s, name, pid)
    assert options(s, "Tundra") == [("U",), ("W",)]
    mana(s, U=1, C=1)
    cast(s, "Pale Moon")
    assert options(s, "Tundra") == [("C",)] and options(s, "Tundra", "p2") == [("C",)]
    assert options(s, "Mountain") == [("R",)]  # a basic land is untouched
    check(s)


def test_naked_singularity_gives_each_basic_land_type_another_color(cards):
    s = build(cards, ["Naked Singularity", "Plains", "Tundra"], ["Mountain"])
    put(s, "Naked Singularity")
    put(s, "Plains")
    put(s, "Tundra")
    put(s, "Mountain", "p2")
    put(s, "Forest")
    assert options(s, "Plains") == [("R",)] and options(s, "Forest") == [("B",)]
    assert options(s, "Tundra") == [("G",), ("R",)]  # a Plains Island: the tapper chooses either color
    assert options(s, "Mountain", "p2") == [("U",)]
    check(s)


def test_reality_twist_leaves_an_unlisted_type_alone(cards):
    s = build(cards, ["Reality Twist", "Plains", "Tundra"], ["Island", "Swamp"])
    put(s, "Reality Twist")
    put(s, "Plains")
    put(s, "Tundra")
    put(s, "Island", "p2")
    put(s, "Swamp", "p2")
    assert options(s, "Plains") == [("R",)]
    assert options(s, "Tundra") == [("R",)]  # it is a Plains; Islands are not listed
    assert options(s, "Island", "p2") == [("U",)]
    assert options(s, "Swamp", "p2") == [("G",)]
    check(s)
