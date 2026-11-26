"""-- test opponent -- over the API: the Play page's Sandbox start with an opponent (POST /games/{id}/bot), the top bar's bot speed and
Step button, and the server's paced driver (app/multiplayer/bots.py) playing its actions as recorded actions of its own."""

from __future__ import annotations

import time

import pytest

from app.multiplayer import bots

GRUUL = """Commander
1 Krenko, Mob Boss

Deck
14 Forest
6 Mountain
8 Grizzly Bears
6 Llanowar Elves
2 Lightning Bolt
"""


@pytest.fixture()
def table(client, monkeypatch):
    monkeypatch.setitem(bots.DELAYS, "normal", 30.0)  # (nothing plays by itself while the test sets up: it switches to Step first)
    deck = client.post("/api/decks", json={"text": GRUUL, "name": "Gruul"}).json()
    res = client.post("/api/games", json={"name": "Deck test", "format": "sandbox", "mode": "lan", "lobby": False, "seats": 1,
                                          "players": [{"name": "Alice", "deck_id": deck["id"]}], "first_player": 0})
    assert res.status_code == 201, res.text
    gid, code = res.json()["game"]["id"], res.json()["game"]["code"]
    host = {"X-Seat-Token": res.json()["seat"]["token"]}
    yield client, gid, code, host, deck["id"]
    client.delete(f"/api/games/{gid}", headers=host)


def test_the_sandbox_start_with_an_opponent_and_step_mode(table):
    client, gid, code, host, deck_id = table
    res = client.post(f"/api/games/{gid}/bot", json={"deck_id": deck_id, "name": "Gruul bot"}, headers=host)
    assert res.status_code == 201, res.text
    view = res.json()["view"]
    them = next(p for p in view["players"] if p["id"] == "p2")
    assert them["bot"] == "simple" and them["name"] == "Gruul bot" and not them["dummy"]
    assert them["hand_count"] == 7 and them["library_count"] == 37 - 7 - 1
    assert view["game"]["bot"]["speed"] == "normal"
    assert client.post("/api/join", json={"code": code, "name": "Eve", "seat": "p2"}).status_code != 200  # (nobody sits there)
    tile = next(p for p in client.get(f"/api/games/{gid}").json()["players"] if p["id"] == "p2")
    assert tile["claimed"] and tile["connected"]  # (the Play page's tile: not "1 open seat", never "away")
    guest = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    refused = client.post(f"/api/games/{gid}/bot", json={"deck_id": deck_id}, headers={"X-Seat-Token": guest})
    assert refused.status_code == 403
    refused = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "pass_priority"}, "as": "p2"}, headers=host)
    assert refused.status_code in (403, 409)  # (the host acts as their own seat, never as the opponent)

    res = client.post(f"/api/games/{gid}/bot/speed", json={"speed": "step"}, headers=host)
    assert res.status_code == 200 and res.json()["view"]["game"]["bot"]["speed"] == "step"

    def send(action: dict) -> dict:
        res = client.post(f"/api/games/{gid}/actions", json={"action": action}, headers=host)
        assert res.status_code == 200, (action, res.text)
        return res.json()

    view = send({"type": "configure", "automation": "full"})
    for _ in range(40):  # Alice passes until the opponent's turn is waiting on it
        if view["game"]["bot"]["waiting"]:
            break
        d = (view.get("rules") or {}).get("decision")
        if d is not None and d.get("player") == "p1" and d.get("options") is not None:
            if d["kind"] == "reconcile":
                firsts = {}
                for o in d["options"]:
                    firsts.setdefault(o.get("group"), o["id"])
                view = send({"type": "choose", "decision_id": d["id"], "option_ids": list(firsts.values())})
            else:
                view = send({"type": d["kind"]} if d["kind"].startswith("declare_") else {"type": "pass_priority"})
            continue
        view = send({"type": "pass_priority"})
    assert view["game"]["bot"]["waiting"], view["turn"]
    seq = view["game"]["seq"]
    time.sleep(0.3)
    assert client.get(f"/api/games/{gid}/view", headers=host).json()["game"]["seq"] == seq  # (Step: nothing plays by itself)
    res = client.post(f"/api/games/{gid}/bot/step", json={}, headers=host)
    assert res.status_code == 200, res.text
    for _ in range(50):  # (the driver plays it in the event loop, right after the reply)
        now = client.get(f"/api/games/{gid}/view", headers=host).json()
        if now["game"]["seq"] != seq:
            break
        time.sleep(0.05)
    assert now["game"]["seq"] != seq
    assert any(e.get("actor") == "p2" for e in now["log"])
    time.sleep(0.2)
    assert client.get(f"/api/games/{gid}/view", headers=host).json()["game"]["seq"] == now["game"]["seq"]  # (one action a step)
    res = client.post(f"/api/games/{gid}/bot/speed", json={"speed": "fast"}, headers=host)
    for _ in range(100):  # Fast: it plays on by itself until the game waits for Alice
        view = client.get(f"/api/games/{gid}/view", headers=host).json()
        if not view["game"]["bot"]["waiting"]:
            break
        time.sleep(0.05)
    assert not view["game"]["bot"]["waiting"]
