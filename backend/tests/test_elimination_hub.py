"""The elimination hub (docs/ELIMINATION_HUB.md): major public events, the private practice table, Deck Lab,
and the eliminated seat's view staying an ordinary public one."""

from __future__ import annotations

import asyncio
import json

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api.practice import sweep
from app.multiplayer.elimination import Pulse
from tests.conftest import guest
from tests.test_protocol_privacy import P1_DECK, P2_DECK, assert_hidden, cards_in

P3_DECK = """Commander
1x Lim-Dûl the Necromancer (tsp) 114
Deck
1x Llanowar Elves (dom) 168
1x Grizzly Bears (tst) M9
10x Forest (cmm) 1002
"""
REMOTE = guest()  # a guest's computer, not the host's


def h(token: str | None) -> dict[str, str]:
    return {"X-Seat-Token": token} if token else {}


def act(client, gid, token, action, status=200):
    res = client.post(f"/api/games/{gid}/actions", json={"action": action}, headers=h(token))
    assert res.status_code == status, res.text
    return res.json()


def view(client, gid, token):
    res = client.get(f"/api/games/{gid}/view", headers=h(token))
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture()
def table(client):
    """Alice, Bob and Carol at a LAN table with rules automation, plus a spectator."""
    decks = [client.post("/api/decks", json={"text": t}).json()["id"] for t in (P1_DECK, P2_DECK, P3_DECK)]
    game = client.post("/api/games", json={
        "mode": "lan", "shuffle": True, "automation": "full", "name": "Friday",
        "players": [{"name": n, "deck_id": d} for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)],
    })
    assert game.status_code == 201, game.text
    gid, code = game.json()["game"]["id"], game.json()["game"]["code"]
    alice = game.json()["seat"]["token"]
    bob = client.post("/api/join", json={"code": code}).json()["token"]
    carol = client.post("/api/join", json={"code": code}).json()["token"]
    spec = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    for tok in (alice, bob, carol):
        act(client, gid, tok, {"type": "draw", "count": 7})
    return client, gid, {"alice": alice, "bob": bob, "carol": carol, "spec": spec}


def room_of(client, gid):
    return client.app.state.services.hub.get(gid)


def concede(client, gid, token):
    act(client, gid, token, {"type": "concede"})


def events(client, gid, token):
    return view(client, gid, token)["game"]["events"]


def finish(client, gid, t, winner="p1"):
    """Alice and Bob, the two still in, agree that ``winner`` won."""
    assert client.post(f"/api/games/{gid}/night/propose", json={"result_type": "single", "winners": [winner]},
                       headers=h(t["alice"])).status_code == 200
    assert client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(t["bob"])).status_code == 200


# --------------------------------------------------------------------------- major public events


def test_departures_the_final_two_and_the_result_are_each_announced_once(table):
    client, gid, t = table
    assert events(client, gid, t["spec"]) == []  # the table as it starts is not news
    concede(client, gid, t["carol"])
    got = events(client, gid, t["spec"])
    assert [(e["kind"], e["text"], e["players"]) for e in got] == [
        ("out", "Carol conceded.", ["p3"]),
        ("final_two", "Final two players remain: Alice and Bob.", ["p1", "p2"]),
    ]
    # everyone sees the same public events; looking again (or another action) adds nothing
    assert events(client, gid, t["alice"]) == events(client, gid, t["carol"]) == got
    act(client, gid, t["alice"], {"type": "set_life", "player": "p1", "value": 33})
    assert events(client, gid, t["bob"]) == got
    finish(client, gid, t)
    last = events(client, gid, t["carol"])[-1]
    assert (last["kind"], last["text"], last["players"]) == ("result", "Alice wins.", ["p1"])
    assert len({e["id"] for e in events(client, gid, t["carol"])}) == 3


def test_a_rematch_starts_a_quiet_event_list():
    pulse = Pulse()

    class Seat:
        def __init__(self) -> None:
            self.left = False

    class Rules:
        conceded: list[str] = []
        lost: dict[str, str] = {}

    class State:
        seat_order = ["p1", "p2", "p3", "p4"]
        players = {p: Seat() for p in seat_order}
        rules = Rules()

    state = State()
    name = {"p1": "Ann", "p2": "Ben", "p3": "Cy", "p4": "Di"}.__getitem__
    state.rules.lost = {"p4": "0 life"}  # already true at the first look (a restart): not announced
    pulse.observe(state, 1, None, name)  # type: ignore[arg-type]
    assert pulse.public() == []
    state.rules.lost = {"p4": "0 life", "p3": "commander damage"}
    pulse.observe(state, 1, None, name)  # type: ignore[arg-type]
    assert [e["text"] for e in pulse.public()] == ["Cy was eliminated.", "Final two players remain: Ann and Ben."]
    state.rules.lost = {"p4": "0 life"}  # an undo brings Cy back, then Cy loses again: still one announcement
    pulse.observe(state, 1, None, name)  # type: ignore[arg-type]
    state.rules.lost = {"p4": "0 life", "p3": "0 life"}
    pulse.observe(state, 1, None, name)  # type: ignore[arg-type]
    assert len(pulse.public()) == 2
    pulse.observe(state, 1, {"result_type": "draw", "winners": [], "winner_names": []}, name)  # type: ignore[arg-type]
    assert pulse.public()[-1]["text"] == "The game is a draw."
    state.rules.lost = {}
    pulse.observe(state, 2, None, name)  # type: ignore[arg-type]
    assert pulse.public() == []  # game 2 of the night starts quiet


# --------------------------------------------------------------------------- privacy: out is not omniscient


def test_an_eliminated_seat_sees_only_what_a_spectator_sees(table):
    client, gid, t = table
    repo = client.app.state.services.cards
    concede(client, gid, t["carol"])
    state = room_of(client, gid).session.state
    hidden = [c for pid in ("p1", "p2") for z in ("hand", "library") for c in cards_in(state, pid, z)]
    assert hidden
    carol, spec = view(client, gid, t["carol"]), view(client, gid, t["spec"])
    assert carol["viewer"] == "p3"
    assert_hidden(carol, hidden, repo)
    # every other player's object looks exactly as it does to a spectator
    others = [cid for cid, c in spec["cards"].items() if c.get("owner") != "p3" and not c.get("zone", "").startswith("p3:")]
    assert any(spec["cards"][cid].get("hidden") for cid in others)
    for cid in others:
        assert carol["cards"].get(cid) == spec["cards"][cid], cid
    for pid in ("p1", "p2"):
        assert carol["zones"][f"{pid}:hand"] == spec["zones"][f"{pid}:hand"]
        assert carol["zones"][f"{pid}:library"] == spec["zones"][f"{pid}:library"]
    # and over the live socket, while the others keep playing
    with client.websocket_connect(f"/ws/games/{gid}?token={t['carol']}") as ws:
        frames = [ws.receive_json()]
        act(client, gid, t["alice"], {"type": "draw", "count": 1})
        act(client, gid, t["bob"], {"type": "look_top", "count": 3})
        for _ in range(2):
            frames.append(ws.receive_json())
    state = room_of(client, gid).session.state
    hidden = [c for pid in ("p1", "p2") for z in ("hand", "library") for c in cards_in(state, pid, z)]
    for frame in frames:
        assert frame["type"] == "state"
        assert_hidden(frame["view"], hidden, repo)
        assert frame["view"]["my_views"] == []


# --------------------------------------------------------------------------- the practice table


def practice(client, gid, token, **body):
    return client.post(f"/api/games/{gid}/practice", json=body, headers=h(token))


def test_only_a_player_who_is_out_gets_a_practice_table(table):
    client, gid, t = table
    assert practice(client, gid, t["carol"]).status_code == 409  # still in the game
    concede(client, gid, t["carol"])
    assert practice(client, gid, t["alice"]).status_code == 409
    assert practice(client, gid, t["spec"]).status_code == 403
    assert practice(client, gid, None).status_code == 403
    assert practice(client, gid, t["carol"]).status_code == 200


def test_the_practice_table_is_private_and_never_touches_the_live_game(table):
    client, gid, t = table
    services = client.app.state.services
    concede(client, gid, t["carol"])
    live = room_of(client, gid)
    before = (live.session.state.model_dump_json(), live.revision, len(live.session.notices), live.session.history.can_undo)
    saves_before = len(services.saves.list_all())

    res = practice(client, gid, t["carol"])
    assert res.status_code == 200, res.text
    pid, ptok = res.json()["game_id"], res.json()["token"]
    assert pid != gid and res.json()["resumed"] is False

    # what the practice table shows: Carol's own deck, nothing from the live game
    pv = view(client, pid, ptok)
    assert pv["viewer"] == "p1" and [p["name"] for p in pv["players"]] == ["Carol"]
    assert pv["game"]["practice"] == {"of": gid, "seat": "p3", "game": 1, "local": False}
    assert pv["game"]["code"] is None and "night" not in pv["game"]
    text = json.dumps(pv)
    assert "Alice" not in text and "Bob" not in text and "Friday" not in text
    assert not set(live.session.state.cards) & set(room_of(client, pid).session.state.cards)
    for c in live.session.state.cards.values():
        assert c.id not in text
    names = {c["name"] for c in pv["cards"].values() if c.get("name")}
    assert "Atraxa, Praetors' Voice" not in names and "Krenko, Mob Boss" not in names and "Lim-Dûl the Necromancer" in names
    assert pv["pregame"] and not pv["pregame"]["finished"]  # dealt a guided opening hand

    # play freely: mulligan, keep, draw, a token, a counter, undo
    act(client, pid, ptok, {"type": "mulligan_take"})
    act(client, pid, ptok, {"type": "mulligan_keep"})
    pstate = room_of(client, pid).session.state
    if pstate.pregame and not pstate.pregame.finished:  # London: put one card on the bottom
        act(client, pid, ptok, {"type": "mulligan_bottom", "card_ids": pstate.zones["p1:hand"][:1]})
    act(client, pid, ptok, {"type": "draw", "count": 2})
    act(client, pid, ptok, {"type": "create_token", "token": {"name": "Goblin", "type_line": "Token Creature — Goblin",
                                                              "power": "1", "toughness": "1"}, "x": 100, "y": 100})
    land = room_of(client, pid).session.state.zones["p1:hand"][0]
    act(client, pid, ptok, {"type": "move", "card_ids": [land], "to": {"zone": "battlefield"}, "x": 200, "y": 100})
    act(client, pid, ptok, {"type": "counter", "card_ids": [land], "kind": "charge", "delta": 2})
    assert client.post(f"/api/games/{pid}/undo", json={}, headers=h(ptok)).status_code == 200
    act(client, pid, ptok, {"type": "reset_deck"})

    # the live game: same state, same revision, no new log line, nothing saved
    after = (live.session.state.model_dump_json(), live.revision, len(live.session.notices), live.session.history.can_undo)
    assert after == before
    assert len(services.saves.list_all()) == saves_before
    assert all("Practice" not in s["name"] for s in services.saves.list_all())
    assert pid not in {g.game_id for g in services.journal.live()}

    # only Carol's practice token opens it; the table is never listed or joinable
    for token in (t["alice"], t["carol"], t["spec"], None):
        assert client.get(f"/api/games/{pid}/view", headers=h(token)).status_code == 403
    assert client.post(f"/api/games/{pid}/actions", json={"action": {"type": "draw"}}, headers=h(t["alice"])).status_code == 403
    assert pid not in {g["id"] for g in client.get("/api/games").json()}
    assert pid not in {g["id"] for g in client.get("/api/games", headers=REMOTE).json()}
    code = room_of(client, pid).code
    assert client.post("/api/join", json={"code": code, "spectate": True}).status_code == 403
    # and it is never a pod game
    assert client.post(f"/api/games/{pid}/result", json={"result_type": "single", "winners": ["p1"]}, headers=h(ptok)).status_code == 403
    assert client.post(f"/api/games/{pid}/night/propose", json={"result_type": "single", "winners": ["p1"]},
                       headers=h(ptok)).status_code == 409
    assert services.stats.for_game(pid) is None


def test_practice_resumes_resets_and_goes_away_when_the_live_game_moves_on(table):
    client, gid, t = table
    hub = client.app.state.services.hub
    concede(client, gid, t["carol"])
    first = practice(client, gid, t["carol"]).json()
    act(client, first["game_id"], first["token"], {"type": "mulligan_keep"})
    again = practice(client, gid, t["carol"]).json()
    assert again["game_id"] == first["game_id"] and again["resumed"] is True
    assert client.get(f"/api/games/{first['game_id']}/view", headers=h(first["token"])).status_code == 403  # a fresh token
    kept = view(client, again["game_id"], again["token"])  # where she left it: the opening hand kept
    assert (kept["pregame"] is None or kept["pregame"]["finished"]) and len(kept["zones"]["p1:hand"]) == 7
    fresh = practice(client, gid, t["carol"], reset=True).json()
    assert fresh["game_id"] != first["game_id"] and hub.get(first["game_id"]) is None
    # the live game ends and the pod plays again: the practice table goes away
    finish(client, gid, t)
    assert practice(client, gid, t["carol"]).status_code == 409  # the game is over: back to the result
    for tok in (t["alice"], t["bob"], t["carol"]):
        client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(tok))
    assert room_of(client, gid).night.number == 2
    asyncio.run(sweep(hub))
    assert hub.get(fresh["game_id"]) is None


def test_putting_the_practice_table_away(table):
    client, gid, t = table
    concede(client, gid, t["carol"])
    opened = practice(client, gid, t["carol"]).json()
    pid = opened["game_id"]
    assert client.delete(f"/api/games/{gid}/practice", headers=h(t["bob"])).status_code == 204  # Bob's, not Carol's
    assert room_of(client, pid) is not None
    with client.websocket_connect(f"/ws/games/{pid}?token={opened['token']}") as ws:
        assert ws.receive_json()["type"] == "state"
        assert client.delete(f"/api/games/{gid}/practice", headers=h(t["carol"])).status_code == 204
        with pytest.raises(WebSocketDisconnect) as closed:
            for _ in range(5):  # the connection's own update arrives first
                ws.receive_json()
        assert closed.value.code == 4404
    assert room_of(client, pid) is None


def test_hot_seat_practice_names_the_seat(client):
    decks = [client.post("/api/decks", json={"text": x}).json()["id"] for x in (P1_DECK, P2_DECK, P3_DECK)]
    gid = client.post("/api/games", json={"mode": "local", "automation": "full", "players": [
        {"name": n, "deck_id": d} for n, d in zip(("Ann", "Ben", "Cy"), decks, strict=True)]}).json()["game"]["id"]
    res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "concede"}, "as": "p2"})
    assert res.status_code == 200, res.text
    assert practice(client, gid, None, viewer="p1").status_code == 409  # Ann is still in
    res = practice(client, gid, None, viewer="p2")
    assert res.status_code == 200, res.text
    pv = view(client, res.json()["game_id"], res.json()["token"])
    assert pv["game"]["practice"] == {"of": gid, "seat": "p2", "game": 1, "local": True}
    assert [p["name"] for p in pv["players"]] == ["Ben"]


# --------------------------------------------------------------------------- Deck Lab


def test_deck_lab_copies_the_match_deck_and_never_touches_it(table):
    client, gid, t = table
    services = client.app.state.services
    live = room_of(client, gid)
    setup = live.night.setups["p3"]
    original = services.decks.get(setup.deck_id)
    snapshot = [(c.section, c.quantity, c.name, c.printing_id) for c in setup.cards]
    state_before = live.session.state.model_dump_json()

    # the host computer: a new deck in the library, ready for the deck editor
    res = client.post(f"/api/games/{gid}/deck-lab", json={}, headers=h(t["carol"]))
    assert res.status_code == 200, res.text
    lab = res.json()
    assert lab["deck_id"] and lab["deck_id"] != setup.deck_id and lab["name"].endswith("(copy)")
    assert lab["commanders"] == ["Lim-Dûl the Necromancer"] and "10 Forest (CMM) 1002" in lab["text"]
    copy = client.get(f"/api/decks/{lab['deck_id']}").json()
    assert sorted((e["section"], e["quantity"], e["name"]) for e in copy["entries"]) == sorted(s[:3] for s in snapshot)
    # edit and save the copy: the match deck, the library original and the live game don't change
    entries = [e for e in copy["entries"] if e["name"] != "Grizzly Bears"]
    assert client.put(f"/api/decks/{lab['deck_id']}", json={"name": "Goblins v2", "entries": entries}).status_code == 200
    assert services.decks.get(setup.deck_id).entries == original.entries
    assert [(c.section, c.quantity, c.name, c.printing_id) for c in live.night.setups["p3"].cards] == snapshot
    assert live.session.state.model_dump_json() == state_before

    # a guest's computer gets the list for its own "My decks"; the host's library is not theirs to write
    count = len(services.decks.list_all())
    res = client.post(f"/api/games/{gid}/deck-lab", json={}, headers={**h(t["bob"]), **REMOTE})
    assert res.status_code == 200, res.text
    assert res.json()["deck_id"] is None and "1 Krenko, Mob Boss (DDN) 13" in res.json()["text"]
    assert len(services.decks.list_all()) == count
    # only your own deck, and spectators have none
    assert "Atraxa" not in res.json()["text"] and "Lim-Dûl" not in res.json()["text"]
    assert client.post(f"/api/games/{gid}/deck-lab", json={}, headers=h(t["spec"])).status_code == 403


def test_a_practice_table_never_asks_for_a_pod_result(table, monkeypatch):
    """-- rules result -- a practice table can turn the rules on, but the engine ending its game opens no end-game proposal:
    a practice table has no pod result to record (record_game_result refuses it)."""
    from app.multiplayer import night as night_mod

    client, gid, t = table
    concede(client, gid, t["carol"])
    res = practice(client, gid, t["carol"])
    proom = room_of(client, res.json()["game_id"])
    monkeypatch.setattr(night_mod, "rules_ending", lambda state: ("win:p1", "single", ["p1"]))
    night_mod.follow_rules(proom)
    assert proom.night.proposal is None and proom.night.rules_end is None
