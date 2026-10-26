"""Wave 110N: Missy (708.2a a face-down 2/2 Cyberman artifact creature, 701.55a villainous choice; "chaos ensues" does nothing without planes, 311.7)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

MISSY, GOLEM = "Missy", "Relic Golem"
EXTRA = [real(GOLEM, "{4}", 4, "Artifact Creature — Golem", "", ("3", "3"))]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([MISSY])


def murder(s, card, pid="p1"):
    mana(s, pid, B=3)
    cast(s, "Murder", [card.id], pay=False)
    answer(s)


@pytest.mark.parametrize(("victim", "owner", "returns"), [("Grizzly Bears", "p2", True), ("Llanowar Elves", "p1", True), (GOLEM, "p2", False)])
def test_a_nonartifact_creature_that_dies_returns_face_down_tapped_under_your_control(cards, victim, owner, returns):
    s = build(cards, [MISSY, "Murder", "Llanowar Elves"], ["Grizzly Bears", GOLEM])
    put(s, MISSY)
    target = put(s, victim, owner)
    murder(s, target)
    back = s.state.cards[target.id]
    if returns:
        assert back.zone == "p1:battlefield" and back.face_down and back.tapped and back.controller == "p1"
        c = ch(s, back)
        assert (c.pt, c.subtypes, {"Artifact", "Creature"} <= set(c.types)) == ((2, 2), {"Cyberman"}, True) and c.name == ""
    else:
        assert back.zone == f"{owner}:graveyard"
    check(s)


def test_missy_herself_dying_does_not_return_anything(cards):
    s = build(cards, [MISSY, "Murder"])
    missy = put(s, MISSY)
    murder(s, missy)
    assert zone_of(s, MISSY) == "p1:graveyard"
    check(s)


def choice(s, option):
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if option in o.label)])
            return
        act(s, s.state.rules.priority, type="pass_priority")


@pytest.mark.parametrize("take_damage", [True, False])
def test_each_opponent_takes_damage_from_each_artifact_creature_or_you_draw(cards, take_damage):
    s = build(cards, [MISSY, GOLEM, "Llanowar Elves"], [])
    put(s, MISSY)
    put(s, GOLEM)
    put(s, "Llanowar Elves")
    hand = len(s.state.zones["p1:hand"])
    stops(s)
    to_phase(s, "end")
    choice(s, "damage" if take_damage else "draw")
    answer(s)
    assert (life(s, "p2"), len(s.state.zones["p1:hand"])) == ((39, hand) if take_damage else (40, hand + 1))
    check(s)


def test_the_face_down_cyberman_is_an_artifact_creature_that_deals_the_damage_too(cards):
    s = build(cards, [MISSY, GOLEM, "Murder"], ["Grizzly Bears"])
    put(s, MISSY)
    put(s, GOLEM)
    murder(s, put(s, "Grizzly Bears", "p2"))
    stops(s)
    to_phase(s, "end")
    choice(s, "damage")
    answer(s)
    assert life(s, "p2") == 38  # the Golem and the Cyberman, 1 each
    check(s)
