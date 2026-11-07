"""Game night (docs/GAME_NIGHT_FLOW.md): pod turn order, agreed endings, rematch vote, lobby return."""

from __future__ import annotations

import itertools
import time

import pytest

from app.multiplayer.night import Night, roll_order, winner_last
from tests.test_lobby import ALICE_DECK, BOB_DECK, create_lobby, h, lobby_of

# --------------------------------------------------------------------------- pure turn-order rules


def scripted(values):
    it = iter(values)
    return lambda: next(it)


def test_d20_orders_highest_first():
    order, rounds = roll_order(["A", "B", "C", "D"], scripted([7, 19, 3, 12]))
    assert order == ["B", "D", "A", "C"]
    assert rounds == [{"A": 7, "B": 19, "C": 3, "D": 12}]


def test_d20_ties_reroll_only_among_the_tied_players():
    # A and C tie on 15; only they reroll (C wins it); D and B tie on 4 and reroll twice
    order, rounds = roll_order(["A", "B", "C", "D"], scripted([15, 4, 15, 4, 2, 9, 6, 6, 1, 20]))
    assert order == ["C", "A", "D", "B"]  # D rolled 20 in the second B/D tie-break
    assert rounds == [{"A": 15, "B": 4, "C": 15, "D": 4}, {"A": 2, "C": 9}, {"B": 6, "D": 6}, {"B": 1, "D": 20}]


def test_winner_goes_last_and_the_rest_keep_their_order():
    # the A/B/C/D example from the plan
    assert winner_last(["A", "B", "C", "D"], "C") == ["A", "B", "D", "C"]
    assert winner_last(["A", "B", "D", "C"], "D") == ["A", "B", "C", "D"]


def test_plan_rolls_again_without_a_single_winner():
    assert Night.plan(["A", "B"], "B")[:2] == (["A", "B"], "winner_last")
    order, source, rounds = Night.plan(["A", "B"], None, scripted([3, 17]))
    assert (order, source, rounds) == (["B", "A"], "d20", [{"A": 3, "B": 17}])


# --------------------------------------------------------------------------- LAN flow


@pytest.fixture()
def table(client):
    """A two-player LAN game started from the lobby under the pod rule."""
    gid, code, alice = create_lobby(client, turn_order="pod")
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    for tok, deck in ((alice, ALICE_DECK), (bob, BOB_DECK)):
        assert client.post(f"/api/games/{gid}/lobby/deck", json={"text": deck}, headers=h(tok)).status_code == 200
        client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(tok))
    res = client.post(f"/api/games/{gid}/lobby/start", json={}, headers=h(alice))
    assert res.status_code == 200, res.text
    return client, gid, alice, bob


def view(client, gid, token):
    res = client.get(f"/api/games/{gid}/view", headers=h(token))
    assert res.status_code == 200, res.text
    return res.json()


def seat_of(client, gid, token):
    return view(client, gid, token)["viewer"]


def test_game_one_turn_order_comes_from_public_d20_rolls(table):
    client, gid, alice, bob = table
    night = view(client, gid, bob)["game"]["night"]
    assert night["number"] == 1 and night["order_source"] == "d20"
    first_round = night["rolls"][0]
    assert set(first_round) == {"p1", "p2"} and all(1 <= v <= 20 for v in first_round.values())
    # seats are in turn order: p1 rolled at least as high as p2 (ties were rerolled)
    final = {}
    for rnd in night["rolls"]:
        final.update(rnd)
    assert final["p1"] > final["p2"]
    # the private winner key never reaches a client
    assert "last_winner_key" not in str(view(client, gid, alice))


def test_agreed_ending_needs_every_remaining_player(table):
    client, gid, alice, bob = table
    a, b = seat_of(client, gid, alice), seat_of(client, gid, bob)
    res = client.post(f"/api/games/{gid}/night/propose", json={"result_type": "single", "winners": [b]}, headers=h(alice))
    assert res.status_code == 200, res.text
    proposal = view(client, gid, bob)["game"]["night"]["proposal"]
    assert proposal["by"] == a and proposal["winners"] == [b] and proposal["agreed"] == [a]
    # a decline: the game continues and nothing is recorded
    assert client.post(f"/api/games/{gid}/night/answer", json={"agree": False}, headers=h(bob)).status_code == 200
    night = view(client, gid, bob)["game"]["night"]
    assert night["proposal"] is None and night["result"] is None
    assert client.get(f"/api/games/{gid}/result").json() is None
    # propose again; this time everyone agrees
    client.post(f"/api/games/{gid}/night/propose", json={"result_type": "single", "winners": [b]}, headers=h(alice))
    client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(bob))
    night = view(client, gid, bob)["game"]["night"]
    assert night["result"]["agreed"] is True and night["result"]["winners"] == [b]
    recorded = client.get(f"/api/games/{gid}/result").json()
    assert recorded["winners"] == ["Bob"] and recorded["notes"].startswith("Agreed result")
    # the log says the players agreed; it never pretends the engine decided
    log = str(view(client, gid, bob)["log"])
    assert "agreed by the players" in log


def test_spectators_and_bad_results_cannot_propose(table):
    client, gid, alice, bob = table
    assert client.post(f"/api/games/{gid}/night/propose", json={"result_type": "single", "winners": []},
                       headers=h(alice)).status_code == 422
    assert client.post(f"/api/games/{gid}/night/propose", json={"result_type": "draw"}).status_code == 403
    assert client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(bob)).status_code == 409


def _finish(client, gid, alice, bob, winner_token):
    w = seat_of(client, gid, winner_token)
    client.post(f"/api/games/{gid}/night/propose", json={"result_type": "single", "winners": [w]}, headers=h(alice))
    client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(bob))
    return w


def test_all_rematch_starts_a_fresh_game_and_the_winner_goes_last(table):
    client, gid, alice, bob = table
    old = client.app.state.services.hub.get(gid).session.state
    old_cards = set(old.cards)
    client.post(f"/api/games/{gid}/actions", json={"action": {"type": "set_life", "player": "p1", "value": 7}}, headers=h(alice))
    _finish(client, gid, alice, bob, alice)  # Alice wins game 1
    assert client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(alice)).json()["decision"] is None
    votes = view(client, gid, bob)["game"]["night"]["votes"]
    assert list(votes.values()) == ["rematch"]
    res = client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(bob))
    assert res.json()["decision"] == "rematch"
    v = view(client, gid, alice)
    night = v["game"]["night"]
    assert night["number"] == 2 and night["order_source"] == "winner_last" and night["result"] is None
    # Alice won, so she now sits last in turn order; the same tokens still reach the same people
    assert v["viewer"] == "p2" and seat_of(client, gid, bob) == "p1"
    assert night["previous_winner"] == "p2"
    state = client.app.state.services.hub.get(gid).session.state
    assert state.players["p2"].name == "Alice" and state.players["p2"].life == 40  # fresh life
    assert not old_cards & set(state.cards)  # fresh game objects
    assert state.turn.number == 1 and state.turn.active_player == "p1"
    # game 2 records its own result; game 1's stays in pod stats
    _finish(client, gid, alice, bob, bob)
    assert client.get(f"/api/games/{gid}/result").json()["winners"] == ["Bob"]
    stats = client.app.state.services.stats
    assert stats.for_game(gid)["winners"] == ["Alice"] and stats.for_game(f"{gid}#2")["winners"] == ["Bob"]


def test_any_lobby_vote_returns_the_pod_to_the_lobby_with_decks_kept(table):
    client, gid, alice, bob = table
    _finish(client, gid, alice, bob, bob)
    res = client.post(f"/api/games/{gid}/night/vote", json={"choice": "lobby"}, headers=h(alice))
    assert res.json()["decision"] == "lobby"
    lobby = lobby_of(client, gid, bob)
    assert lobby["phase"] == "lobby"
    seats = {s["name"]: s for s in lobby["seats"] if s["claimed"]}
    assert set(seats) == {"Alice", "Bob"}
    assert seats["Bob"]["deck"]["commanders"] == ["Krenko, Mob Boss"] and not seats["Bob"]["ready"]
    # Bob changes his deck in the lobby, then the next game puts last game's winner (Bob) last
    bob_seat = next(s["id"] for s in lobby["seats"] if s["name"] == "Bob")
    assert client.post(f"/api/games/{gid}/lobby/deck", json={"text": ALICE_DECK, "name": "Copy"}, headers=h(bob)).status_code == 200
    for tok in (alice, bob):
        client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(tok))
    assert client.post(f"/api/games/{gid}/lobby/start", json={}, headers=h(alice)).status_code == 200
    night = view(client, gid, bob)["game"]["night"]
    assert night["number"] == 2 and night["order_source"] == "winner_last"
    assert seat_of(client, gid, bob) == "p2" and bob_seat in ("p1", "p2")
    state = client.app.state.services.hub.get(gid).session.state
    assert state.players["p2"].deck_name == "Copy"


def test_host_settles_a_hanging_vote(table):
    client, gid, alice, bob = table
    _finish(client, gid, alice, bob, alice)
    client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(alice))
    # Bob never answers; only the host may force it
    assert client.post(f"/api/games/{gid}/night/vote", json={"choice": "lobby", "force": True}, headers=h(bob)).status_code == 403
    res = client.post(f"/api/games/{gid}/night/vote", json={"choice": "lobby", "force": True}, headers=h(alice))
    assert res.json()["decision"] == "lobby"
    assert lobby_of(client, gid, alice)["phase"] == "lobby"


def test_draw_rerolls_the_order(table):
    client, gid, alice, bob = table
    client.post(f"/api/games/{gid}/night/propose", json={"result_type": "draw"}, headers=h(alice))
    client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(bob))
    client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(alice))
    client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(bob))
    night = view(client, gid, alice)["game"]["night"]
    assert night["number"] == 2 and night["order_source"] == "d20" and night["rolls"]


def test_hot_seat_rematch_and_no_lobby(client):
    decks = []
    for text in (ALICE_DECK, BOB_DECK):
        decks.append(client.post("/api/decks", json={"text": text}).json()["id"])
    res = client.post("/api/games", json={"name": "Home", "mode": "local", "players": [
        {"name": n, "deck_id": d} for n, d in zip(("Alice", "Bob"), decks, strict=True)]})
    gid = res.json()["game"]["id"]
    assert client.post(f"/api/games/{gid}/result", json={"result_type": "single", "winners": ["p1"]}).status_code == 201
    assert client.post(f"/api/games/{gid}/night/vote", json={"choice": "lobby", "as_player": "p1"}).status_code == 409
    res = client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch", "as_player": "p1"})
    assert res.json()["decision"] == "rematch"
    state = client.app.state.services.hub.get(gid).session.state
    assert [state.players[p].name for p in state.seat_order] == ["Bob", "Alice"]


def test_order_permutations_cover_every_tie_shape():
    # every way four players can roll 1-2 settles into a strict order with no duplicates
    for values in itertools.product((1, 2), repeat=4):
        seq = list(values) + [((i * 7) % 20) + 1 for i in range(40)]
        order, _ = roll_order(["A", "B", "C", "D"], scripted(seq))
        assert sorted(order) == ["A", "B", "C", "D"]


def test_night_survives_a_host_restart(table):
    client, gid, alice, bob = table
    _finish(client, gid, alice, bob, alice)
    hub = client.app.state.services.hub
    room = hub.get(gid)
    meta = hub.meta(room)
    restored = Night.from_meta(meta["night"])
    assert restored.result == room.night.result and restored.history == room.night.history
    assert restored.last_winner_key == room.seats[restored.result["winners"][0]].token


def test_own_deck_is_only_ever_the_askers(table):
    client, gid, alice, bob = table
    mine = client.get(f"/api/games/{gid}/night/deck", headers=h(bob)).json()
    names = {c["name"] for c in mine["cards"]}
    assert "Krenko, Mob Boss" in names and "Atraxa, Praetors' Voice" not in names
    # no token: no deck (spectators and strangers get nothing)
    assert client.get(f"/api/games/{gid}/night/deck").status_code == 403


def test_nudge_reaches_only_the_player_the_game_waits_on_and_is_rate_limited(table):
    client, gid, alice, bob = table
    state = client.app.state.services.hub.get(gid).session.state
    waiting = state.turn.active_player
    nudger = bob if seat_of(client, gid, alice) == waiting else alice
    res = client.post(f"/api/games/{gid}/night/signal", json={"kind": "nudge"}, headers=h(nudger))
    assert res.status_code == 200 and res.json()["to"] == waiting
    assert client.post(f"/api/games/{gid}/night/signal", json={"kind": "nudge"}, headers=h(nudger)).status_code == 429
    other = alice if nudger == bob else bob
    assert client.post(f"/api/games/{gid}/night/signal", json={"kind": "nudge"}, headers=h(other)).status_code == 409


def test_reactions_are_for_spectators_and_players_who_are_out(table):
    client, gid, alice, bob = table
    assert client.post(f"/api/games/{gid}/night/signal", json={"kind": "react", "emoji": "👍"}, headers=h(alice)).status_code == 403
    # emotes (fixed table talk) are for everyone at the table, players still in the game too; nothing else is free text
    assert client.post(f"/api/games/{gid}/night/signal", json={"kind": "react", "emoji": "Nice!"}, headers=h(alice)).status_code == 200
    assert client.post(f"/api/games/{gid}/night/signal", json={"kind": "react", "emoji": "GG"}, headers=h(alice)).status_code == 429
    assert client.post(f"/api/games/{gid}/night/signal", json={"kind": "react", "emoji": "Hello"}, headers=h(alice)).status_code == 422
    code = client.get(f"/api/games/{gid}").json()["code"]
    spectator = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    assert client.post(f"/api/games/{gid}/night/signal", json={"kind": "react", "emoji": "🔥"}, headers=h(spectator)).status_code == 200
    assert client.post(f"/api/games/{gid}/night/signal", json={"kind": "react", "emoji": "🔥"}, headers=h(spectator)).status_code == 429
    assert client.post(f"/api/games/{gid}/night/signal", json={"kind": "react", "emoji": "<script>"}, headers=h(spectator)).status_code == 422


def test_pings_point_at_public_cards_and_spots_never_at_hidden_ones(table):
    client, gid, alice, bob = table
    me, other = seat_of(client, gid, alice), seat_of(client, gid, bob)
    mine = view(client, gid, alice)
    commander = mine["zones"][f"{me}:command"][0]["id"] if isinstance(mine["zones"][f"{me}:command"][0], dict) else mine["zones"][f"{me}:command"][0]
    hand = mine["zones"][f"{me}:hand"]
    library_top = client.app.state.services.hub.get(gid).session.state.zones[f"{me}:library"][0]
    signal = f"/api/games/{gid}/night/signal"
    with client.websocket_connect(f"/ws/games/{gid}?token={bob}") as ws:
        ws.receive_json()
        # hidden cards (my hand, my library) can't be pointed at: their ids would leak
        assert client.post(signal, json={"kind": "ping", "card": hand[0]}, headers=h(alice)).status_code == 404
        assert client.post(signal, json={"kind": "ping", "card": library_top}, headers=h(alice)).status_code == 404
        assert client.post(signal, json={"kind": "ping", "card": commander}, headers=h(alice)).status_code == 200
        got = ws.receive_json()
        while got["type"] != "signal":
            got = ws.receive_json()
        assert got == {"type": "signal", "kind": "ping", "from": me, "from_name": "Alice", "card": commander}
        assert client.post(signal, json={"kind": "ping", "card": commander}, headers=h(alice)).status_code == 429
    time.sleep(0.65)
    spot = client.post(signal, json={"kind": "ping", "player": other, "x": 420.3333, "y": 210}, headers=h(alice))
    assert spot.status_code == 200
    assert client.post(signal, json={"kind": "ping"}, headers=h(bob)).status_code == 422
    assert client.post(signal, json={"kind": "ping", "player": other, "x": 99999, "y": 0}, headers=h(bob)).status_code == 422
    code = client.get(f"/api/games/{gid}").json()["code"]
    spectator = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    assert client.post(signal, json={"kind": "ping", "card": commander}, headers=h(spectator)).status_code == 403


def test_the_lobby_recaps_tonights_games(table):
    client, gid, alice, bob = table
    _finish(client, gid, alice, bob, bob)
    client.post(f"/api/games/{gid}/night/vote", json={"choice": "lobby"}, headers=h(alice))
    recap = lobby_of(client, gid, alice)["night"]
    assert len(recap) == 1 and recap[0]["winner_names"] == ["Bob"] and recap[0]["agreed"] is True
    assert recap[0]["commanders"]["Bob"] == ["Krenko, Mob Boss"] and recap[0]["minutes"] >= 0
