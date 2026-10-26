# ruff: noqa: F811  (the imported `cards` fixture is used as the test argument)
"""Wave 110F: Mystic Barrier -- 508.1d "each player may attack only the nearest opponent in the last chosen direction" (reuses combat_teyo66)."""
from __future__ import annotations

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_combat_teyo66 import NAMES, cards, cast, choose, declare, refuse, roundtrip, setup  # noqa: F401
from tests.test_rules_wave30m_durations import to_phase

BARRIER = NAMES[1]


def test_barrier_full(cards):
    assert coverage.of_card_data(cards.resolve(BARRIER)).level == "FULL"


def test_barrier_choice_on_entering_then_again_each_upkeep_replaces_it(cards):
    """When it enters: left (p1 may attack only p2, p2 only p3). At p1's next upkeep the new choice (right) replaces the old one."""
    s, bears = setup(cards)
    cast(s, BARRIER)
    choose(s, "left")
    t = s.state.turn.number  # (p1's turn)
    refuse(s, bears["p2"], "p1", pid="p2", turn=t + 1)
    declare(s, bears["p2"], "p3", pid="p2", turn=t + 1)
    to_phase(s, "upkeep", turn=t + 3)
    while s.state.rules.decision is None:  # (the upkeep trigger is on the stack)
        act(s, s.state.rules.priority, type="pass_priority")
    choose(s, "right")
    refuse(s, bears["p1"], "p2", turn=t + 3)
    declare(s, bears["p1"], "p3", turn=t + 3)
    roundtrip(s)
