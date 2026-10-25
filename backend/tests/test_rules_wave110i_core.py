"""Wave 110I: real Oracle text; every scenario checks the replay and a save and a load.

* Kraven the Hunter: dies trigger judged on the dead creature's controller's creatures (700.4, 603.10a).
* Green Dragon: an end-of-turn watch on damage to creatures an opponent controls (603.7, 120.3).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave100n_multi import answer, cast
from tests.wave9c_kit import build, check, mana, put, card_named

EXTRA = [
    real("Green Dragon", "{3}{G}{G}", 5, "Creature — Dragon",
         "Flying\nPoison Breath — When this creature enters, until end of turn, whenever a creature an opponent controls is dealt damage, destroy it.",
         ("4", "4"), "G"),
    real("Kraven the Hunter", "{2}{G}{G}", 4, "Legendary Creature — Human Warrior",
         "Trample\nWhenever a creature an opponent controls with the greatest power among creatures that player controls dies, draw a card and put a +1/+1 counter on Kraven the Hunter.",
         ("3", "3"), "G"),
]
NAMES = [c["name"] for c in EXTRA]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("mine", [False, True])
def test_green_dragon_destroys_damaged_opponent_creature_only(cards, mine):
    s = build(cards, ["Green Dragon", "Lightning Bolt", "Garruk's Horde"], ["Garruk's Horde"])
    horde = put(s, "Garruk's Horde", "p1" if mine else "p2")
    mana(s, G=2, C=3)
    cast(s, "Green Dragon")
    answer(s)
    mana(s, R=1)
    cast(s, "Lightning Bolt", [horde.id])
    answer(s)
    assert s.state.cards[horde.id].zone.endswith("graveyard") is (not mine)  # (your own creature isn't "an opponent controls")
    check(s)


@pytest.mark.parametrize("bigger", [False, True])
def test_kraven_draws_and_grows_only_when_the_greatest_power_creature_dies(cards, bigger):
    s = build(cards, ["Kraven the Hunter", "Lightning Bolt"], ["Grizzly Bears", "Garruk's Horde"])
    bears = put(s, "Grizzly Bears", "p2")
    if bigger:
        put(s, "Garruk's Horde", "p2")
    mana(s, G=2, C=2)
    cast(s, "Kraven the Hunter")
    answer(s)
    hand = len(s.state.zones["p1:hand"])
    mana(s, R=1)
    cast(s, "Lightning Bolt", [bears.id])
    answer(s)
    assert s.state.cards[bears.id].zone.endswith("graveyard")
    kraven = card_named(s, "Kraven the Hunter")
    assert (len(s.state.zones["p1:hand"]) - hand + 1, kraven.counters) == ((1, {}) if bigger else (2, {"+1/+1": 1}))
    check(s)
