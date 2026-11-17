"""-- target dummy -- a test table with two or more dummies ends once its only human player is out (app/rules/dummy_ending.py): the
dummies win, nothing more happens (no endless empty turns of dummies drawing from empty libraries), Take it back still finds the
losing action, and it all replays the same through a reload."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.history import History
from app.game.session import GameSession
from app.game.state import GameState
from app.multiplayer.night import rules_ending
from app.rules.dummy_ending import DUMMIES_WIN
from tests.game_helpers import act, turn_on
from tests.test_target_dummy import lose_as_alice, pass_until, replay_matches, sandbox


def two_dummies(cards) -> GameSession:
    s = sandbox(cards)
    act(s, "p1", type="add_dummy")
    act(s, "p1", type="add_dummy", life=10)
    turn_on(s, "full")
    pass_until(s, 1, "main1")
    return s


def reloaded(s: GameSession, cards) -> GameSession:
    loaded = GameState.model_validate(s.state.model_dump(mode="json"))
    again = GameSession(loaded, cards=cards, history=History.from_dict(s.history.to_dict()))
    assert again.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")
    return again


def test_the_game_ends_when_alice_loses_to_two_dummies(cards):
    from app.game.handlers.dummy import before_the_end

    s = two_dummies(cards)
    turn = s.state.turn.number
    before = lose_as_alice(s)
    r = s.state.rules
    assert r.draw_reason == DUMMIES_WIN and r.winner is None and r.decision is None
    assert s.state.turn.number == turn  # (the dummies take no turns of their own)
    assert rules_ending(s.state) == ("win:p2,p3", "multiple", ["p2", "p3"])
    with pytest.raises(ActionError, match="The game is over"):  # (the dummies answer nothing more: app/game/dummy.py)
        act(s, "p1", type="cast_spell", card_id=next(c for c in s.state.zones["p1:hand"]))
    replay_matches(s)
    again = reloaded(s, cards)
    assert again.state.rules.draw_reason == DUMMIES_WIN
    # Take it back: just before the pass that lost it, and the test goes on
    assert before_the_end(s.state, s.history, "p1") == before
    s.undo_to("p1", before, host=True)
    r = s.state.rules
    assert r.draw_reason is None and r.lost == {}
    replay_matches(s)


def test_the_game_ends_when_alice_concedes_to_three_dummies(cards):
    s = sandbox(cards)
    for _ in range(3):
        act(s, "p1", type="add_dummy")
    turn_on(s, "full")
    pass_until(s, 1, "main1")
    turn = s.state.turn.number
    act(s, "p1", type="concede")
    r = s.state.rules
    assert r.conceded == ["p1"] and r.draw_reason == DUMMIES_WIN and s.state.turn.number == turn
    assert rules_ending(s.state)[1:] == ("multiple", ["p2", "p3", "p4"])
    replay_matches(s)
    reloaded(s, cards)


def test_one_dummy_left_is_the_ordinary_win_and_a_dummy_free_table_is_untouched(cards):
    s = sandbox(cards)
    act(s, "p1", type="add_dummy")
    turn_on(s, "full")
    pass_until(s, 1, "main1")
    lose_as_alice(s)
    assert s.state.rules.winner == "p2" and s.state.rules.draw_reason is None
    assert rules_ending(s.state) == ("win:p2", "single", ["p2"])
    # a goldfish table (no dummy at all) goes on as before
    solo = sandbox(cards, rules=True)
    pass_until(solo, 2, "main1")
    assert solo.state.rules.draw_reason is None and solo.state.rules.winner is None


def test_alice_killing_one_of_two_dummies_goes_on(cards):
    s = two_dummies(cards)
    act(s, "p1", type="set_life", player="p3", value=0)
    act(s, "p1", type="pass_priority")
    r = s.state.rules
    assert "p3" in r.lost and r.draw_reason is None and r.winner is None
    pass_until(s, 2, "main1")  # (Alice and the one dummy left go on)


def test_reset_dummy_after_the_dummies_won_keeps_the_test_over(cards):
    """Bringing a lost dummy back while Alice is out must not restart the dummies' endless turns."""
    s = two_dummies(cards)
    act(s, "p1", type="add_dummy")
    act(s, "p1", type="set_life", player="p4", value=0)
    act(s, "p1", type="pass_priority")
    assert "p4" in s.state.rules.lost
    pass_until(s, 2, "main1")
    lose_as_alice(s)
    assert s.state.rules.draw_reason == DUMMIES_WIN
    # (Alice, out of the game, can't press Reset dummy herself: the server's own reset must not reopen it either)
    s.perform("p1", {"type": "reset_dummy", "player": "p4"}, trusted=True)
    r = s.state.rules
    assert "p4" not in r.lost and r.draw_reason == DUMMIES_WIN
    assert rules_ending(s.state)[2] == ["p2", "p3", "p4"]
    replay_matches(s)
