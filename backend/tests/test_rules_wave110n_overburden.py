"""Wave 110N: Overburden (603.6a every nontoken creature entering, any player's: they return a land they control to its owner's hand)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

BURDEN = "Overburden"
EXTRA = [real("Flash Squire", "{U}", 1, "Creature — Human", "Flash", ("1", "1"), "U"), real("Make Token", "{W}", 1, "Instant", "Create a 1/1 white Soldier creature token.", None, "W")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([BURDEN])


def lands(s, pid):
    return sorted(c.name for c in s.state.cards.values() if c.zone == f"{pid}:battlefield" and ch(s, c).is_land)


def step(s, pid):
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            assert d.player == pid
            act(s, pid, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
            return
        act(s, s.state.rules.priority, type="pass_priority")


def test_the_player_who_cast_the_creature_returns_a_land(cards):
    s = build(cards, [BURDEN, "Grizzly Bears"], forests=9)
    put(s, BURDEN)
    for c in [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:3]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    cast(s, "Grizzly Bears")
    step(s, "p1")
    answer(s)
    assert len(lands(s, "p1")) == 2 and zone_of(s, "Grizzly Bears") == "p1:battlefield"
    check(s)


def test_an_opponents_creature_makes_that_opponent_return_their_land(cards):
    s = build(cards, [BURDEN, "Make Token"], ["Flash Squire"], islands=9)
    put(s, BURDEN)
    isle = [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][0]
    act(s, "p2", type="move", card_ids=[isle.id], to={"player": "p2", "zone": "battlefield"})
    act(s, "p2", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)  # (Bob wants priority with Alice's spell on the stack)
    cast(s, "Make Token")
    if s.state.rules.priority == "p1":
        act(s, "p1", type="pass_priority")
    mana(s, "p2", U=1)
    cast(s, "Flash Squire", pid="p2", pay=False)
    answer(s)  # (Bob's one land is the only choice: nothing to ask)
    assert lands(s, "p2") == [] and zone_of(s, "Island", "p2") == "p2:hand" and zone_of(s, "Flash Squire", "p2") == "p2:battlefield"
    check(s)


def test_a_token_does_not_count(cards):
    s = build(cards, [BURDEN, "Make Token"], forests=9)
    put(s, BURDEN)
    f = [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][0]
    act(s, "p1", type="move", card_ids=[f.id], to={"player": "p1", "zone": "battlefield"})
    cast(s, "Make Token")
    answer(s)
    assert lands(s, "p1") == ["Forest"]
    check(s)
