"""Old saves keep loading after format changes."""

from __future__ import annotations

import copy

from app.game.history import History
from app.storage.save_format import SAVE_VERSION, decode, encode
from app.storage.saves import load_payload
from tests.game_helpers import act, find, make_session, zone


def as_v1(state_dict: dict) -> dict:
    """Turn a current state dump into the v1 shape (known_to/revealed/searches)."""
    old = copy.deepcopy(state_dict)
    for card in old["cards"].values():
        card["revealed"] = bool(card.pop("revealed_to"))
        card["known_to"] = ["*"] if card["revealed"] else ["p2"]  # v1 "memory" that must not survive
    views = old.pop("views")
    old["searches"] = {v["viewer"]: v["zone"] for v in views if v["kind"] == "search"}
    old.pop("hidden_salt")
    for key in ("reminders",):
        old.pop(key, None)
    for p in old["players"].values():
        p.pop("mana", None)
    return old


def test_v1_save_migrates_and_keeps_history(cards):
    s = make_session(cards, shuffle=True)
    act(s, "p1", type="draw", count=7)
    act(s, "p1", type="search_start", zone={"zone": "library"})
    act(s, "p1", type="life", delta=-3)
    history = s.history.to_dict()
    payload = {
        "format": "fyodor-save",
        "version": 1,
        "saved_at": 0,
        "state": as_v1(s.state.model_dump(mode="json")),
        "history": {**history, "base": as_v1(history["base"])},
    }
    migrated = decode(encode(payload))
    assert migrated["version"] == SAVE_VERSION == 2
    state, restored_history = load_payload(migrated)
    assert state.players["p1"].life == 37
    assert state.searching("p1") == "p1:library"
    assert state.hidden_salt and state.hidden_salt == migrated["history"]["base"]["hidden_salt"]
    assert all(c.revealed_to == [] for c in state.cards.values())
    assert restored_history is not None  # replay of the migrated history matches the migrated state
    assert isinstance(restored_history, History) and restored_history.cursor == 3


def test_v1_known_cards_are_not_remembered(cards):
    s = make_session(cards)
    act(s, "p1", type="draw", count=15)
    sol = find(s.state, "Sol Ring")
    act(s, "p1", type="move", card_ids=[sol.id], to={"zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[sol.id], to={"zone": "hand"})
    payload = {"format": "fyodor-save", "version": 1, "saved_at": 0,
               "state": as_v1(s.state.model_dump(mode="json")), "history": None}
    state, _ = load_payload(decode(encode(payload)))
    from app.game.views import build_view

    theirs = build_view(state, "p2")
    assert sol.id not in theirs["cards"]
    assert len(theirs["zones"]["p1:hand"]) == len(zone(state, "p1", "hand"))
