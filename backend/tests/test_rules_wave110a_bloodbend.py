"""Wave 110A: Secret of Bloodbending (723.1 control of a player for their next combat phase, or turn when waterbend {10} (701.67) was paid; 2025-10-02 rulings)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.control import controller_of
from app.rules import coverage
from tests.test_rules_wave18h_player_control import drive
from tests.wave53d_kit import table
from tests.wave110a_kit import *

SECRET = "Secret of Bloodbending"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def _cast(cards, paid, target="p2"):
    s = table(cards, mine=[SECRET, "Island"], bobs=["Grizzly Bears"])
    c = to_hand(s, SECRET)
    fund(s, (s.cards.resolve(SECRET).get("mana_cost") or "") + ("{10}" if paid else ""))
    act(s, "p1", type="cast_spell", card_id=c.id, targets=[target], optional_costs=[c.id + ":waterbend103"] if paid else [], sources=[])
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)  # a stop in every step, so the combat steps can be looked at
    drive(s, lambda s: not s.state.zones.get("stack"))
    return s, c


def _at(s, turn, phase):
    drive(s, lambda s: s.state.turn.number == turn and s.state.turn.phase == phase and s.state.rules.priority is not None)
    return controller_of(s.state, "p2")


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(SECRET)).level == "FULL"


def test_unpaid_controls_only_their_next_combat_phase_then_exiles(cards):
    s, c = _cast(cards, False)
    assert [(x.controlled, x.controller, x.combat) for x in s.state.rules.player_control] == [("p2", "p1", True)]
    assert s.state.cards[c.id].zone == "p1:exile"  # "Exile Secret of Bloodbending."
    assert _at(s, 2, "main1") == "p2"  # 723.1: not before the combat phase
    assert _at(s, 2, "begin_combat") == "p1" and s.state.turn.active_player == "p2"  # 723.3: still the active player
    assert _at(s, 2, "end_combat") == "p1"
    assert _at(s, 2, "main2") == "p2"  # the phase is over
    assert s.state.rules.player_control[0].status == "done"
    drive(s, lambda s: s.state.turn.number == 3)
    assert s.state.rules.player_control == []
    check(s)


def test_paid_controls_their_whole_next_turn_instead(cards):
    s, _ = _cast(cards, True)
    assert [(x.combat) for x in s.state.rules.player_control] == [False]
    assert _at(s, 2, "main1") == "p1" and _at(s, 2, "main2") == "p1"
    check(s)


def test_control_waits_through_other_players_combat_phases(cards):
    s, _ = _cast(cards, False, "p3")
    _at(s, 2, "main2")  # Bob's combat phase came and went
    assert [(x.controlled, x.status) for x in s.state.rules.player_control] == [("p3", "pending")] and controller_of(s.state, "p2") == "p2"
    drive(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "begin_combat")
    assert controller_of(s.state, "p3") == "p1"  # Carol's own combat phase
    check(s)
