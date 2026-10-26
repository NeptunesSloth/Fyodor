"""Wave 110N: Sword-Point Diplomacy (118.12: for each revealed card an opponent may pay 3 life to keep it out of the hand; 701.20 reveal)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

SWORD = "Sword-Point Diplomacy"
EXTRA = [real(SWORD, "{2}{R}", 3, "Sorcery",
              "Reveal the top three cards of your library. For each of those cards, put that card into your hand unless any opponent pays 3 life. Then exile the rest.", None, "R")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([SWORD])


def run(cards, answers, bob_life=40):
    s = build(cards, [SWORD])
    act(s, "p1", type="set_life", player="p2", value=bob_life)
    to_hand(s, SWORD)
    top = list(s.state.zones["p1:library"][:3])
    hand0 = len(s.state.zones["p1:hand"])  # (with the Sword)
    cast(s, SWORD)
    answer(s, *answers)
    return s, top, hand0


@pytest.mark.parametrize(("answers", "paid"), [
    (["decline", "decline", "decline"], 0),
    (["pay", "decline", "decline"], 1),
    (["decline", "pay", "pay"], 2),
    (["pay", "pay", "pay"], 3),
])
def test_each_card_goes_to_hand_unless_an_opponent_pays(cards, answers, paid):
    s, top, hand0 = run(cards, answers)
    kept = [c for a, c in zip(answers, top, strict=True) if a == "decline"]
    lost = [c for a, c in zip(answers, top, strict=True) if a == "pay"]
    assert life(s, "p2") == 40 - 3 * paid
    assert all(s.state.cards[c].zone == "p1:hand" for c in kept)
    assert all(s.state.cards[c].zone == "p1:exile" for c in lost)
    assert len(s.state.zones["p1:hand"]) == hand0 - 1 + len(kept)
    check(s)


def test_an_opponent_who_cant_pay_is_not_asked(cards):
    s, top, _ = run(cards, [], bob_life=2)
    assert s.state.rules.decision is None and life(s, "p2") == 2
    assert all(s.state.cards[c].zone == "p1:hand" for c in top)
    check(s)
