"""Wave 110A: See the Unwritten (ruling 2014-09-20: ferocious is checked before any card enters; "instead" gives only the upgraded effect)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.wave110a_kit import *

SEE = "See the Unwritten"
NAMES = ["Grizzly Bears", "Llanowar Elves", "Muscle Sliver"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def _scene(cards, ferocious):
    s = build(cards, [SEE, *NAMES, "Shivan Dragon"])
    if ferocious:
        put(s, "Shivan Dragon")
    for n in NAMES:
        c = to_hand(s, n)
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "library"}, position="top")
    cast(s, SEE)
    return s


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(SEE)).level == "FULL"


@pytest.mark.parametrize(("ferocious", "entered"), [(False, 1), (True, 2)])
def test_puts_one_creature_or_two_with_ferocious_and_the_rest_go_to_the_graveyard(cards, ferocious, entered):
    s = _scene(cards, ferocious)
    answer(s, NAMES[:entered])
    bf = [n for n in NAMES if card_named(s, n).zone == "p1:battlefield"]
    assert bf == NAMES[:entered]  # 701.20 reveal, 400.7: the chosen creatures entered, none more (instead, not in addition)
    assert all(card_named(s, n).zone == "p1:graveyard" for n in NAMES[entered:])
    assert len(s.state.zones["p1:graveyard"]) == 8 - entered + 1  # the rest of the eight revealed cards, and the spell itself
    check(s)


def test_without_ferocious_a_second_creature_cannot_be_chosen(cards):
    s = _scene(cards, False)
    d = s.state.rules.decision
    assert d is not None and d.max_choices == 1
