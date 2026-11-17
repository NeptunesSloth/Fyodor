"""611.3a / 613.8: a layer-6 or layer-7 static's "as long as …" condition and its "for each …" count read the other objects as every layer
leaves them — the flying another static gives (Levitation), the power an anthem gives (Glorious Anthem) — not as their printed values.
A static never applies on the strength of itself: while its condition is judged it is left out (it does not depend on itself), and two
statics whose conditions read each other (a dependency loop, 613.8b) are judged in timestamp order — the earlier one without the later.
Real Oracle text (Scryfall) except the plainly labelled "Test" cards (no printed card's grant or pump is conditioned on another creature's
power: only rule statics are, Bristlepack Sentry and Drowsing Tyrannodon); each scenario checks the replay and a save and a load."""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.test_rules_wave12a_counters_keywords import real
from app.rules import sba
from tests.game_helpers import act
from tests.wave9c_kit import build, check, pt, put

EXTRA = [
    real("Skycat Sovereign", "{W}{U}", 2, "Creature — Elemental Cat", "Flying\nThis creature gets +1/+1 for each other creature you control with "
         "flying.\n{2}{W}{U}: Create a 1/1 white Cat Bird creature token with flying.", ("1", "1"), "WU"),
    real("Radiant, Archangel", "{3}{W}{W}", 5, "Legendary Creature — Angel", "Flying, vigilance\nRadiant gets +1/+1 for each other creature on the "
         "battlefield with flying.", ("3", "3"), "W"),
    real("Escaped Shapeshifter", "{3}{U}{U}", 5, "Creature — Shapeshifter", "As long as an opponent controls a creature with flying not named Escaped "
         "Shapeshifter, this creature has flying. The same is true for first strike, trample, and protection from any color.", ("3", "4"), "U"),
    real("Levitation", "{2}{U}{U}", 4, "Enchantment", "Creatures you control have flying.", None, "U"),
    real("Favorable Winds", "{1}{U}", 2, "Enchantment", "Creatures you control with flying get +1/+1.", None, "U"),
    real("Glorious Anthem", "{1}{W}{W}", 3, "Enchantment", "Creatures you control get +1/+1.", None, "W"),
    real("Bristlepack Sentry", "{1}{G}", 2, "Creature — Plant Wolf", "Defender\nAs long as you control a creature with power 4 or greater, this "
         "creature can attack as though it didn't have defender.", ("3", "3"), "G"),
    # (labelled test cards: a pump and a grant conditioned on power)
    real("Test Ferocious Cub", "{1}{G}", 2, "Creature — Cat", "This creature gets +2/+2 as long as you control a creature with power 4 or greater.",
         ("3", "3"), "G"),
    real("Test Ferocious Hawk", "{1}{U}", 2, "Creature — Bird", "This creature has flying as long as you control another creature with power 4 or "
         "greater.", ("1", "1"), "U"),
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database
    from tests.fixtures.cards import fixture_cards

    settings.ensure_dirs()
    have = {c["name"] for c in fixture_cards()}
    build_database([*fixture_cards(), *(c for c in EXTRA if c["name"] not in have)], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def pt_of(s, c):
    card = s.state.cards[c.id]
    ch = Plan(s.state, "p1", s.cards, None).ch(card)
    return sba.power(card, ch), sba.toughness(card, ch)


def keywords(s, c):
    return set(Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).keywords)


def test_full(cards):
    for c in EXTRA:
        assert coverage.of_card_data(cards.resolve(c["name"])).level == "FULL", c["name"]


# -- "for each …" counts --


def test_skycat_sovereign_counts_the_creatures_levitation_gives_flying(cards):
    s = build(cards, ["Skycat Sovereign", "Grizzly Bears", "Levitation", "Favorable Winds"])
    put(s, "Skycat Sovereign")
    put(s, "Grizzly Bears")
    assert pt(s, "Skycat Sovereign") == (1, 1)
    put(s, "Levitation")
    assert pt(s, "Skycat Sovereign") == (2, 2)  # the Bears fly now (layer 6): one other creature with flying
    put(s, "Favorable Winds")
    assert pt(s, "Skycat Sovereign") == (3, 3) and pt(s, "Grizzly Bears") == (3, 3)
    check(s)


def test_radiant_counts_an_opponents_creature_their_levitation_gives_flying(cards):
    s = build(cards, ["Radiant, Archangel"], ["Grizzly Bears", "Levitation"])
    put(s, "Radiant, Archangel")
    put(s, "Grizzly Bears", "p2")
    assert pt(s, "Radiant, Archangel") == (3, 3)
    put(s, "Levitation", "p2")
    assert pt(s, "Radiant, Archangel") == (4, 4)
    check(s)


# -- "as long as …" conditions --


def test_escaped_shapeshifter_sees_flying_an_opponents_static_gives(cards):
    s = build(cards, ["Escaped Shapeshifter"], ["Grizzly Bears", "Levitation"])
    shifter = put(s, "Escaped Shapeshifter")
    put(s, "Grizzly Bears", "p2")
    assert "flying" not in keywords(s, shifter)
    put(s, "Levitation", "p2")
    assert "flying" in keywords(s, shifter)
    check(s)


def test_pump_condition_reads_power_an_anthem_gives(cards):
    s = build(cards, ["Test Ferocious Cub", "Bristlepack Sentry", "Glorious Anthem"])
    put(s, "Test Ferocious Cub")
    put(s, "Bristlepack Sentry")
    assert pt(s, "Test Ferocious Cub") == (3, 3)
    put(s, "Glorious Anthem")  # the Sentry is a 4/4 now
    assert pt(s, "Test Ferocious Cub") == (6, 6)
    check(s)


def test_pump_condition_never_satisfies_itself(cards):
    s = build(cards, ["Test Ferocious Cub"])
    put(s, "Test Ferocious Cub")  # a 3/3: only its own +2/+2 would make it a creature with power 4 or greater
    assert pt(s, "Test Ferocious Cub") == (3, 3)
    check(s)


def test_grant_condition_reads_a_pump_that_is_itself_conditional(cards):
    s = build(cards, ["Test Ferocious Hawk", "Test Ferocious Cub", "Bristlepack Sentry", "Glorious Anthem"])
    hawk = put(s, "Test Ferocious Hawk")
    put(s, "Test Ferocious Cub")
    assert "flying" not in keywords(s, hawk)
    put(s, "Bristlepack Sentry")
    put(s, "Glorious Anthem")  # Sentry 4/4 → the Cub gets +2/+2 (6/6) → the Hawk flies
    assert pt(s, "Test Ferocious Cub") == (6, 6) and "flying" in keywords(s, hawk)
    check(s)


def test_two_conditional_pumps_reading_each_other_do_not_lift_each_other(cards):
    s = build(cards, ["Test Ferocious Cub", "Test Ferocious Cub", "Glorious Anthem"])
    cubs = [c for c in s.state.cards.values() if c.name == "Test Ferocious Cub" and c.owner == "p1"]
    assert len(cubs) == 2
    for c in cubs:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    # each would be 5/5 only if the other already were: a loop (613.8b), judged in timestamp order, so neither applies
    assert [pt_of(s, c) for c in cubs] == [(3, 3), (3, 3)]
    put(s, "Glorious Anthem")  # 4/4 each from the anthem: now each satisfies both conditions
    assert [pt_of(s, c) for c in cubs] == [(6, 6), (6, 6)]
    check(s)
