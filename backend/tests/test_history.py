from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.history import SNAPSHOT_EVERY, History
from app.game.session import GameSession
from tests.game_helpers import act, find, make_session, zone


@pytest.fixture()
def s(cards):
    return make_session(cards, shuffle=True)


def snapshot(session: GameSession) -> str:
    data = session.state.model_dump(mode="json")
    return json.dumps(data, sort_keys=True)


def test_undo_redo_every_action_type_restores_exact_state(s, cards):
    """Record a long mixed game, then undo everything step by step and redo it all."""
    from tests.fixtures.cards import GOBLIN

    snapshots = [snapshot(s)]

    def step(actor, **payload):
        act(s, actor, **payload)
        snapshots.append(snapshot(s))

    step("p1", type="shuffle")
    step("p1", type="draw", count=7)
    step("p1", type="mulligan")
    step("p2", type="draw", count=7)
    hand = zone(s.state, "p1", "hand")
    step("p1", type="move", card_ids=hand[:2], to={"zone": "battlefield"}, x=100, y=100)
    step("p1", type="tap", card_ids=zone(s.state, "p1", "battlefield")[:1])
    step("p1", type="counter", card_ids=zone(s.state, "p1", "battlefield")[:1], kind="+1/+1", delta=2)
    step("p1", type="create_token", token={"card_id": GOBLIN["id"]}, count=2)
    step("p2", type="life", player="p1", delta=-5)
    krenko = find(s.state, "Krenko, Mob Boss")
    step("p1", type="move", card_ids=[krenko.id], to={"zone": "stack"})
    step("p1", type="resolve_top")
    step("p1", type="commander_damage", player="p2", commander=krenko.commander_key, delta=4)
    step("p1", type="roll", sides=20)
    step("p1", type="search_start", zone={"zone": "library"})
    step("p1", type="search_end", shuffle=True)
    step("p1", type="phase", to="next")
    step("p1", type="next_turn")

    for expected in reversed(snapshots[:-1]):
        s.undo("p1")
        assert snapshot(s) == expected
    with pytest.raises(ActionError):
        s.undo("p1")
    for expected in snapshots[1:]:
        s.redo("p1")
        assert snapshot(s) == expected
    with pytest.raises(ActionError):
        s.redo("p1")


def test_undo_shuffle_restores_previous_library_order(s):
    before = list(zone(s.state, "p1", "library"))
    act(s, "p1", type="shuffle")
    assert zone(s.state, "p1", "library") != before
    s.undo("p1")
    assert zone(s.state, "p1", "library") == before


def test_new_action_after_undo_discards_redo(s):
    act(s, "p1", type="draw")
    act(s, "p1", type="draw")
    s.undo("p1")
    assert s.history.can_redo
    act(s, "p1", type="life", delta=-1)
    assert not s.history.can_redo
    assert len(zone(s.state, "p1", "hand")) == 1


def test_undo_notices_logged_out_of_band(s):
    act(s, "p1", type="draw")
    s.undo("p1")
    view = s.view("p2")
    assert "undid: draw" in view["log"][-1]["parts"][-1]["t"]


def test_failed_action_leaves_state_intact(s):
    before = snapshot(s)
    with pytest.raises(ActionError):
        # the first card is valid; the second is not on the battlefield, so the whole action fails
        act(s, "p1", type="set_position", moves=[[zone(s.state, "p1", "command")[0], 1, 1]])
    assert snapshot(s) == before


def test_history_serialization_round_trip(s):
    for _ in range(SNAPSHOT_EVERY + 5):
        act(s, "p1", type="life", delta=-1)
        act(s, "p2", type="roll", sides=6)
    s.undo("p1")
    data = json.loads(json.dumps(s.history.to_dict()))
    restored = History.from_dict(data)
    assert restored.cursor == s.history.cursor
    assert restored.state_at(restored.cursor).model_dump(mode="json") == s.state.model_dump(mode="json")
    assert restored.can_redo


def test_history_limit_rebases(cards):
    s = make_session(cards)
    s.history = History(s.state, limit=SNAPSHOT_EVERY * 2)
    for _ in range(SNAPSHOT_EVERY * 5):
        act(s, "p1", type="life", delta=-1)
    assert len(s.history.actions) <= SNAPSHOT_EVERY * 2
    life = s.state.players["p1"].life
    s.undo("p1")
    assert s.state.players["p1"].life == life + 1
