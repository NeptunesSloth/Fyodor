"""Old saves keep loading after format changes."""

from __future__ import annotations

import copy

from app.game.history import History
from app.game.session import GameSession
from app.storage.save_format import SAVE_VERSION, decode, encode
from app.storage.saves import load_payload
from tests.game_helpers import act, enable, find, make_session, zone


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
    assert migrated["version"] == SAVE_VERSION == 6
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


def test_history_with_a_retired_action_type_still_loads_the_table(cards):
    s = make_session(cards)
    act(s, "p1", type="draw", count=3)
    payload = {"state": s.state.model_dump(mode="json"), "history": s.history.to_dict()}
    payload["history"]["actions"].append({"type": "add_reminder", "text": "upkeep thing", "actor": "p1", "ts": 0})
    payload["state"]["reminders"] = [{"id": "x", "owner": "p1", "text": "t", "when": "upkeep"}]
    state, history = load_payload(payload)
    assert history is None  # undo history is dropped, the table is intact
    assert len(zone(state, "p1", "hand")) == 3


def test_v2_save_with_reminders_migrates_to_v3_and_keeps_history(cards):
    s = make_session(cards)
    act(s, "p1", type="draw", count=3)
    act(s, "p1", type="life", delta=-2)
    history = s.history.to_dict()
    actions = list(history["actions"])
    # a v2 game had a reminder in between: drop it, keep everything else
    actions.insert(1, {"type": "add_reminder", "text": "x", "when": "upkeep", "actor": "p1", "ts": 0, "r": {"ids": ["rem1"]}})
    state = s.state.model_dump(mode="json")
    state["reminders"] = [{"id": "rem1", "owner": "p1", "text": "x", "when": "upkeep"}]
    for c in state["cards"].values():
        c.pop("face_down_kind", None)
    payload = {"format": "fyodor-save", "version": 2, "saved_at": 0, "state": state,
               "history": {**history, "actions": actions, "cursor": 3}}
    migrated = decode(encode(payload))
    assert migrated["version"] == SAVE_VERSION and migrated["migrated_from"] == 2
    assert [a["type"] for a in migrated["history"]["actions"]] == ["draw", "life"]
    assert migrated["history"]["cursor"] == 2
    loaded, restored = load_payload(migrated)
    assert restored is not None and restored.cursor == 2
    assert loaded.players["p1"].life == 38 and len(zone(loaded, "p1", "hand")) == 3


def test_v3_save_gets_card_origins_for_reset(cards):
    s = make_session(cards)
    state = s.state.model_dump(mode="json")
    for c in state["cards"].values():
        c.pop("origin", None)
    payload = {"format": "fyodor-save", "version": 3, "saved_at": 0, "state": state, "history": None}
    loaded, _ = load_payload(decode(encode(payload)))
    krenko = find(loaded, "Krenko, Mob Boss")
    song = find(loaded, "Seething Song")
    assert krenko.origin == "command" and song.origin == "sideboard" and find(loaded, "Sol Ring").origin == "library"


def test_v4_save_becomes_a_sandbox_game_in_v5(cards):
    s = make_session(cards)
    act(s, "p1", type="draw", count=2)
    state = s.state.model_dump(mode="json")
    state.pop("rules", None)
    state["settings"].pop("automation", None)
    history = s.history.to_dict()
    history["base"].pop("rules", None)
    payload = {"format": "fyodor-save", "version": 4, "saved_at": 0, "state": state, "history": history}
    migrated = decode(encode(payload))
    assert migrated["version"] == SAVE_VERSION == 6 and migrated["migrated_from"] == 4
    assert migrated["state"]["rules"] is None and migrated["state"]["settings"]["automation"] == "off"
    loaded, restored = load_payload(migrated)
    assert loaded.rules is None and loaded.settings.automation == "off"
    assert restored is not None and restored.cursor == 1


def _as_v5_rules(rules):
    if isinstance(rules, dict):
        prefs = rules.pop("prefs", {})
        rules["stops"] = {pid: {"own": p["stops_my_turn"], "others": p["stops_their_turn"],
                                "hold_priority": p["hold_priority"], "smart_pass": p["response"] == "auto"}
                          for pid, p in prefs.items()}


def _as_v5(state):
    state["settings"]["automation"] = "rules" if state["settings"]["automation"] == "full" else "off"
    state["settings"].pop("automation_options", None)
    _as_v5_rules(state.get("rules"))
    return state


def test_v5_rules_game_becomes_full_and_stops_become_preferences(cards):
    s = GameSession(enable(make_session(cards).state), cards=cards)
    act(s, "p2", type="set_stops", own=["upkeep", "main1"], others=["end"], smart_pass=False)
    act(s, "p1", type="pass_priority")
    history = s.history.to_dict()
    for action in history["actions"]:
        for step in action.get("r") or []:
            if step["type"] == "rules_sync":
                _as_v5_rules(step["rules"])
    payload = {"format": "fyodor-save", "version": 5, "saved_at": 0,
               "state": _as_v5(s.state.model_dump(mode="json")), "history": {**history, "base": _as_v5(history["base"])}}
    migrated = decode(encode(payload))
    assert migrated["version"] == SAVE_VERSION == 6
    loaded, restored = load_payload(migrated)
    assert loaded.settings.automation == "full" and loaded.settings.automation_options.auto_sba
    bob = loaded.rules.prefs["p2"]
    assert (bob.response, bob.stops_my_turn, bob.stops_their_turn) == ("on", ["upkeep", "main1"], ["end"])
    assert restored is not None and restored.rebuild().model_dump(mode="json") == loaded.model_dump(mode="json")


def test_v5_sandbox_game_stays_off(cards):
    s = make_session(cards)
    act(s, "p1", type="draw", count=2)
    history = s.history.to_dict()
    payload = {"format": "fyodor-save", "version": 5, "saved_at": 0,
               "state": _as_v5(s.state.model_dump(mode="json")), "history": {**history, "base": _as_v5(history["base"])}}
    loaded, restored = load_payload(decode(encode(payload)))
    assert loaded.settings.automation == "off" and loaded.rules is None and restored is not None
