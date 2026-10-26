"""Wave 110C: Phylactery Lich. 614.1c / 614.12a (the counter is put as it enters, a replacement, not a trigger), 603.8 (state trigger: sacrifice when no
permanent has a phylactery counter), 122.6 (counter put on the chosen artifact)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.wave110c_kit import answer, build, card_named, cast, check, make_db, mana, put, real, zone

LICH = ("Indestructible\nAs this creature enters, put a phylactery counter on an artifact you control.\n"
        "When you control no permanents with phylactery counters on them, sacrifice this creature.")
EXTRA = [real("Phylactery Lich", "{B}{B}{B}", 3, "Creature — Zombie", LICH, ("5", "5"), "B"),
         real("Test Rock", "{1}", 1, "Artifact", "{T}: Add {C}.", None, ""),
         real("Test Smash", "{R}", 1, "Instant", "Destroy target artifact.", None, "R"),
         real("Test Gem", "{2}", 2, "Artifact", "{T}: Add {C}.", None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Phylactery Lich")).level == "FULL"


def counters(s, name):
    return card_named(s, name).counters.get("phylactery", 0)


def test_one_artifact_gets_the_counter_and_lich_stays(cards):
    s = build(cards, ["Phylactery Lich", "Test Rock"])
    put(s, "Test Rock")
    mana(s, B=3)
    cast(s, "Phylactery Lich")
    answer(s)
    assert counters(s, "Test Rock") == 1
    assert zone(s, card_named(s, "Phylactery Lich")) == "p1:battlefield"
    check(s)


def test_two_artifacts_the_controller_chooses(cards):
    s = build(cards, ["Phylactery Lich", "Test Rock", "Test Gem"])
    put(s, "Test Rock")
    gem = put(s, "Test Gem")
    mana(s, B=3)
    cast(s, "Phylactery Lich")
    answer(s, gem.id)
    assert counters(s, "Test Gem") == 1 and counters(s, "Test Rock") == 0
    assert zone(s, card_named(s, "Phylactery Lich")) == "p1:battlefield"
    check(s)


def test_no_artifact_lich_is_sacrificed(cards):  # 603.8: nothing carries a counter
    s = build(cards, ["Phylactery Lich"])
    mana(s, B=3)
    cast(s, "Phylactery Lich")
    answer(s)
    assert zone(s, card_named(s, "Phylactery Lich")) == "p1:graveyard"


def test_losing_the_artifact_sacrifices_the_lich(cards):
    s = build(cards, ["Phylactery Lich", "Test Rock", "Test Smash"])
    rock = put(s, "Test Rock")
    mana(s, B=3)
    cast(s, "Phylactery Lich")
    answer(s)
    mana(s, R=1)
    cast(s, "Test Smash", [rock.id])
    answer(s)
    assert zone(s, card_named(s, "Phylactery Lich")) == "p1:graveyard"
