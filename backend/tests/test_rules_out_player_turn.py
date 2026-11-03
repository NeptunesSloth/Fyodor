"""A player who is out of the game can't move the turn on with the table tools.

800.4a: a player who conceded (104.3a) or lost (104.3) has left the game. With rules automation on,
their rules intents are already refused (``compile_intent``); the table's manual step controls
(``phase`` / ``next_turn``) are refused for them too, so the dial is not the only guard. The players
still in the game keep their manual overrides.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.state import GameState
from tests.game_helpers import act
from tests.test_rules_effects import replay_matches, rules
from tests.test_rules_review5 import build3

TURN_ACTIONS = [{"type": "phase", "to": "next"}, {"type": "phase", "to": "prev"}, {"type": "phase", "to": "end"},
                {"type": "next_turn"}]


def knock_out(s, how):
    """Bob (p2, not the active player) leaves the game: he concedes, or loses at 0 life (704.5a)."""
    if how == "conceded":
        act(s, "p2", type="concede")
        assert "p2" in rules(s).conceded
    else:
        act(s, "p1", type="set_life", player="p2", value=0)
        act(s, "p1", type="pass_priority")  # 704.3: the next check makes him lose
        assert "p2" in rules(s).lost
    assert rules(s).winner is None  # Alice and Carol are still playing


@pytest.mark.parametrize("how", ["conceded", "lost"])
@pytest.mark.parametrize("payload", TURN_ACTIONS, ids=lambda p: f"{p['type']}-{p.get('to', '')}")
def test_a_player_who_is_out_cannot_change_the_turn_or_step(cards, how, payload):
    s = build3(cards)
    knock_out(s, how)
    turn = s.state.turn.model_dump(mode="json")
    seq = s.state.seq
    with pytest.raises(ActionError, match="left this game"):
        act(s, "p2", **payload)
    assert s.state.turn.model_dump(mode="json") == turn and s.state.seq == seq
    replay_matches(s)


@pytest.mark.parametrize("how", ["conceded", "lost"])
def test_the_players_still_in_the_game_keep_their_manual_step_controls(cards, how):
    s = build3(cards)
    knock_out(s, how)
    before = s.state.turn.phase
    act(s, "p3", type="phase", to="next")  # a manual override by a player still in the game
    assert s.state.turn.phase != before
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def test_the_active_player_concedes_the_engine_moves_the_turn_on_and_they_cannot(cards):
    """800.4a: the engine's own steps end the turn of the active player who left; their table controls are refused."""
    s = build3(cards)
    assert s.state.turn.active_player == "p1"
    act(s, "p1", type="concede")
    assert "p1" in rules(s).conceded and s.state.turn.active_player != "p1"
    turn = s.state.turn.model_dump(mode="json")
    for payload in TURN_ACTIONS:
        with pytest.raises(ActionError, match="left this game"):
            act(s, "p1", **payload)
    assert s.state.turn.model_dump(mode="json") == turn
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped
