"""-- undo back to here -- GameSession.undo_to takes back every action after a history position at once (a whole combat, a whole
turn) with one replay, under the same rules as undoing them one at a time (app/game/undo_rights.py, app/game/undo_requests.py)."""

from __future__ import annotations

import json

import pytest

from app.game import history as history_mod
from app.game.errors import ActionError
from tests.game_helpers import act, make_session
from tests.test_undo_policy import REMOTE, lan, post  # noqa: F401 - the ``lan`` fixture

__all__ = ["lan"]


def dump(s) -> str:
    return json.dumps(s.state.model_dump(mode="json"), sort_keys=True)


def test_undo_to_matches_undoing_one_at_a_time_and_redo_puts_them_back(cards):
    s = make_session(cards)
    states = [dump(s)]
    for delta in (-1, -2, -3, -4, -5):
        act(s, "p1", type="life", delta=delta)
        states.append(dump(s))
    s.undo_to("p2", 2)
    assert dump(s) == states[2] and s.history.cursor == 2 and s.history.can_redo
    for expected in states[3:]:
        s.redo("p1")
        assert dump(s) == expected


def test_undo_to_replays_once(cards, monkeypatch):
    s = make_session(cards)
    for _ in range(6):
        act(s, "p1", type="life", delta=-1)
    calls = []
    real = history_mod.History.state_at
    monkeypatch.setattr(history_mod.History, "state_at", lambda self, p: calls.append(p) or real(self, p))
    s.undo_to("p1", 1)
    assert calls == [1]


def test_undo_to_tells_the_journal_one_undo_per_action(cards):
    s = make_session(cards)
    for _ in range(4):
        act(s, "p1", type="life", delta=-1)
    heard = []
    s.history.listener = lambda kind, action: heard.append(kind)
    s.undo_to("p1", 1)
    assert heard == ["undo"] * 3


def test_undo_to_keeps_the_undo_setting_for_every_action(cards):
    s = make_session(cards)
    act(s, "p1", type="configure", undo_policy="own")
    act(s, "p1", type="life", delta=-3)
    act(s, "p2", type="life", delta=-2)
    act(s, "p1", type="life", delta=-1)
    with pytest.raises(ActionError, match="own actions.*#3"):
        s.undo_to("p1", 1)
    assert s.history.cursor == 4  # nothing was undone
    s.undo_to("p1", 3)
    assert s.history.cursor == 3


def test_undo_to_asks_one_at_a_time_for_what_players_already_saw(cards):
    s = make_session(cards)
    act(s, "p1", type="life", delta=-1)
    act(s, "p1", type="draw", count=1)
    act(s, "p1", type="life", delta=-1)
    with pytest.raises(ActionError, match="a draw.*one action at a time"):
        s.undo_to("p1", 0, others=["p2"])
    s.undo_to("p1", 0)  # a hot-seat table (nobody else to ask): as one undo at a time would
    assert s.history.cursor == 0


def test_undo_to_refuses_a_position_with_nothing_after_it(cards):
    s = make_session(cards)
    act(s, "p1", type="life", delta=-1)
    for position in (1, 2, -1):
        with pytest.raises(ActionError):
            s.undo_to("p1", position)


def test_api_undo_back_to_here(client, lan):  # noqa: F811
    history = f"/api/games/{lan['gid']}/history"
    for _ in range(3):
        assert post(client, lan, "actions", lan["host"], {"action": {"type": "life", "delta": -1}}).status_code == 200
    first = client.get(history, headers={"X-Seat-Token": lan["host"]}).json()["cursor"] - 2
    res = post(client, lan, f"history/{first}/undo", lan["bob"], **REMOTE)
    assert res.status_code == 200, res.text
    assert res.json()["game"]["can_redo"]
    items = client.get(history, headers={"X-Seat-Token": lan["host"]}).json()["items"]
    assert [it["undone"] for it in items][-3:] == [False, True, True]
    assert all("turn" in it and "phase" in it for it in items)
    assert post(client, lan, f"history/{first}/undo", lan["bob"], **REMOTE).status_code == 409  # nothing after it any more
