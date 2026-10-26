"""Wave 110N: The Beamtown Bullies (115.1 the opponent whose turn it is, 701.15 goaded by the Bullies' controller, 603.7 exiled at the next end step)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

BULLIES = "The Beamtown Bullies"
EXTRA = [real("Legend Squire", "{1}{B}", 2, "Legendary Creature — Human", "", ("2", "2"), "B")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([BULLIES])


def setup(cards):
    s = build(cards, [BULLIES, "Grizzly Bears", "Legend Squire"])
    put(s, BULLIES)
    for n in ("Grizzly Bears", "Legend Squire"):
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    return s


def to_opponents_turn(s):
    act(s, "p1", type="set_stops", own=STEPS + ["upkeep"], others=STEPS + ["upkeep"], smart_pass=False)
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "upkeep" and s.state.rules.priority == "p1")


def test_on_the_opponents_turn_they_put_the_creature_onto_the_battlefield_under_their_control(cards):
    from app.rules.keyword_actions import goaded_by

    s = setup(cards)
    bears = card_named(s, "Grizzly Bears")
    to_opponents_turn(s)
    act(s, "p1", type="activate_ability", card_id=card_named(s, BULLIES).id, ability=1, targets=["p2", bears.id], target_counts=[1, 1])
    answer(s)
    now = s.state.cards[bears.id]
    assert now.zone == "p2:battlefield" and now.controller == "p2"
    c = ch(s, now)
    assert "haste" in c.keywords and goaded_by(c) == {"p1"}
    stops(s)
    for _ in range(80):  # Bob's turn: the goaded Bears must attack (701.15b), then the end step exiles it
        d = s.state.rules.decision
        if s.state.turn.phase == "end" and s.state.turn.number == 2:
            break
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
        elif d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    assert zone_of(s, "Grizzly Bears") == "p1:exile"
    check(s)


def test_it_cannot_be_activated_on_your_own_turn(cards):
    s = setup(cards)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=card_named(s, BULLIES).id, ability=1, targets=["p2", card_named(s, "Grizzly Bears").id], target_counts=[1, 1])
    check(s)


def test_a_legendary_creature_card_cannot_be_chosen(cards):
    s = setup(cards)
    to_opponents_turn(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=card_named(s, BULLIES).id, ability=1, targets=["p2", card_named(s, "Legend Squire").id], target_counts=[1, 1])
    check(s)
