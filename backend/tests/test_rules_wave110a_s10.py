"""Wave 110A session 10: real Oracle text cards (tests/fixtures/wave110a_cards.json), each scenario checks replay and save/load.

* Yuna's Decision - 701.21a sacrifice, then (608.2c) "If you do" draw and put at most one creature card and one land card from hand onto the battlefield.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *

YUNA = "Yuna's Decision"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([YUNA])


def _on_bf(s, name):
    return sum(1 for c in s.state.cards.values() if c.name == name and c.zone == "p1:battlefield")


def test_yuna_sacrifices_draws_and_puts_a_creature_and_a_land(cards):
    s = build(cards, [YUNA, "Muscle Sliver", "Grizzly Bears", "Forest"])
    put(s, "Muscle Sliver")
    to_hand(s, "Grizzly Bears")
    to_hand(s, "Forest")
    cast(s, YUNA, modes=[0])
    answer(s)
    assert _on_bf(s, "Muscle Sliver") == 0 and zone_of(s, "Muscle Sliver") == "p1:graveyard"
    assert _on_bf(s, "Grizzly Bears") == 1 and _on_bf(s, "Forest") == 1
    check(s)


def test_yuna_does_nothing_more_without_a_creature_to_sacrifice(cards):
    s = build(cards, [YUNA, "Grizzly Bears", "Forest"])
    bears = to_hand(s, "Grizzly Bears")
    cast(s, YUNA, modes=[0])
    answer(s)
    assert s.state.cards[bears.id].zone == "p1:hand"  # 608.2c: "If you do" - nothing was sacrificed, so no puts
    check(s)
