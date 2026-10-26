"""Wave 110B session 14 (real Oracle text in tests/fixtures/wave110b_cards.json).

* Tranquil Frillback: 107.1b pay {G} up to three times, 603.12 the reflexive ability, 700.2b "choose up to that many" modes = the times paid.
"""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import build, card_named, check, drive, life, mana, put, repository, to_hand


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Tranquil Frillback")).level == "FULL"


def frillback(cards, G, times, modes):
    """Cast it with {2}{G} + ``G`` more green; pay ``times``; choose the mode indexes ``modes`` (artifact and enchantment targets exist)."""
    s = build(cards, ["Tranquil Frillback", "Sol Ring"], ["Grizzly Bears"], forests=30)
    ring = put(s, "Sol Ring")
    to_hand(s, "Tranquil Frillback")
    mana(s, G=3 + G)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Tranquil Frillback").id)
    seen = []

    def answer(d):
        seen.append(d.prompt)
        if "how many times" in d.prompt:
            return [f"x:{times}"] if times else ["decline"]
        if d.kind == "choose_cards" and "mode" in d.prompt:
            return [f"{i}:0" for i in modes]
        return None
    drive(s, answer)
    return s, ring, seen


def test_pay_twice_two_modes(cards):
    s, ring, seen = frillback(cards, 2, 2, [0, 2])
    assert s.state.cards[ring.id].zone.endswith("graveyard") and life(s, "p1") == 44  # destroy artifact, gain 4 (40 + 4)
    assert any("up to two" in p for p in seen)
    check(s)


def test_pay_once_limits_to_one_mode(cards):
    s, ring, seen = frillback(cards, 3, 1, [2])
    assert s.state.cards[ring.id].zone.endswith("battlefield") and life(s, "p1") == 44
    assert any("up to one" in p for p in seen)
    check(s)


def test_pay_nothing_no_modes(cards):
    s, ring, _ = frillback(cards, 3, 0, [])
    assert s.state.cards[ring.id].zone.endswith("battlefield") and life(s, "p1") == 40
    check(s)


def test_hawkeye_attack_pays_once_for_one_mode(cards):
    """Hawkeye (same "pay {1} up to three times ... choose up to that many" with ability word and mode labels): attacking taps it (603.2)."""
    assert coverage.of_card_data(cards.resolve("Hawkeye, Master Marksman")).level == "FULL"
    from tests.wave110b_kit import attack

    s = build(cards, ["Hawkeye, Master Marksman"], ["Grizzly Bears"], forests=30)
    hawk = put(s, "Hawkeye, Master Marksman")
    mana(s, G=3)

    def answer(d):
        if "how many times" in d.prompt:
            return ["x:1"]
        if d.kind == "choose_cards" and "mode" in d.prompt:
            return ["1:0"]
        return None
    attack(s, hawk)
    drive(s, answer)
    assert life(s, "p2") == 38  # Explosive: 2 damage to target player (before combat damage)
    check(s)
