"""-- undo policy (gap 3) -- the host's undo setting is enforced on the server (app/game/undo_rights.py): "everyone" (the
default) keeps today's behavior, "own" lets a player take back only their own history entries, "host" only the host (anyone
at a hot-seat table, where everyone sits at the host computer). Each view says what its client needs to show the controls."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.history import History
from app.game.session import GameSession
from app.game.state import GameState
from tests.conftest import guest
from tests.game_helpers import act, make_session, zone
from tests.test_games_api import ATRAXA, KRENKO
from tests.test_rules_effects import build, draw_all, hand, mana

REMOTE = guest()


def replay_matches(s: GameSession) -> None:
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def life(s: GameSession, pid: str) -> int:
    return s.state.players[pid].life


# ---------------------------------------------------------------------------- session


def test_everyone_is_the_default_and_unchanged(cards):
    s = make_session(cards)
    assert s.state.settings.undo_policy == "everyone"
    act(s, "p1", type="life", delta=-3)
    s.undo("p2")  # anyone undoes anyone's action, host or not
    assert life(s, "p1") == 40
    s.redo("p2")
    assert life(s, "p1") == 37


def test_own_policy_takes_back_only_your_own_entries(cards):
    s = make_session(cards)
    act(s, "p1", type="configure", undo_policy="own")
    act(s, "p1", type="life", delta=-3)
    act(s, "p2", type="life", delta=-2)  # e.g. Bob's answer to Alice's spell: his own entry
    with pytest.raises(ActionError, match="only undo their own actions.*the last action was Bob's"):
        s.undo("p1", host=True)  # the host gets no exception (their override: restore from history)
    s.undo("p2")
    assert life(s, "p2") == 40
    with pytest.raises(ActionError, match="only redo their own actions.*the next action to redo was Bob's"):
        s.redo("p1")
    s.undo("p1")
    assert life(s, "p1") == 40
    s.redo("p1")
    s.redo("p2")
    assert (life(s, "p1"), life(s, "p2")) == (37, 38)
    replay_matches(s)


def test_own_policy_counts_rules_follow_ups_as_the_senders(cards):
    """Everything the server compiles into an intent (the spell resolving, its enters trigger, the draw) is one entry: the
    caster's. Under "own" the caster takes it back whole; another player can't."""
    s = build(cards)
    draw_all(s)
    act(s, "p1", type="configure", undo_policy="own")
    mana(s, G=2)
    hand_before = list(zone(s.state, "p1", "hand"))
    visionary = hand(s, "p1", "Elvish Visionary")
    act(s, "p1", type="cast_spell", card_id=visionary.id)
    assert s.state.cards[visionary.id].zone == "p1:battlefield"
    with pytest.raises(ActionError, match="Alice's"):
        s.undo("p2")
    s.undo("p1")
    assert zone(s.state, "p1", "hand") == hand_before and s.state.cards[visionary.id].zone == "p1:hand"
    replay_matches(s)


def test_host_policy_is_the_hosts_alone(cards):
    s = make_session(cards)
    act(s, "p1", type="configure", undo_policy="host")
    act(s, "p2", type="life", delta=-2)
    with pytest.raises(ActionError, match="Only the host may undo"):
        s.undo("p2")
    s.undo("p1", host=True)  # anyone's action
    assert life(s, "p2") == 40
    with pytest.raises(ActionError, match="Only the host may redo"):
        s.redo("p2")
    s.redo("p1", host=True)
    assert life(s, "p2") == 38


def test_nothing_to_undo_wins_over_the_policy(cards):
    s = make_session(cards)
    s.state.settings.undo_policy = "host"
    with pytest.raises(ActionError, match="Nothing to undo"):
        s.undo("p2")


def test_undo_policy_survives_undo_save_and_load(cards):
    s = make_session(cards)
    act(s, "p1", type="configure", undo_policy="own")
    act(s, "p2", type="life", delta=-1)
    s.undo("p2")
    s.redo("p2")
    replay_matches(s)
    data = json.loads(json.dumps({"state": s.state.model_dump(mode="json"), "history": s.history.to_dict()}))
    loaded = GameSession(GameState.model_validate(data["state"]), cards=cards, history=History.from_dict(data["history"]))
    assert loaded.state.settings.undo_policy == "own"
    with pytest.raises(ActionError, match="Bob's"):
        loaded.undo("p1")
    loaded.undo("p2")
    replay_matches(loaded)
    # an old save without the field loads as "everyone"
    old = data["state"]
    del old["settings"]["undo_policy"]
    assert GameState.model_validate(old).settings.undo_policy == "everyone"


# ---------------------------------------------------------------------------- API: LAN room with a host and guests


@pytest.fixture()
def lan(client):
    a = client.post("/api/decks", json={"text": KRENKO}).json()["id"]
    b = client.post("/api/decks", json={"text": ATRAXA}).json()["id"]
    body = {"name": "Undo night", "mode": "lan", "players": [{"name": "Alice", "deck_id": a}, {"name": "Bob", "deck_id": b},
                                                             {"name": "Cleo", "deck_id": b}]}
    game = client.post("/api/games", json=body).json()
    gid, code = game["game"]["id"], game["game"]["code"]
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}, headers=REMOTE).json()["token"]
    cleo = client.post("/api/join", json={"code": code, "name": "Cleo"}, headers=REMOTE).json()["token"]
    return {"gid": gid, "host": game["seat"]["token"], "host_computer": game["host_token"], "bob": bob, "cleo": cleo}


def post(client, t, path, token, json_body=None, **headers):
    return client.post(f"/api/games/{t['gid']}/{path}", json=json_body or {}, headers={"X-Seat-Token": token, **headers})


def act_as(client, t, token, action, **headers):
    return post(client, t, "actions", token, {"action": action}, **headers)


def view_of(client, t, token, **headers):
    return client.get(f"/api/games/{t['gid']}/view", headers={"X-Seat-Token": token, **headers}).json()


def test_lan_default_lets_anyone_undo(client, lan):
    assert act_as(client, lan, lan["host"], {"type": "life", "delta": -3}).status_code == 200
    res = post(client, lan, "undo", lan["bob"], **REMOTE)
    assert res.status_code == 200 and res.json()["players"][0]["life"] == 40
    game = res.json()["game"]
    assert game["settings"]["undo_policy"] == "everyone" and game["undo_by"] is None and game["redo_by"] is None


def test_lan_only_the_host_configures_and_host_policy_holds(client, lan):
    assert act_as(client, lan, lan["bob"], {"type": "configure", "undo_policy": "everyone"}, **REMOTE).status_code == 403
    assert act_as(client, lan, lan["host"], {"type": "configure", "undo_policy": "host"}).status_code == 200
    assert act_as(client, lan, lan["bob"], {"type": "life", "delta": -2}, **REMOTE).status_code == 200
    res = post(client, lan, "undo", lan["bob"], **REMOTE)
    assert res.status_code == 409 and "Only the host may undo" in res.json()["detail"]
    assert view_of(client, lan, lan["bob"], **REMOTE)["game"]["undo_host"] is False
    assert view_of(client, lan, lan["host"])["game"]["undo_host"] is True
    # the host computer watching without a seat is a spectator: it never undoes (as before)
    assert post(client, lan, "undo", lan["host_computer"]).status_code == 403
    res = post(client, lan, "undo", lan["host"])
    assert res.status_code == 200 and res.json()["players"][1]["life"] == 40
    assert post(client, lan, "redo", lan["cleo"], **REMOTE).status_code == 409
    assert post(client, lan, "redo", lan["host"]).json()["players"][1]["life"] == 38


def test_lan_own_policy_and_its_view(client, lan):
    act_as(client, lan, lan["host"], {"type": "configure", "undo_policy": "own"})
    act_as(client, lan, lan["bob"], {"type": "life", "delta": -2}, **REMOTE)
    # every viewer learns whose entry the next undo touches (public: the log names every action's actor), nothing more
    for token, headers in ((lan["host"], {}), (lan["bob"], REMOTE), (lan["cleo"], REMOTE)):
        game = view_of(client, lan, token, **headers)["game"]
        assert (game["settings"]["undo_policy"], game["undo_by"], game["redo_by"]) == ("own", "p2", None)
    for token, headers in ((lan["host"], {}), (lan["cleo"], REMOTE)):
        res = post(client, lan, "undo", token, **headers)
        assert res.status_code == 409 and "the last action was Bob's" in res.json()["detail"]
    res = post(client, lan, "undo", lan["bob"], **REMOTE)
    assert res.status_code == 200 and res.json()["game"]["undo_by"] == "p1" and res.json()["game"]["redo_by"] == "p2"
    assert post(client, lan, "redo", lan["cleo"], **REMOTE).status_code == 409
    assert post(client, lan, "redo", lan["bob"], **REMOTE).status_code == 200


def test_lan_websocket_undo_obeys_the_policy(client, lan):
    act_as(client, lan, lan["host"], {"type": "configure", "undo_policy": "host"})
    act_as(client, lan, lan["bob"], {"type": "life", "delta": -2}, **REMOTE)
    with client.websocket_connect(f"/ws/games/{lan['gid']}?token={lan['bob']}", headers=REMOTE) as ws:
        assert ws.receive_json()["type"] == "state"
        ws.send_json({"type": "undo", "id": 1})
        while (msg := ws.receive_json())["type"] == "state":
            pass
        assert msg["type"] == "error" and "Only the host may undo" in msg["message"]
    with client.websocket_connect(f"/ws/games/{lan['gid']}?token={lan['host']}") as ws:
        assert ws.receive_json()["type"] == "state"
        ws.send_json({"type": "undo", "id": 2})
        while (msg := ws.receive_json())["type"] == "state":
            pass
        assert msg["type"] == "ack" and msg["status"] == "ACCEPTED"
    assert view_of(client, lan, lan["host"])["players"][1]["life"] == 40


# ---------------------------------------------------------------------------- API: hot-seat game on one computer


@pytest.fixture()
def local(client):
    a = client.post("/api/decks", json={"text": KRENKO}).json()["id"]
    b = client.post("/api/decks", json={"text": ATRAXA}).json()["id"]
    body = {"name": "Hot seat", "players": [{"name": "Alice", "deck_id": a}, {"name": "Bob", "deck_id": b}]}
    return client.post("/api/games", json=body).json()["game"]["id"]


def local_act(client, gid, actor, action):
    return client.post(f"/api/games/{gid}/actions", json={"action": action, "as": actor, "viewer": actor})


def test_hot_seat_host_policy_allows_everyone_at_the_host_computer(client, local):
    local_act(client, local, "p1", {"type": "configure", "undo_policy": "host"})
    local_act(client, local, "p1", {"type": "life", "delta": -3})
    res = client.post(f"/api/games/{local}/undo", json={"as": "p2", "viewer": "p2"})
    assert res.status_code == 200 and res.json()["players"][0]["life"] == 40
    assert res.json()["game"]["undo_host"] is True


def test_hot_seat_own_policy_follows_the_acting_seat(client, local):
    local_act(client, local, "p1", {"type": "configure", "undo_policy": "own"})
    local_act(client, local, "p1", {"type": "life", "delta": -3})
    res = client.post(f"/api/games/{local}/undo", json={"as": "p2", "viewer": "p2"})
    assert res.status_code == 409 and "Alice's" in res.json()["detail"]
    view = client.get(f"/api/games/{local}/view", params={"viewer": "all"}).json()
    assert view["game"]["undo_by"] == "p1"
    assert client.post(f"/api/games/{local}/undo", json={"as": "p1", "viewer": "all"}).status_code == 200


def test_save_and_load_keep_the_policy(client, local):
    local_act(client, local, "p1", {"type": "configure", "undo_policy": "own"})
    local_act(client, local, "p2", {"type": "life", "delta": -1})
    saved = client.post(f"/api/games/{local}/save", json={"name": "Own undo"}).json()
    gid = client.post(f"/api/saves/{saved['id']}/load", json={}).json()["game"]["id"]
    view = client.get(f"/api/games/{gid}/view", params={"viewer": "p1"}).json()
    assert view["game"]["settings"]["undo_policy"] == "own" and view["game"]["undo_by"] == "p2"
    assert client.post(f"/api/games/{gid}/undo", json={"as": "p1", "viewer": "p1"}).status_code == 409
    assert client.post(f"/api/games/{gid}/undo", json={"as": "p2", "viewer": "p2"}).status_code == 200
