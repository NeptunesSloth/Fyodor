"""-- I have a response -- (app/rules/response_call.py, app/multiplayer/response_call.py) and -- flip the table --.

"Wait, I have a response!": a seated player without priority calls for a hold; they get priority at the next moment they legally
would, whatever their RESPONSE setting or PASS UNTIL … said, and everyone hears it. It never takes priority out of turn."""

from __future__ import annotations

import json
import time

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from app.multiplayer import bots, response_call
from app.rules import progress
from tests.game_helpers import act, enable, find, make_session
from tests.pod_c_kit import hold, mana, table
from tests.test_rules_effects import replay_matches


@pytest.fixture()
def s(cards):
    s = GameSession(enable(make_session(cards).state), cards=cards)
    act(s, "p1", type="pass_priority")  # Alice's first main phase
    return s


def r(s):
    return s.state.rules


def log_text(s, viewer: str) -> str:
    return json.dumps(s.view(viewer)["log"], ensure_ascii=False)


def cast_ring(s):
    act(s, "p1", type="draw", count=7)
    act(s, "p1", type="play_land", card_id=find(s.state, "Mountain", "p1").id)
    ring = find(s.state, "Sol Ring", "p1")
    act(s, "p1", type="cast_spell", card_id=ring.id)
    return ring


def test_a_hold_stops_the_engine_before_the_top_object_resolves_even_with_response_off(s):
    act(s, "p2", type="set_prefs", response="off")  # Bob: pass whenever the rules allow
    hold(s)
    ring = cast_ring(s)
    assert r(s).priority == "p1" and s.state.cards[ring.id].zone == "stack"
    act(s, "p2", type="set_prefs", respond=True)  # "wait, I have a response!"
    assert r(s).responding == ["p2"] and s.view("p1")["rules"]["responding"] == ["p2"]  # everyone sees it
    assert "Bob has a response!" in log_text(s, "p1")
    act(s, "p1", type="pass_priority")
    assert r(s).priority == "p2" and s.state.cards[ring.id].zone == "stack"  # Bob gets it before Sol Ring resolves
    assert r(s).responding == []  # answered
    act(s, "p2", type="pass_priority")
    assert s.state.cards[ring.id].zone == "p1:battlefield"
    replay_matches(s)


def test_a_hold_takes_back_an_automatic_pass_but_never_a_players_own(s):
    act(s, "p2", type="set_prefs", response="on")  # Bob stops at every priority
    ring = cast_ring(s)  # Alice is passed for, Arena-style, right after her cast; Bob has priority
    assert r(s).priority == "p2" and r(s).passed == ["p1"] and s.state.cards[ring.id].zone == "stack"
    act(s, "p1", type="set_prefs", respond=True)  # Alice: wait, I respond to that myself
    assert r(s).passed == []  # (the engine's pass for her is taken back)
    act(s, "p2", type="pass_priority")
    assert r(s).priority == "p1" and s.state.cards[ring.id].zone == "stack"
    act(s, "p1", type="pass_priority")  # (Bob passed already: Sol Ring resolves)
    assert s.state.cards[ring.id].zone == "p1:battlefield" and r(s).priority == "p1"
    act(s, "p1", type="pass_priority")  # Alice's own pass stands…
    assert r(s).priority == "p2" and r(s).passed == ["p1"]
    act(s, "p1", type="set_prefs", respond=True)
    assert r(s).passed == ["p1"]  # …a hold then waits for her next priority instead
    act(s, "p2", type="pass_priority")
    assert s.state.turn.phase != "main1" and r(s).priority == "p1" and r(s).responding == []


def test_a_hold_overrides_pass_until(cards):
    s = table(cards, ["Lightning Bolt", "Lightning Bolt"])
    bolts = [c.id for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=bolts, to={"zone": "hand"})
    hold(s)
    mana(s, R=2)
    for cid in bolts:
        act(s, "p1", type="cast_spell", card_id=cid, targets=["p2"])
    act(s, "p1", type="set_prefs", response="on")
    act(s, "p2", type="set_prefs", response="on")
    act(s, "p1", type="pass_priority")
    assert r(s).priority == "p2"
    act(s, "p2", type="pass_priority", until="stack_empty")  # Bob: Resolve all
    assert len(s.state.zones["stack"]) == 1 and r(s).priority == "p1"
    act(s, "p2", type="set_prefs", respond=True)  # …then sees the first Bolt hit: wait!
    act(s, "p1", type="pass_priority")
    assert r(s).priority == "p2" and len(s.state.zones["stack"]) == 1  # the last Bolt waits for him
    assert r(s).prefs["p2"].pass_until is None  # (his Resolve all is over)
    replay_matches(s)


def test_a_hold_called_mid_chain_stops_it_at_the_next_priority_and_is_recorded(cards):
    s = table(cards, ["Lightning Bolt"] * 4)
    bolts = [c.id for c in s.state.cards.values() if c.name == "Lightning Bolt" and c.owner == "p1"]
    act(s, "p1", type="move", card_ids=bolts, to={"zone": "hand"})
    hold(s)
    mana(s, R=4)
    for cid in bolts:
        act(s, "p1", type="cast_spell", card_id=cid, targets=["p2"])
    act(s, "p2", type="set_prefs", response="off")  # Bob passes for himself whenever he may

    class Watcher:  # the hub's interim stream: a hold heard after the first Bolt resolved
        def __init__(self) -> None:
            self.calls: dict[str, float] = {}

        def __call__(self, plan, resolved: int) -> None:
            if resolved == 1:
                self.calls["p2"] = 0.0

    prepared = s.prepare("p1", {"type": "pass_priority", "until": "stack_empty"}, watcher=Watcher())
    s.commit(prepared)
    assert len(s.state.zones["stack"]) == 3 and r(s).priority == "p2"  # the chain stopped for him
    assert "Bob has a response!" in log_text(s, "p1")
    replay_matches(s)  # (recorded in the action's steps: replay doesn't depend on when he called)
    assert progress.calls(object()) == ()  # (outside an action nothing is pending)


def test_a_hold_is_cancelled_by_pressing_again_and_refused_for_players_who_left(s):
    act(s, "p2", type="set_prefs", respond=True)
    act(s, "p2", type="set_prefs", respond=False)
    assert r(s).responding == [] and "withdrew" in log_text(s, "p1")
    act(s, "p2", type="concede")
    with pytest.raises(ActionError):
        act(s, "p2", type="set_prefs", respond=True)


def test_a_hold_never_takes_priority_out_of_turn(s):
    act(s, "p2", type="set_prefs", respond=True)
    assert r(s).priority == "p1"  # Alice keeps her priority: Bob gets his when she passes
    act(s, "p1", type="pass_priority")
    assert r(s).priority == "p2" and s.state.turn.phase == "main1"


def test_concede_and_flip_the_table_is_a_concession_with_a_log_line(s):
    act(s, "p2", type="concede", flip=True)
    assert "p2" in r(s).conceded
    assert "Bob flipped the table" in log_text(s, "p1")
    replay_matches(s)


# ------------------------------------------------------------------------------------------- over the API

@pytest.fixture()
def lan(client):
    from tests.test_lobby import ALICE_DECK, BOB_DECK, create_lobby, h

    gid, code, alice = create_lobby(client)
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    for tok, deck in ((alice, ALICE_DECK), (bob, BOB_DECK)):
        assert client.post(f"/api/games/{gid}/lobby/deck", json={"text": deck}, headers=h(tok)).status_code == 200
        client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(tok))
    assert client.post(f"/api/games/{gid}/lobby/start", json={}, headers=h(alice)).status_code == 200
    return client, gid, alice, bob, h


def _next_signal(ws):
    got = ws.receive_json()
    while got["type"] != "signal":
        got = ws.receive_json()
    return got


def test_the_shout_reaches_everyone_and_the_flip_is_rate_limited_and_only_ones_own(lan):
    client, gid, alice, bob, h = lan
    room = client.app.state.services.hub.get(gid)
    assert client.post(f"/api/games/{gid}/actions", json={"action": {"type": "configure", "automation": "full"}},
                       headers=h(alice)).status_code == 200
    for tok in (alice, bob):  # (opening hands kept)
        client.post(f"/api/games/{gid}/actions", json={"action": {"type": "mulligan_keep"}}, headers=h(tok))
    state = room.session.state
    assert state.rules is not None and (state.pregame is None or state.pregame.finished)
    holder = state.rules.priority or state.turn.active_player
    caller_tok = alice if client.get(f"/api/games/{gid}/view", headers=h(alice)).json()["viewer"] != holder else bob
    other_tok = bob if caller_tok == alice else alice
    caller = client.get(f"/api/games/{gid}/view", headers=h(caller_tok)).json()["viewer"]
    with client.websocket_connect(f"/ws/games/{gid}?token={other_tok}") as ws:
        ws.receive_json()
        res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "set_prefs", "respond": True}}, headers=h(caller_tok))
        assert res.status_code == 200, res.text
        got = _next_signal(ws)
        assert got["kind"] == "response" and got["from"] == caller and got["on"] is True
        assert caller in client.get(f"/api/games/{gid}/view", headers=h(other_tok)).json()["rules"]["responding"]
        assert not response_call.waiting(room)  # (applied: nothing pending any more)
        signal = f"/api/games/{gid}/night/signal"
        assert client.post(signal, json={"kind": "flip"}, headers=h(caller_tok)).status_code == 200
        got = _next_signal(ws)
        assert got["kind"] == "flip" and got["from"] == caller and got["concede"] is False
        assert client.post(signal, json={"kind": "flip"}, headers=h(caller_tok)).status_code == 429  # once in a while
        res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "concede", "flip": True}}, headers=h(other_tok))
        assert res.status_code == 200, res.text
        got = _next_signal(ws)
        other = client.get(f"/api/games/{gid}/view", headers=h(other_tok)).json()["viewer"]
        assert got["kind"] == "flip" and got["from"] == other and got["concede"] is True
    code = client.get(f"/api/games/{gid}").json()["code"]
    spectator = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    assert client.post(f"/api/games/{gid}/night/signal", json={"kind": "flip"}, headers=h(spectator)).status_code == 403


def test_the_test_opponent_waits_while_a_hold_is_pending(client, monkeypatch):
    from tests.test_test_opponent_api import GRUUL

    monkeypatch.setitem(bots.DELAYS, "normal", 30.0)
    deck = client.post("/api/decks", json={"text": GRUUL, "name": "Gruul"}).json()
    res = client.post("/api/games", json={"name": "Deck test", "format": "sandbox", "mode": "lan", "lobby": False, "seats": 1,
                                          "players": [{"name": "Alice", "deck_id": deck["id"]}], "first_player": 0})
    gid = res.json()["game"]["id"]
    host = {"X-Seat-Token": res.json()["seat"]["token"]}
    try:
        assert client.post(f"/api/games/{gid}/bot", json={"deck_id": deck["id"], "name": "Gruul bot"}, headers=host).status_code == 201
        assert client.post(f"/api/games/{gid}/bot/speed", json={"speed": "step"}, headers=host).status_code == 200

        def send(action: dict) -> dict:
            res = client.post(f"/api/games/{gid}/actions", json={"action": action}, headers=host)
            assert res.status_code == 200, (action, res.text)
            return res.json()

        view = send({"type": "configure", "automation": "full"})
        for _ in range(40):  # Alice passes until the opponent is waited on
            if view["game"]["bot"]["waiting"]:
                break
            d = (view.get("rules") or {}).get("decision")
            if d is not None and d.get("player") == "p1" and d.get("options") is not None:
                if d["kind"] == "reconcile":
                    firsts: dict = {}
                    for o in d["options"]:
                        firsts.setdefault(o.get("group"), o["id"])
                    view = send({"type": "choose", "decision_id": d["id"], "option_ids": list(firsts.values())})
                else:
                    view = send({"type": d["kind"]} if d["kind"].startswith("declare_") else {"type": "pass_priority"})
                continue
            view = send({"type": "pass_priority"})
        assert view["game"]["bot"]["waiting"]
        room = client.app.state.services.hub.get(gid)
        response_call.pending(room)["p1"] = time.monotonic()  # Alice's hold, heard and not applied yet
        seq = view["game"]["seq"]
        assert client.post(f"/api/games/{gid}/bot/speed", json={"speed": "fast"}, headers=host).status_code == 200
        time.sleep(0.6)
        assert client.get(f"/api/games/{gid}/view", headers=host).json()["game"]["seq"] == seq  # the opponent waits
        response_call.pending(room).clear()  # (the hold landed)
        for _ in range(30):
            time.sleep(0.1)
            if client.get(f"/api/games/{gid}/view", headers=host).json()["game"]["seq"] != seq:
                break
        assert client.get(f"/api/games/{gid}/view", headers=host).json()["game"]["seq"] != seq  # then it plays on
    finally:
        client.delete(f"/api/games/{gid}", headers=host)
