"""Wave 110E session 10: Oracle-text scenarios for cards promoted this session (each docstring names the rule)."""
from __future__ import annotations

import tests.test_rules_wave110e_cards as base
from app.rules import coverage
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave30m_durations import stops, to_phase
from tests.test_rules_wave110e_cards import answer, card_db, cast  # noqa: F401  (the fixture)
from tests.wave9c_kit import build, check, life, mana, put

REPROACH = real("Teferi's Reproach", "{2}{W}{W}", 4, "Instant",
                "Choose target opponent. Until that player's next turn, they gain protection from everything and their life total can't change. "
                "All nonland permanents they control phase out. (While they're phased out, they're treated as though they don't exist. "
                "They phase in before that player untaps during their next untap step.)\nExile Teferi's Reproach.", None, "W")
BEAR = real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G")
DRAIN = real("Test Drain", "{B}", 1, "Sorcery", "Each opponent loses 3 life.", None, "B")
base.EXTRA.extend([REPROACH, BEAR, DRAIN])


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Teferi's Reproach")).level == "FULL"


def test_teferis_reproach_shields_the_opponent_until_their_next_turn(cards):
    """702.16j, 119.7, 702.26: target opponent has protection from everything, life can't change, nonland permanents phase out; all end at their turn."""
    s = build(cards, ["Teferi's Reproach", "Test Drain"], ["Test Bear", "Test Bear"])
    bear = put(s, "Test Bear", "p2")
    mana(s, W=2, C=2, B=1)
    cast(s, "Teferi's Reproach", ["p2"])
    answer(s)
    assert s.state.cards[bear.id].zone.endswith(":phased")
    cast(s, "Test Drain")
    answer(s)
    assert life(s, "p2") == 40
    check(s)
    stops(s, "upkeep")
    to_phase(s, "upkeep", 2)
    assert not s.state.cards[bear.id].zone.endswith(":phased")
    assert not s.state.rules.life_locks and not s.state.rules.player_shields
    check(s)
