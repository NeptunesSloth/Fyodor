"""Wave 110O: single-card wordings, real Oracle text (tests/fixtures/wave110o_cards.json). Every scenario checks the replay and a save and a load.

* 608.2c, 611.2a, 109.4: Evil's Thrall takes the creature until end of turn, or until the end of your next turn while you control a Villain of greater mana value.
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

REMEMBRANCE, THRALL = "Serene Remembrance", "Evil's Thrall"


@pytest.mark.parametrize("name", [REMEMBRANCE, THRALL])
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


def thrall(s, villain):
    bears = put(s, "Grizzly Bears", "p2")
    if villain:
        put_new(s, villain)
    bears_now = now(s, bears)
    assert bears_now.controller == "p2"
    cast_on(s, THRALL, bears)
    return bears


@pytest.mark.parametrize(("villain", "next_turn_too"), [(None, False), ("Common Crook", False), ("Roxxon Brutes", True)])
def test_evil_thrall_lasts_until_the_end_of_your_next_turn_only_with_a_bigger_villain(cards, villain, next_turn_too):
    """A Villain of equal mana value (Common Crook 2, Grizzly Bears 2) is not "greater"."""
    s = build(cards, [THRALL, "Common Crook", "Roxxon Brutes"], ["Grizzly Bears"])
    bears = thrall(s, villain)
    c = now(s, bears)
    assert c.controller == "p1" and not c.tapped and "haste" in ch(s, bears).keywords
    to_phase(s, "main1", turn=2)
    assert now(s, bears).controller == ("p1" if next_turn_too else "p2")
    to_phase(s, "main2", turn=3)
    assert now(s, bears).controller == ("p1" if next_turn_too else "p2")
    to_phase(s, "main1", turn=4)
    assert now(s, bears).controller == "p2"
    check(s)



def test_evil_thrall_ignores_a_bigger_villain_an_opponent_controls(cards):
    s = build(cards, [THRALL], ["Grizzly Bears", "Roxxon Brutes"])
    put(s, "Roxxon Brutes", "p2")
    bears = thrall(s, None)
    to_phase(s, "main1", turn=2)
    assert now(s, bears).controller == "p2"
    check(s)
