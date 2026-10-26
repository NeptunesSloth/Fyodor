"""Wave 110N: Vislor Turlough (701.15 goad by the old controller, 611.2b only for as long as the opponent controls it)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

VISLOR = "Vislor Turlough"
EXTRA = [real("Take Back", "{1}", 1, "Sorcery", "Gain control of target creature.", None, "U")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([VISLOR])


def goaders(s, c):
    from app.rules.keyword_actions import goaded_by

    return goaded_by(ch(s, c))


def enter(cards, give):
    s = build(cards, [VISLOR, "Take Back"])
    vislor = cast(s, VISLOR)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes" if give else "no"])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return s, vislor


def test_an_opponent_gains_control_of_it_and_it_is_goaded_by_the_old_controller(cards):
    s, vislor = enter(cards, True)
    assert s.state.cards[vislor.id].controller == "p2" and goaders(s, vislor) == {"p1"}
    check(s)


def test_declined_you_keep_it_and_it_is_not_goaded(cards):
    s, vislor = enter(cards, False)
    assert s.state.cards[vislor.id].controller == "p1" and goaders(s, vislor) == set()
    check(s)


def test_the_goaded_creature_must_attack_on_the_opponents_turn(cards):
    s, vislor = enter(cards, True)
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id]) if d is not None else act(s, s.state.rules.priority, type="pass_priority")
    assert d.player == "p2"
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": vislor.id, "target": "p1"}])
    check(s)


def test_the_goad_ends_when_the_old_controller_takes_it_back(cards):
    s, vislor = enter(cards, True)
    cast(s, "Take Back", [vislor.id])
    answer(s)
    assert s.state.cards[vislor.id].controller == "p1" and goaders(s, vislor) == set()
    check(s)
