"""S7 -- the first turn: 502.4, no player gets priority in the untap step. A new game with the rules on starts in turn 1's untap step and
the engine goes straight on to the first step that gives priority (upkeep, then the draw step the starting player of a two-player game
skips, 103.8a), exactly as every later turn does -- with or without mulligans first, and after a Start over. The run is part of the
starting table: nothing in the history to undo, and a replay from the history rebuilds the same table."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.mulligan import COMMANDER_LONDON
from app.game.rules_state import AUTOMATION_PRESETS, start_rules
from app.game.session import GameSession
from app.game.state import GameSettings
from tests.game_helpers import act, deck, engine_pays


def table(cards, policy=None, *, begin=True):
    """Like the API's game creation (app/api/games.py): rules started before play, then the first turn begun."""
    a = deck(cards, "Krenko, Mob Boss", [(20, "Mountain")])
    b = deck(cards, "Atraxa, Praetors' Voice", [(20, "Island")])
    state = new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], settings=GameSettings(mulligan=policy), shuffle=False)
    state.settings.automation = "full"
    state.settings.automation_options = AUTOMATION_PRESETS["full"].model_copy()
    start_rules(state)
    engine_pays(state)
    s = GameSession(state, cards=cards)
    if begin:
        s.begin_first_turn()
    return s


def replay_matches(s):
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def at(s):
    return s.state.turn.number, s.state.turn.phase, s.state.rules.priority


def test_a_new_game_without_mulligans_never_gives_priority_in_the_untap_step(cards):
    s = table(cards)
    assert at(s) == (1, "main1", "p1") and s.state.rules.step == "1:main1"
    assert s.state.zones["p1:hand"] == []  # 103.8a: the starting player of a two-player game skips the first draw (no hands dealt here)
    assert "skips the first draw" in str(s.state.log)
    assert s.history.actions == []  # part of the starting table: nothing to take back into the untap step
    replay_matches(s)
    act(s, "p1", type="pass_priority")  # the game goes on from there
    act(s, "p1", type="pass_priority")
    assert at(s)[:2] == (2, "main1") and s.state.turn.active_player == "p2" and len(s.state.zones["p2:hand"]) == 1
    replay_matches(s)


def test_without_begin_the_table_was_waiting_in_the_untap_step(cards):
    s = table(cards, begin=False)  # (what every new game did before S7)
    assert at(s) == (1, "untap", "p1")
    s.begin_first_turn()
    assert at(s) == (1, "main1", "p1")
    s.begin_first_turn()  # (once only: nothing more to do)
    assert at(s) == (1, "main1", "p1") and s.history.actions == []


def test_mulligans_and_opening_hands_still_come_first(cards):
    s = table(cards, COMMANDER_LONDON)
    assert s.state.pregame is not None and not s.state.pregame.finished
    assert s.state.turn.phase == "untap"  # nothing begins before the opening hands are kept (103.5)
    act(s, "p1", type="mulligan_keep")
    act(s, "p2", type="mulligan_keep")
    while s.state.rules.decision is not None:  # the opening-hand actions (103.6), before the first turn
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    assert at(s) == (1, "main1", "p1")
    replay_matches(s)


def test_start_over_begins_the_new_game_past_its_untap_step(cards):
    s = table(cards)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="pass_priority")
    assert s.state.turn.number == 2
    act(s, "p1", type="restart_game", draw=7, fresh=True)
    assert at(s) == (1, "main1", "p1") and s.state.turn.active_player == "p1"
    replay_matches(s)
    s.undo("p1")  # undo takes back the whole Start over, the run through the untap step with it
    assert s.state.turn.number == 2
    s.redo("p1")
    assert at(s) == (1, "main1", "p1")
    replay_matches(s)


def test_rules_off_tables_are_untouched(cards):
    a = deck(cards, "Krenko, Mob Boss", [(20, "Mountain")])
    state = new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=a)], shuffle=False)
    s = GameSession(state, cards=cards)
    s.begin_first_turn()
    assert (s.state.turn.number, s.state.turn.phase) == (1, "untap") and s.state.rules is None


def test_a_restart_and_a_table_for_one_begin_past_the_untap_step_too(cards):
    s = table(cards)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="restart_game", draw=7)  # (the plain Restart, not Start over)
    assert at(s)[:2] == (1, "main1")
    replay_matches(s)
    a = deck(cards, "Krenko, Mob Boss", [(20, "Mountain")])
    state = new_game([PlayerSetup("Alice", cards=a)], shuffle=False)  # a LAN night with only the host: its turns go on
    state.settings.automation = "full"
    state.settings.automation_options = AUTOMATION_PRESETS["full"].model_copy()
    start_rules(state)
    solo = GameSession(state, cards=cards)
    solo.begin_first_turn()
    assert at(solo) == (1, "main1", "p1")
