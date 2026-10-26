"""Wave 110A: Zenos yae Galvus // Shinryu, Transcendent Rival (608.2c public choice, 611.2c fixed set, 603.10a look-back, 701.28 transform, 603.10f / 104.2b)."""

# ruff: noqa: F403, F405
from __future__ import annotations

from contextlib import suppress

import pytest

from app.game.errors import ActionError
from app.rules import chosen, coverage
from app.rules.plan import Plan
from tests.wave53d_kit import table
from tests.wave110a_kit import *

ZENOS = "Zenos yae Galvus // Shinryu, Transcendent Rival"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def _scene(cards):
    s = table(cards, mine=[ZENOS, "Grizzly Bears", "Llanowar Elves", "Lightning Bolt"], bobs=["Grizzly Bears", "Llanowar Elves"], carols=["Grizzly Bears"])
    put(s, "Grizzly Bears"), put(s, "Llanowar Elves")  # Alice's own
    bob_bears, bob_elves = put(s, "Grizzly Bears", "p2"), put(s, "Llanowar Elves", "p2")
    carol_bears = put(s, "Grizzly Bears", "p3")
    cast(s, ZENOS)
    return s, bob_bears, bob_elves, carol_bears


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(ZENOS)).level == "FULL"


def test_enters_shrinks_every_creature_but_zenos_and_the_chosen_one(cards):
    s, bob_bears, bob_elves, carol_bears = _scene(cards)
    answer(s, bob_bears.id)
    assert s.state.cards[bob_bears.id].zone == "p2:battlefield" and pt(s, "Grizzly Bears", "p2") == (2, 2)  # the chosen creature is spared
    assert s.state.cards[bob_elves.id].zone == "p2:graveyard"  # 1/1 gets -2/-2
    assert s.state.cards[carol_bears.id].zone == "p3:graveyard"  # 2/2 gets -2/-2
    assert card_named(s, ZENOS).zone == "p1:battlefield" and card_named(s, "Llanowar Elves").zone == "p1:graveyard"
    check(s)


def test_chosen_creature_leaving_transforms_zenos_and_a_chosen_opponent_loss_wins(cards):
    s, bob_bears, bob_elves, carol_bears = _scene(cards)
    answer(s, bob_bears.id)
    zenos = card_named(s, ZENOS)
    assert s.state.cards[zenos.id].face == 0
    cast(s, "Lightning Bolt", [bob_bears.id])  # the chosen creature dies
    answer(s, "p3")  # As it transforms into Shinryu, choose an opponent
    assert s.state.cards[zenos.id].face == 1 and chosen.player_of(Plan(s.state, "p1", s.cards, None), zenos.id) == "p3"
    check(s)
    act(s, "p1", type="set_life", player="p2", value=3)
    cast(s, "Lightning Bolt", ["p2"])  # a player who is not the chosen one loses: no win
    answer(s)
    assert s.state.rules.winner is None
    act(s, "p1", type="set_life", player="p3", value=3)
    cast(s, "Lightning Bolt", ["p3"])
    with suppress(ActionError):  # the game ends while the helper still passes priority
        answer(s)
    assert s.state.rules.winner == "p1"
    check(s)


def test_other_creatures_dying_to_the_minus_two_do_not_transform_zenos(cards):
    s, bob_bears, bob_elves, carol_bears = _scene(cards)
    answer(s, bob_bears.id)
    zenos = card_named(s, ZENOS)
    assert s.state.cards[bob_elves.id].zone == "p2:graveyard" and s.state.cards[carol_bears.id].zone == "p3:graveyard"  # others left, the chosen one did not
    assert s.state.cards[zenos.id].face == 0 and s.state.cards[zenos.id].zone == "p1:battlefield"
    check(s)
