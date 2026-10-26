"""Wave 110M: Golgothian Sylex. CR 206.3b lists the names "originally printed in the Antiquities expansion"; 701.21a: sacrificed by its controller.
Every scenario checks the replay and a save and a load.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave36a_kit import ready
from tests.wave110m_kit import *

SYLEX = "Golgothian Sylex"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([SYLEX])


def test_sylex_sacrifices_every_antiquities_named_nontoken_permanent_of_every_player(cards):
    s = build(cards, [SYLEX, "Millstone", "Atog", "Grizzly Bears"], ["Mishra's Factory", "Elite Vanguard"], forests=20)
    sylex = put(s, SYLEX)
    put(s, "Atog")
    put(s, "Millstone")
    put(s, "Grizzly Bears")
    put(s, "Mishra's Factory", "p2")
    put(s, "Elite Vanguard", "p2")
    ready(s, SYLEX)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=sylex.id, ability=0)
    answer(s)
    assert [zone_of(s, n) for n in (SYLEX, "Millstone", "Atog")] == ["p1:graveyard"] * 3  # (the Sylex is named in the list too)
    assert zone_of(s, "Mishra's Factory", "p2") == "p2:graveyard"
    assert zone_of(s, "Grizzly Bears") == zone_of(s, "Elite Vanguard", "p2").replace("p2", "p1") == "p1:battlefield"
    check(s)


def test_sylex_leaves_a_token_that_shares_a_listed_name(cards):
    s = build(cards, [SYLEX], forests=20)
    sylex = put(s, SYLEX)
    act(s, "p1", type="create_token", player="p1", token={"name": "Atog", "power": "1", "toughness": "2", "type_line": "Token Creature — Atog"})
    ready(s, SYLEX)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=sylex.id, ability=0)
    answer(s)
    assert zone_of(s, SYLEX) == "p1:graveyard"
    assert any(c.name == "Atog" and c.is_token and c.zone == "p1:battlefield" for c in s.state.cards.values())
    check(s)
