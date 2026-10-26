"""Wave 110A session 14: real-Oracle scenario tests."""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *
from app.rules import keyword_actions, scripts  # isort: skip

NAMES = ["Jon Irenicus, Shattered One"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test(NAMES)


def _jon(cards, give=True):
    s = build(cards, ["Jon Irenicus, Shattered One", "Grizzly Bears"], ["Island"])
    put(s, "Jon Irenicus, Shattered One")
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    until(s, lambda s: s.state.rules.decision is not None or (s.state.turn.phase == "end" and s.state.zones.get("stack")))
    answer(s, "p2", bears.id if give else [])
    return s, bears


def test_jon_gives_a_creature_counters_tap_goad_and_no_sacrifice(cards):  # 701.15a goad with no end, 611.2a no duration = rest of the game, 122.1
    s, bears = _jon(cards)
    c = s.state.cards[bears.id]
    assert (c.controller, c.counters.get("+1/+1"), c.tapped) == ("p2", 2, True)
    assert keyword_actions.goaded_by(ch(s, bears)) == {"p1"}
    assert "cant_be_sacrificed" in scripts.statics(ch(s, bears))
    assert [e.duration for e in s.state.rules.effects if "goaded:p1" in e.imposes] == ["permanent"]  # never expires (not at Jon's controller's next turn)
    check(s)


def test_jon_with_no_creature_chosen_changes_nothing(cards):  # "up to one": zero targets is legal (115.1b)
    s, bears = _jon(cards, give=False)
    assert s.state.cards[bears.id].controller == "p1" and s.state.cards[bears.id].counters.get("+1/+1") is None
    check(s)
