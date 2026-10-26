"""Wave 110M: stored dice results (706.8). Every scenario checks the replay and a save and a load.

* 706.8a-c: "When this creature enters, roll five six-sided dice and store those results on it.", "At the beginning of combat on your turn, you may reroll any
  number of this creature's stored results." and "This creature gets +X/+X, where X is the greatest number of stored results on it of the same value." (Centaur of Attention).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.test_rules_random_consequences import faces
from tests.wave110m_kit import *

CENTAUR = "Centaur of Attention"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([CENTAUR])


def stored(s, c):
    return sorted(s.state.rules.stored_dice110m.get(s.state.rules.object_id(c.id), []))


def cast_centaur(s, monkeypatch, rolls):
    faces(monkeypatch, rolls)
    c = cast(s, CENTAUR, extra="")
    answer(s)
    return c


def at_combat(s):
    """Pass until the reroll question of the beginning-of-combat trigger is asked (the trigger resolves, 603.3)."""
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            return d
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no reroll question")


def test_etb_stores_five_results_and_power_is_the_biggest_set(cards, monkeypatch):
    s = build(cards, [CENTAUR], ["Elite Vanguard"], forests=20)
    c = cast_centaur(s, monkeypatch, [2, 2, 5, 2, 6])
    assert stored(s, c) == [2, 2, 2, 5, 6]
    assert ch(s, c).pt == (6, 6)  # 3/3 + 3 of a kind (613.4c)
    check(s)


def test_all_different_results_give_plus_one(cards, monkeypatch):
    s = build(cards, [CENTAUR], ["Elite Vanguard"], forests=20)
    c = cast_centaur(s, monkeypatch, [1, 2, 3, 4, 5])
    assert ch(s, c).pt == (4, 4)
    check(s)


def test_combat_reroll_replaces_only_the_chosen_results(cards, monkeypatch):
    s = build(cards, [CENTAUR], ["Elite Vanguard"], forests=20)
    c = cast_centaur(s, monkeypatch, [1, 2, 3, 4, 5])
    stops(s)
    faces(monkeypatch, [5, 5])  # the two rerolled dice
    d = at_combat(s)
    assert d is not None and d.min_choices == 0 and d.max_choices == 5
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["0", "1"])  # the stored 1 and 2
    answer(s)
    assert stored(s, c) == [3, 4, 5, 5, 5]
    assert ch(s, c).pt == (6, 6)
    check(s)


def test_combat_reroll_of_none_changes_nothing(cards, monkeypatch):
    s = build(cards, [CENTAUR], ["Elite Vanguard"], forests=20)
    c = cast_centaur(s, monkeypatch, [3, 3, 4, 5, 6])
    stops(s)
    d = at_combat(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    answer(s)
    assert stored(s, c) == [3, 3, 4, 5, 6]
    assert ch(s, c).pt == (5, 5)
    check(s)


def test_rerolling_everything_stores_five_new_results(cards, monkeypatch):
    s = build(cards, [CENTAUR], ["Elite Vanguard"], forests=20)
    c = cast_centaur(s, monkeypatch, [1, 2, 3, 4, 5])
    stops(s)
    faces(monkeypatch, [6, 6, 6, 6, 1])
    d = at_combat(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["0", "1", "2", "3", "4"])
    answer(s)
    assert stored(s, c) == [1, 6, 6, 6, 6]
    assert ch(s, c).pt == (7, 7)
    check(s)
