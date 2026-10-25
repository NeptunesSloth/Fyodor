"""Wave 110O: single-card wordings, real Oracle text (tests/fixtures/wave110o_cards.json). Every scenario checks the replay and a save and a load.

* 701.24a, 608.2b: Serene Remembrance shuffles itself and up to three target cards from a single graveyard into their owners' libraries.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110o_kit import (  # noqa: F401
    EXTRA,
    ability,
    activate,
    card_db,
    cast_on,
    ch,
    check,
    cost,
    full,
    grave_new,
    hand_new,
    mana,
    move,
    now,
    put,
    put_new,
    refused,
    settle,
    to_hand,
    to_phase,
)

REMEMBRANCE = "Serene Remembrance"


@pytest.mark.parametrize("name", [REMEMBRANCE])
def test_the_cards_are_full(name):
    assert full(name)


def remembrance(s, targets):
    c = to_hand(s, REMEMBRANCE)
    mana(s, "p1", G=1)
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[t.id for t in targets], target_counts=[len(targets)])
    settle(s)
    return now(s, c)


@pytest.mark.parametrize("n", [0, 1, 3])
def test_serene_remembrance_shuffles_itself_and_up_to_three_targets_into_their_owner_library(cards, n):
    s = build(cards, [REMEMBRANCE])
    mine = [grave_new(s, "Forest") for _ in range(n)]
    lib = len(s.state.zones["p1:library"])
    spell = remembrance(s, mine)
    assert spell.zone == "p1:library" and len(s.state.zones["p1:library"]) == lib + n
    assert all(now(s, c).zone == "p1:library" for c in mine) and len(s.state.zones["p1:graveyard"]) == 0
    check(s)


def test_serene_remembrance_sends_a_graveyard_card_to_its_owner_not_the_caster(cards):
    s = build(cards, [REMEMBRANCE])
    theirs = grave_new(s, "Island", "p2")
    lib = len(s.state.zones["p2:library"])
    spell = remembrance(s, [theirs])
    assert spell.zone == "p1:library" and now(s, theirs).zone == "p2:library" and len(s.state.zones["p2:library"]) == lib + 1
    check(s)


def test_serene_remembrance_cant_target_cards_of_two_graveyards(cards):
    s = build(cards, [REMEMBRANCE])
    a, b = grave_new(s, "Forest"), grave_new(s, "Island", "p2")
    c = to_hand(s, REMEMBRANCE)
    mana(s, "p1", G=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, targets=[a.id, b.id], target_counts=[2])
    check(s)
