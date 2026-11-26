"""Spectator side activities (docs/SPECTATOR_ACTIVITIES_MILESTONE.md): the live summary for the practice table's corner,
the damage sandbox, fake-point predictions, the next-game deck queue and the host's switch for reactions.

All of it stays outside the live match (no action, log line, history step, revision or save) and reads only the public
(spectator) view: being out of the game, or watching it, grants nothing hidden."""

from __future__ import annotations

import json

import pytest

from app.game.session import GameSession
from app.game.visibility import OMNISCIENT, SPECTATOR
from app.multiplayer.night import Night
from app.multiplayer.sandbox import Scenario, simulate
from tests.test_elimination_hub import P3_DECK, act, concede, h, room_of, view
from tests.test_elimination_hub import table as table  # noqa: F401 - the shared fixture
from tests.test_lobby import ALICE_DECK, BOB_DECK, create_lobby, lobby_of
from tests.test_protocol_privacy import P1_DECK, P2_DECK, fingerprints


def frozen(room) -> tuple:
    """Everything about the live game an activity must never change."""
    s = room.session
    return (s.state.model_dump_json(), room.revision, len(s.notices), s.history.can_undo, len(s.state.log))


def hidden_cards(room, owners=("p1", "p2")):
    state = room.session.state
    return [state.cards[c] for pid in owners for z in ("hand", "library") for c in state.zones[f"{pid}:{z}"]]


def assert_no_hidden(payload, cards, repo) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    for card in cards:
        for token in fingerprints(card, repo):
            if token != card.id:  # a public placeholder never names the card; its server id is checked separately
                assert token not in text, f"{token!r} of hidden {card.name} leaked"
        assert f'"{card.id}"' not in text, f"id of hidden {card.name} leaked"


@pytest.fixture()
def seen_viewers(monkeypatch):
    """Every viewer a live view is built for while the test runs."""
    seen: list[str] = []
    real = GameSession.view

    def spy(self, viewer, **kw):
        seen.append(viewer)
        return real(self, viewer, **kw)

    monkeypatch.setattr(GameSession, "view", spy)
    return seen


# --------------------------------------------------------------------------- the live summary (Watch + PiP)


def test_the_live_summary_is_public_and_the_same_for_everyone(table, seen_viewers):
    client, gid, t = table
    repo = client.app.state.services.cards
    room = room_of(client, gid)
    concede(client, gid, t["carol"])
    act(client, gid, t["alice"], {"type": "look_top", "count": 3})  # a private look: Alice's alone
    act(client, gid, t["alice"], {"type": "set_life", "player": "p2", "value": 31})
    before = frozen(room)
    seen_viewers.clear()
    got = {who: client.get(f"/api/games/{gid}/watch", headers=h(t[who])) for who in ("carol", "spec", "alice")}
    assert all(r.status_code == 200 for r in got.values())
    bodies = {who: r.json() for who, r in got.items()}
    assert bodies["carol"] == bodies["spec"] == bodies["alice"]  # nobody's summary knows more
    summary = bodies["carol"]
    assert set(seen_viewers) == {SPECTATOR} and OMNISCIENT not in seen_viewers
    players = {p["name"]: p for p in summary["players"]}
    assert players["Bob"]["life"] == 31 and players["Carol"]["out"] == "conceded" and players["Alice"]["out"] is None
    assert players["Alice"]["hand"] == 8 and summary["stack"] == {"count": 0, "top": None}  # (S7: 7 and her first draw, 103.8c)
    assert summary["active_name"] and summary["turn"] == 1 and summary["log"]
    assert_no_hidden(summary, hidden_cards(room), repo)
    assert frozen(room) == before  # reading it changes nothing


def test_the_live_summary_is_for_the_table_only(table):
    client, gid, t = table
    assert client.get(f"/api/games/{gid}/watch").status_code == 403
    assert client.get(f"/api/games/{gid}/watch", headers=h("not-a-token")).status_code == 403
    concede(client, gid, t["carol"])
    practice = client.post(f"/api/games/{gid}/practice", json={}, headers=h(t["carol"])).json()
    assert client.get(f"/api/games/{practice['game_id']}/watch", headers=h(practice["token"])).status_code == 409


# --------------------------------------------------------------------------- damage sandbox


def _to_battlefield(client, gid, token, room, pid, name, **extra):
    state = room.session.state
    cid = next(c for c in state.zones[f"{pid}:library"] + state.zones[f"{pid}:hand"] if state.cards[c].name == name)
    act(client, gid, token, {"type": "move", "card_ids": [cid], "to": {"zone": "battlefield"}, "x": 100, "y": 100, **extra})
    return cid


@pytest.fixture()
def manual_table(client):
    """Alice, Bob and Carol at a LAN table without rules automation (the sandbox reads printed stats plus counters)."""
    decks = [client.post("/api/decks", json={"text": t}).json()["id"] for t in (P3_DECK, P2_DECK, P1_DECK)]
    game = client.post("/api/games", json={"mode": "lan", "shuffle": True, "name": "Friday", "players": [
        {"name": n, "deck_id": d} for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)]})
    assert game.status_code == 201, game.text
    gid, code = game.json()["game"]["id"], game.json()["game"]["code"]
    tokens = {"alice": game.json()["seat"]["token"]}
    tokens["bob"] = client.post("/api/join", json={"code": code}).json()["token"]
    tokens["carol"] = client.post("/api/join", json={"code": code}).json()["token"]
    tokens["spec"] = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    for who in ("alice", "bob", "carol"):
        act(client, gid, tokens[who], {"type": "draw", "count": 5})
    return client, gid, tokens


def test_the_sandbox_board_is_the_public_board_and_nothing_more(manual_table, seen_viewers):
    client, gid, t = manual_table
    repo = client.app.state.services.cards
    room = room_of(client, gid)
    bears = _to_battlefield(client, gid, t["alice"], room, "p1", "Grizzly Bears")
    act(client, gid, t["alice"], {"type": "counter", "card_ids": [bears], "kind": "+1/+1", "delta": 2})
    _to_battlefield(client, gid, t["bob"], room, "p2", "Lightning Bolt", face_down=True)  # face down: nobody else knows
    state = room.session.state
    elves = next(c for c in state.zones["p2:battlefield"] if state.cards[c].face_down)  # (a new id once face down, 406.3)
    act(client, gid, t["bob"], {"type": "set_life", "player": "p2", "value": 12})
    before = frozen(room)
    seen_viewers.clear()
    res = client.get(f"/api/games/{gid}/sandbox/board", headers=h(t["spec"]))
    assert res.status_code == 200, res.text
    board = res.json()
    assert set(seen_viewers) == {SPECTATOR}
    by_id = {c["id"]: c for c in board["creatures"]}
    assert by_id[bears]["name"] == "Grizzly Bears" and (by_id[bears]["power"], by_id[bears]["toughness"]) == (4, 4)
    assert by_id[bears]["controller"] == "p1"
    hidden = by_id[elves]
    assert (hidden["name"], hidden["power"], hidden["toughness"], hidden["keywords"]) == ("Face-down creature", 2, 2, [])
    assert {p["name"]: p["life"] for p in board["players"]}["Bob"] == 12
    # the face-down creature's identity, every hand and every library stay hidden
    face_down = room.session.state.cards[elves]
    text = json.dumps(board, ensure_ascii=False)
    for token in fingerprints(face_down, repo):
        if token != face_down.id:
            assert token not in text
    assert_no_hidden(board, hidden_cards(room, ("p1", "p2", "p3")), repo)
    # Bob, who controls it, gets the same public board: the sandbox never uses a player's own view
    assert client.get(f"/api/games/{gid}/sandbox/board", headers=h(t["bob"])).json() == board
    assert frozen(room) == before


def test_the_sandbox_board_reads_derived_stats_from_the_public_view(table):
    client, gid, t = table
    room = room_of(client, gid)
    bears = _to_battlefield(client, gid, t["carol"], room, "p3", "Grizzly Bears")
    act(client, gid, t["carol"], {"type": "counter", "card_ids": [bears], "kind": "+1/+1", "delta": 1})
    board = client.get(f"/api/games/{gid}/sandbox/board", headers=h(t["spec"])).json()
    bear = next(c for c in board["creatures"] if c["id"] == bears)
    stats = view(client, gid, t["spec"])["rules"]["stats"].get(bears, {})
    assert [bear["power"], bear["toughness"]] == stats.get("pt", [2, 2]) == [3, 3]


def test_a_what_if_combat_uses_the_engines_damage_and_never_touches_the_game(manual_table):
    client, gid, t = manual_table
    room = room_of(client, gid)
    before = frozen(room)
    scenario = {
        "players": [{"id": "p1", "name": "Alice", "life": 10}, {"id": "p2", "name": "Bob", "life": 5, "commander_damage": {"p1:0": 18}}],
        "creatures": [
            {"id": "a1", "name": "Big", "controller": "p1", "power": 6, "toughness": 6, "keywords": ["trample", "lifelink"],
             "commander": "p1:0", "attacking": "p2"},
            {"id": "a2", "name": "Striker", "controller": "p1", "power": 2, "toughness": 2, "keywords": ["double strike"], "attacking": "p2"},
            {"id": "b1", "name": "Wall", "controller": "p2", "power": 0, "toughness": 4, "blocking": "a1"},
            {"id": "b2", "name": "Bear", "controller": "p2", "power": 2, "toughness": 2, "blocking": "a2"},
        ],
    }
    res = client.post(f"/api/games/{gid}/sandbox/combat", json=scenario, headers=h(t["spec"]))
    assert res.status_code == 200, res.text
    out = res.json()
    # first strike: the double striker kills the Bear; regular damage: lethal to the Wall, the rest tramples over (702.19b)
    assert [r["round"] for r in out["rounds"]] == ["first", "second"]
    assert out["rounds"][0]["dealt"] == [{"source": "a2", "target": "b2", "amount": 2}]
    assert out["rounds"][1]["dealt"] == [{"source": "a1", "target": "b1", "amount": 4}, {"source": "a1", "target": "p2", "amount": 2}]
    players = {p["id"]: p for p in out["players"]}
    assert players["p1"]["life"] == 16  # lifelink: all 6
    assert players["p2"]["life"] == 3 and players["p2"]["commander_damage"] == {"p1:0": 20} and players["p2"]["loses"] == []
    died = {c["id"]: c["died"] for c in out["creatures"]}
    assert died == {"a1": None, "a2": None, "b1": "lethal damage", "b2": "lethal damage"}
    assert frozen(room) == before
    # a scenario that doesn't add up is refused, and only the table may use it
    bad = {**scenario, "creatures": [{**scenario["creatures"][2], "blocking": "nobody"}]}
    assert client.post(f"/api/games/{gid}/sandbox/combat", json=bad, headers=h(t["spec"])).status_code == 422
    assert client.post(f"/api/games/{gid}/sandbox/combat", json=scenario).status_code == 403


def test_sandbox_lethal_checks():
    def run(creatures, **player):
        out = simulate(Scenario.model_validate({"players": [{"id": "p1"}, {"id": "p2", **player}], "creatures": creatures}))
        return {p["id"]: p for p in out["players"]}["p2"], {c["id"]: c["died"] for c in out["creatures"]}

    # 21 commander damage from one commander (704.6c / 903.10a)
    p2, _ = run([{"id": "c", "controller": "p1", "power": 5, "toughness": 5, "commander": "p1:0", "attacking": "p2"}],
                commander_damage={"p1:0": 16})
    assert p2["loses"] == ["21 or more commander damage (p1:0)"] and p2["life"] == 35
    # infect: poison, not life (702.90b); 10 poison loses (704.5c)
    p2, _ = run([{"id": "i", "controller": "p1", "power": 3, "toughness": 1, "keywords": ["infect"], "attacking": "p2"}], poison=7)
    assert (p2["poison"], p2["life"], p2["loses"]) == (10, 40, ["10 or more poison counters"])
    # deathtouch kills the blocker; indestructible shrugs off lethal damage; deathtouch + trample needs only 1 per blocker
    p2, died = run([
        {"id": "dt", "controller": "p1", "power": 5, "toughness": 1, "keywords": ["deathtouch", "trample"], "attacking": "p2"},
        {"id": "big", "controller": "p2", "power": 0, "toughness": 9, "blocking": "dt"},
        {"id": "ind", "controller": "p1", "power": 1, "toughness": 1, "keywords": ["indestructible"], "attacking": "p2"},
        {"id": "b", "controller": "p2", "power": 4, "toughness": 4, "blocking": "ind"},
    ], life=4)
    assert died == {"dt": None, "big": "deathtouch", "ind": None, "b": None}
    assert (p2["life"], p2["loses"]) == (0, ["0 or less life"])


# --------------------------------------------------------------------------- predictions


def predictions(client, gid, token):
    res = client.get(f"/api/games/{gid}/predictions", headers=h(token))
    assert res.status_code == 200, res.text
    return res.json()


def predict(client, gid, token, market, choice, stake, status=200, **extra):
    res = client.post(f"/api/games/{gid}/predictions", json={"market": market, "choice": choice, "stake": stake, **extra},
                      headers=h(token))
    assert res.status_code == status, res.text
    return res.json()


def test_predictions_are_for_people_out_of_the_game_hidden_then_revealed_and_scored(table):
    client, gid, t = table
    room = room_of(client, gid)
    services = client.app.state.services
    assert predict(client, gid, t["alice"], "winner", "p1", 50, status=403)  # still in the game
    assert predict(client, gid, t["carol"], "winner", "p1", 50, status=403)  # Carol is still in, too
    concede(client, gid, t["carol"])
    before = frozen(room)
    predict(client, gid, t["carol"], "winner", "p1", 50)
    predict(client, gid, t["carol"], "next_out", "p2", 25)
    predict(client, gid, t["spec"], "winner", "p2", 100, name="Dana")
    predict(client, gid, t["spec"], "next_out", "p1", 10, name="Dana")
    predict(client, gid, t["spec"], "winner", "p3", 10, status=422)  # Carol is out already
    predict(client, gid, t["spec"], "winner", "p2", 7, status=422)  # fixed stakes only
    predict(client, gid, t["spec"], "next_out", "p1", 500, status=422)  # more than Dana has left to stake
    assert frozen(room) == before  # no action, log line, history step or revision

    # picks stay hidden until the game ends: each person sees their own, the players see nothing
    mine = predictions(client, gid, t["spec"])
    assert mine["can_predict"] and mine["available"] == 390 and set(mine["picks"]) == {"winner", "next_out"}
    assert mine["picks"]["winner"] == {"choice": "p2", "choice_name": "Bob", "stake": 100, "outcome": None}
    assert "Carol" not in json.dumps(mine["picks"]) and mine["recap"] is None
    alice = predictions(client, gid, t["alice"])
    assert alice["can_predict"] is False and alice["picks"] == {}
    for who in ("alice", "bob", "spec"):
        assert "predictions" not in view(client, gid, t[who])["game"]

    # Bob goes out next, then Alice confirms the rules result (the last player in the game wins)
    concede(client, gid, t["bob"])
    assert client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(t["alice"])).status_code == 200
    assert room.night.result and room.night.result["winners"] == ["p1"]

    recap = view(client, gid, t["bob"])["game"]["predictions"]  # revealed to the whole table
    picks = {(r["name"], r["market"]): (r["choice_name"], r["stake"], r["outcome"]) for r in recap["picks"]}
    assert picks == {("Carol", "winner"): ("Alice", 50, "won"), ("Carol", "next_out"): ("Bob", 25, "won"),
                     ("Dana", "winner"): ("Bob", 100, "lost"), ("Dana", "next_out"): ("Alice", 10, "lost")}
    assert [(s["name"], s["balance"], s["correct"]) for s in recap["standings"]] == [("Carol", 575, 2), ("Dana", 390, 0)]
    assert predictions(client, gid, t["spec"])["recap"] == recap
    predict(client, gid, t["spec"], "winner", "p1", 10, status=409)  # settled
    # scored once, however often the table is looked at
    view(client, gid, t["spec"])
    assert [s["balance"] for s in predictions(client, gid, t["carol"])["standings"]] == [575, 390]
    # memory only: never in the room's recovery record or a save
    assert "Dana" not in json.dumps(services.hub.meta(room))
    assert "Dana" not in room.session.state.model_dump_json()


def test_a_prediction_can_be_changed_or_withdrawn_and_a_draw_voids_it(table):
    client, gid, t = table
    room = room_of(client, gid)
    concede(client, gid, t["carol"])
    predict(client, gid, t["spec"], "winner", "p1", 100)
    predict(client, gid, t["spec"], "winner", "p2", 25)  # changed: one pick per market
    assert predictions(client, gid, t["spec"])["picks"]["winner"]["choice"] == "p2"
    res = client.delete(f"/api/games/{gid}/predictions/winner", headers=h(t["spec"]))
    assert res.status_code == 200 and res.json()["picks"] == {}
    predict(client, gid, t["spec"], "winner", "p2", 25)
    predict(client, gid, t["carol"], "next_out", "p1", 50)
    for tok in ("alice", "bob"):  # an agreed draw: nobody else goes out and nobody wins
        if room.night.proposal is None:
            assert client.post(f"/api/games/{gid}/night/propose", json={"result_type": "draw", "winners": []}, headers=h(t[tok])).status_code == 200
        else:
            assert client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(t[tok])).status_code == 200
    recap = predictions(client, gid, t["spec"])["recap"]
    assert {r["outcome"] for r in recap["picks"]} == {"void"}
    assert {s["balance"] for s in recap["standings"]} == {500}


# --------------------------------------------------------------------------- next-game deck queue


@pytest.fixture()
def pod(client):
    """Alice, Bob and Carol start a game from the lobby, with a spectator watching."""
    gid, code, alice = create_lobby(client, automation="full", mulligan_rule="none")
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    carol = client.post("/api/join", json={"code": code, "name": "Carol"}).json()["token"]
    for tok, deck in ((alice, ALICE_DECK), (bob, BOB_DECK), (carol, P3_DECK)):
        assert client.post(f"/api/games/{gid}/lobby/deck", json={"text": deck}, headers=h(tok)).status_code == 200
        client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(tok))
    assert client.post(f"/api/games/{gid}/lobby/start", json={}, headers=h(alice)).status_code == 200
    spec = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    return client, gid, code, {"alice": alice, "bob": bob, "carol": carol, "spec": spec}


def seat_of(client, gid, token):
    return view(client, gid, token)["viewer"]


def end_game(client, gid, t, winner_token):
    """The players still in agree on a winner."""
    room = room_of(client, gid)
    left = [tok for tok in (t["alice"], t["bob"], t["carol"]) if seat_of(client, gid, tok) not in room.session.state.rules.conceded]
    winner = seat_of(client, gid, winner_token)
    assert client.post(f"/api/games/{gid}/night/propose", json={"result_type": "single", "winners": [winner]},
                       headers=h(left[0])).status_code == 200
    for tok in left[1:]:
        client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(tok))
    assert room.night.result is not None


def test_queued_decks_wait_for_the_lobby_and_a_rematch_ignores_them(pod):
    client, gid, code, t = pod
    room = room_of(client, gid)
    carol_seat = seat_of(client, gid, t["carol"])
    queue = lambda tok, body: client.post(f"/api/games/{gid}/next-deck", json=body, headers=h(tok))  # noqa: E731
    assert queue(t["carol"], {"text": BOB_DECK, "name": "Goblins v2"}).status_code == 403  # still playing
    concede(client, gid, t["carol"])
    assert carol_seat in room.session.state.rules.conceded
    before = (frozen(room), {k: v.deck_name for k, v in room.night.setups.items()})
    res = queue(t["carol"], {"text": BOB_DECK, "name": "Goblins v2"})
    assert res.status_code == 200, res.text
    assert res.json()["queued"]["name"] == "Goblins v2" and res.json()["queued"]["commanders"] == ["Krenko, Mob Boss"]
    assert queue(t["spec"], {"text": ALICE_DECK, "name": "Watcher's deck"}).status_code == 200
    assert queue(t["alice"], {"text": BOB_DECK}).status_code == 403  # Alice is still in the game
    assert queue(t["spec"], {"archidekt": "https://archidekt.com/decks/1"}).status_code == 422
    assert client.get(f"/api/games/{gid}/next-deck", headers=h(t["carol"])).json()["queued"]["name"] == "Goblins v2"
    assert client.get(f"/api/games/{gid}/next-deck", headers=h(t["alice"])).json()["queued"] is None  # only your own
    # the current game and its decks don't change
    assert (frozen(room), {k: v.deck_name for k, v in room.night.setups.items()}) == before
    assert "Goblins v2" not in json.dumps(view(client, gid, t["bob"]))

    # a same-decks rematch: everyone keeps the deck they had; the queue waits
    end_game(client, gid, t, t["alice"])
    for tok in (t["alice"], t["bob"], t["carol"]):
        client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(tok))
    assert room.night.number == 2
    carol_now = seat_of(client, gid, t["carol"])
    assert room.night.setups[carol_now].deck_name != "Goblins v2"

    # back to the lobby: Carol's queued deck is proposed (not ready), everyone else keeps theirs
    end_game(client, gid, t, t["bob"])
    assert client.post(f"/api/games/{gid}/night/vote", json={"choice": "lobby"}, headers=h(t["alice"])).status_code == 200
    lobby = lobby_of(client, gid, t["carol"])
    mine = next(s for s in lobby["seats"] if s["id"] == lobby["viewer"])
    assert mine["deck"]["name"] == "Goblins v2" and mine["ready"] is False and mine["queued"] is True
    others = lobby_of(client, gid, t["bob"])
    assert all("queued" not in s for s in others["seats"])
    assert {s["name"]: s["deck"]["name"] for s in others["seats"] if s["claimed"] and s["name"] != "Carol"}["Bob"] != "Goblins v2"
    assert client.get(f"/api/games/{gid}/next-deck", headers=h(t["carol"])).json()["queued"] is None  # used up

    # she can still change it: the queued mark goes with it
    assert client.post(f"/api/games/{gid}/lobby/deck", json={"text": P3_DECK}, headers=h(t["carol"])).status_code == 200
    mine = next(s for s in lobby_of(client, gid, t["carol"])["seats"] if s["id"] == lobby["viewer"])
    assert "queued" not in mine

    # the spectator takes a seat in the lobby and brings the deck they queued while watching
    res = client.post("/api/join", json={"code": code, "name": "Dana"}, headers=h(t["spec"]))
    assert res.status_code == 200, res.text
    dana = lobby_of(client, gid, res.json()["token"])
    seat = next(s for s in dana["seats"] if s["id"] == dana["viewer"])
    assert seat["deck"]["name"] == "Watcher's deck" and seat["queued"] is True and seat["ready"] is False


def test_keeping_the_current_deck_forgets_the_queued_one(pod):
    client, gid, _, t = pod
    room = room_of(client, gid)
    assert client.post(f"/api/games/{gid}/next-deck", json={"text": BOB_DECK}, headers=h(t["spec"])).status_code == 200
    assert client.delete(f"/api/games/{gid}/next-deck", headers=h(t["spec"])).status_code == 204
    assert room.night.queued == {}
    assert client.get(f"/api/games/{gid}/next-deck", headers=h("nope")).status_code == 403


# --------------------------------------------------------------------------- the host's switch for reactions


def test_the_host_can_turn_reactions_off_for_the_whole_table(table):
    client, gid, t = table
    room = room_of(client, gid)
    services = client.app.state.services
    react = lambda: client.post(f"/api/games/{gid}/night/signal", json={"kind": "react", "emoji": "🔥"}, headers=h(t["spec"]))  # noqa: E731
    assert view(client, gid, t["spec"])["game"]["night"]["reactions"] is True  # on by default
    assert client.post(f"/api/games/{gid}/night/reactions", json={"on": False}, headers=h(t["bob"])).status_code == 403
    assert client.post(f"/api/games/{gid}/night/reactions", json={"on": False}, headers=h(t["spec"])).status_code == 403
    state_before = room.session.state.model_dump_json()
    res = client.post(f"/api/games/{gid}/night/reactions", json={"on": False}, headers=h(t["alice"]))  # Alice hosts
    assert res.status_code == 200 and res.json() == {"reactions": False}
    assert view(client, gid, t["spec"])["game"]["night"]["reactions"] is False
    assert react().status_code == 409
    assert room.session.state.model_dump_json() == state_before  # a table setting, not part of the game
    assert services.hub.meta(room)["night"]["reactions"] is False  # survives a host restart
    assert Night.from_meta(services.hub.meta(room)["night"]).reactions is False
    assert Night.from_meta({"number": 2}).reactions is True  # an older record: on
    assert client.post(f"/api/games/{gid}/night/reactions", json={"on": True}, headers=h(t["alice"])).status_code == 200
    assert react().status_code == 200
