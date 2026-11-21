"""-- quick undo request (TABLETOP_QOL_MILESTONE #7) -- an undo that asks the table first (app/game/undo_requests.py).

At a LAN table, an undo the host's undo setting refuses can be requested instead, and an undo of an action that showed hidden
information or a random outcome asks under every setting. Every other seated player still in the game approves (one decline
ends it); the server then undoes it, attributed to the requester. Any change to the table cancels a request. Hot-seat tables
undo directly, as before."""

from __future__ import annotations

import json

import pytest

from app.game.actions import ACTION_ADAPTER
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.history import History
from app.game.session import GameSession
from app.game.state import GameState
from app.game.undo_requests import answer, ask, classify, request, shown
from tests.conftest import guest
from tests.game_helpers import act, deck, enable, make_session, zone
from tests.test_games_api import ATRAXA, KRENKO
from tests.test_rules_effects import build, draw_all, hand, mana, rules

REMOTE = guest()


def replay_matches(s: GameSession) -> None:
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def last(s: GameSession):
    return s.history.actions[s.history.cursor - 1]


def notices(s: GameSession) -> list[str]:
    return ["".join(p.t or "" for p in n.parts) for n in s.notices]


def three(cards) -> GameSession:
    lands = deck(cards, "Krenko, Mob Boss", [(10, "Mountain")])
    state = new_game([PlayerSetup(name, cards=lands) for name in ("Alice", "Bob", "Cleo")], name="Three", shuffle=False)
    return GameSession(state, cards=cards)


# ---------------------------------------------------------------------------- what an action showed


def test_table_tools_that_show_hidden_information_or_chance(cards):
    s = make_session(cards)

    def top(zone_name="library"):
        return [zone(s.state, "p1", zone_name)[0]]

    steps = [
        (lambda: {"type": "life", "delta": -1}, None),
        (lambda: {"type": "draw", "count": 2}, "draw"),
        (lambda: {"type": "move", "card_ids": top("hand"), "to": {"zone": "battlefield"}, "x": 100, "y": 100}, None),
        (lambda: {"type": "look_top", "count": 2}, "look"),
        (lambda: {"type": "end_view"}, None),
        (lambda: {"type": "reveal", "card_ids": top("hand")}, "reveal"),
        (lambda: {"type": "search_start", "zone": {"zone": "library"}}, "search"),
        (lambda: {"type": "search_end", "shuffle": True}, "random"),
        (lambda: {"type": "move", "card_ids": top(), "to": {"zone": "hand"}}, "draw"),  # dragging the top card into the hand
        (lambda: {"type": "move", "card_ids": top(), "to": {"zone": "graveyard"}}, "library"),
        (lambda: {"type": "mill", "count": 2}, "library"),
        (lambda: {"type": "shuffle"}, "random"),
        (lambda: {"type": "roll", "sides": 20}, "random"),
        (lambda: {"type": "coin"}, "random"),
        (lambda: {"type": "discard_random"}, "random"),
        (lambda: {"type": "tap", "card_ids": top("battlefield")}, None),
        (lambda: {"type": "chat", "text": "gg"}, None),
    ]
    for payload, kind in steps:
        sent = payload()
        act(s, "p1", **sent)
        assert (sent["type"], last(s).shown) == (sent["type"], kind)
    replay_matches(s)


def test_the_rules_engine_steps_and_choices(cards):
    """An intent is one history entry: what the rules compiled into it counts (the scry's look, the enters trigger's draw, the
    search's shuffle); casting a spell or playing a land that shows nothing stays plain."""
    s = build(cards)
    draw_all(s)
    act(s, "p1", type="play_land", card_id=hand(s, "p1", "Thornwood Falls").id)
    assert last(s).shown is None
    mana(s, G=2)
    act(s, "p1", type="cast_spell", card_id=hand(s, "p1", "Elvish Visionary").id)  # resolves; its enters trigger draws
    assert last(s).shown == "draw"
    myr = build(cards)
    draw_all(myr)
    mana(myr, C=3)
    act(myr, "p1", type="cast_spell", card_id=hand(myr, "p1", "Perilous Myr").id)
    assert last(myr).shown is None
    opt = build(cards)
    act(opt, "p1", type="draw", count=10)
    mana(opt, U=1)
    act(opt, "p1", type="cast_spell", card_id=hand(opt, "p1", "Opt").id)
    d = rules(opt).decision
    assert d.kind == "choose_cards" and last(opt).shown == "look"  # the scry offers the top card: Alice saw it
    act(opt, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert last(opt).shown == "draw"  # then Opt draws
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Rampant Growth"), (6, "Forest")])
    growth = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=alice)], shuffle=False)),
                         cards=cards)
    act(growth, "p1", type="pass_priority")
    act(growth, "p1", type="draw")
    mana(growth, G=2)
    act(growth, "p1", type="cast_spell", card_id=hand(growth, "p1", "Rampant Growth").id)
    d = rules(growth).decision
    assert d.kind == "choose_cards" and last(growth).shown == "search"  # the search shows Alice her lands
    act(growth, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    assert last(growth).shown == "random"  # then shuffles
    for t in (s, myr, opt, growth):
        replay_matches(t)


def test_a_search_that_finds_nothing_asks_the_same(cards):
    """Privacy by omission: what an action showed never depends on which cards a private choice offers, so the table can't
    tell from an undo whether a search found anything."""
    found = {}
    for lands in ("Forest", "Thornwood Falls"):  # basic lands to find, or none at all
        alice = deck(cards, "Krenko, Mob Boss", [(1, "Rampant Growth"), (6, lands)])
        s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=alice)], shuffle=False)),
                        cards=cards)
        act(s, "p1", type="pass_priority")
        act(s, "p1", type="draw")
        mana(s, G=2)
        act(s, "p1", type="cast_spell", card_id=hand(s, "p1", "Rampant Growth").id)
        found[lands] = (len(rules(s).decision.options), last(s).shown, ask(s, "p2", host=False, others=["p1"]))
        replay_matches(s)
    assert found["Forest"][0] > 0 and found["Thornwood Falls"][0] == 0
    assert found["Forest"][1:] == found["Thornwood Falls"][1:] == ("search", "This undo would take back a library search that players already saw.")


def test_older_actions_fall_back_to_their_steps():
    draw = ACTION_ADAPTER.validate_python({"type": "draw", "actor": "p1"})
    life = ACTION_ADAPTER.validate_python({"type": "life", "delta": 1, "actor": "p1"})
    assert (shown(draw), shown(life), shown(None)) == ("draw", None, None)



def test_drawing_on_the_servers_randomness_counts(cards):
    """A random pick the rules engine makes (Recorder: the action used the server's randomness) shows a random outcome."""
    s = make_session(cards)
    act(s, "p1", type="life", delta=1)
    assert classify(last(s), set(), s.state, True) == "random" and classify(last(s), set(), s.state, False) is None


# ---------------------------------------------------------------------------- the session


def test_default_policy_asks_before_undoing_a_draw_and_not_a_life_change(cards):
    s = make_session(cards)
    act(s, "p1", type="life", delta=-3)
    act(s, "p1", type="draw")
    with pytest.raises(ActionError, match="take back a draw that players already saw"):
        s.undo("p2", others=["p1"])
    with pytest.raises(ActionError, match="take back a draw"):
        s.undo("p1", others=["p2"])  # your own draw too: you saw the card
    s.undo("p1")  # at a hot-seat table (no one to ask: others=None) it undoes directly, as before
    assert len(zone(s.state, "p1", "hand")) == 0
    s.undo("p2", others=["p1"])  # a life change shows nothing: direct
    assert s.state.players["p1"].life == 40
    s.redo("p2")
    s.redo("p2")  # redo is never asked: it puts back the same recorded outcome
    assert len(zone(s.state, "p1", "hand")) == 1 and last(s).shown == "draw"
    s.undo("p1", others=[])  # nobody else in the game to ask: direct
    replay_matches(s)


def test_request_approved_by_everyone_is_undone_for_the_requester(cards):
    s = make_session(cards)
    act(s, "p1", type="draw")
    drawn = zone(s.state, "p1", "hand")[0]
    assert ask(s, "p2", host=False, others=["p1"]) == "This undo would take back a draw that players already saw."
    req = request(s, "p2", host=False, others=["p1"])
    assert req.public(s.state) == {"id": req.id, "by": "p2", "by_name": "Bob", "label": "draw", "shown": "draw",
                                   "why": "This undo would take back a draw that players already saw.",
                                   "voters": ["p1"], "approved": [], "waiting": ["p1"]}
    with pytest.raises(ActionError, match="already waiting"):
        request(s, "p1", host=False, others=["p2"])
    with pytest.raises(ActionError, match="Only the other players"):
        answer(s, "p2", "approve")
    undone = answer(s, "p1", "approve")
    assert undone is not None and undone.type == "draw" and s.undo_request is None
    assert zone(s.state, "p1", "hand") == [] and drawn in zone(s.state, "p1", "library")
    assert notices(s)[-2:] == ["Bob asks the table to undo: draw.", "Bob undid: draw (with the table's approval)"]
    assert s.notices[-1].actor == "p2"
    replay_matches(s)


def test_every_voter_must_approve_and_one_decline_ends_it(cards):
    s = three(cards)
    act(s, "p1", type="draw")
    request(s, "p1", host=False, others=["p2", "p3"])
    assert answer(s, "p2", "approve") is None and s.undo_request is not None
    assert s.undo_request.public(s.state)["waiting"] == ["p3"]
    assert answer(s, "p3", "decline") is None and s.undo_request is None
    assert len(zone(s.state, "p1", "hand")) == 1  # nothing undone
    assert notices(s)[-1] == "Cleo declined Alice's undo request (draw). The game goes on."
    with pytest.raises(ActionError, match="No undo request"):
        answer(s, "p2", "approve")


def test_the_requester_withdraws(cards):
    s = make_session(cards)
    act(s, "p1", type="draw")
    request(s, "p2", host=False, others=["p1"])
    with pytest.raises(ActionError, match="Only the player who asked"):
        answer(s, "p1", "withdraw")
    answer(s, "p2", "withdraw")
    assert s.undo_request is None and notices(s)[-1] == "Bob withdrew their undo request (draw)."
    assert len(zone(s.state, "p1", "hand")) == 1


@pytest.mark.parametrize("change", ["action", "undo", "redo"])
def test_any_change_to_the_table_cancels_a_request(cards, change):
    s = make_session(cards)
    act(s, "p1", type="life", delta=-1)
    act(s, "p1", type="draw")
    if change == "redo":
        s.undo("p1")
        s.redo("p1")
    request(s, "p2", host=False, others=["p1"])
    if change == "action":
        act(s, "p1", type="chat", text="wait, I meant to…")
    else:
        s.undo("p1")  # (at a hot-seat table: direct)
        if change == "redo":
            s.redo("p1")
    assert s.undo_request is None
    assert any("Bob's undo request (draw) was cancelled: the table moved on." in n for n in notices(s))
    with pytest.raises(ActionError, match="No undo request"):
        answer(s, "p1", "approve")


def test_own_policy_refusal_can_be_requested(cards):
    s = make_session(cards)
    act(s, "p1", type="configure", undo_policy="own")
    act(s, "p1", type="life", delta=-5)
    with pytest.raises(ActionError, match="Alice's"):
        s.undo("p2", others=["p1"])
    assert ask(s, "p2", host=False, others=["p1"]).startswith("Players may only undo their own actions")
    assert ask(s, "p1", host=False, others=["p2"]) is None  # Alice undoes her own life change directly
    with pytest.raises(ActionError, match="Nobody else in the game"):
        request(s, "p2", host=False, others=[])
    with pytest.raises(ActionError, match="Nothing to ask"):
        request(s, "p1", host=False, others=["p2"])
    req = request(s, "p2", host=False, others=["p1"])
    assert req.shown is None and req.label == "life change" and req.refused is not None
    answer(s, "p1", "approve")
    assert s.state.players["p1"].life == 40
    replay_matches(s)


def test_hot_seat_has_no_requests(cards):
    s = make_session(cards)
    act(s, "p1", type="draw")
    with pytest.raises(ActionError, match="hot-seat"):
        request(s, "p2", host=True, others=None)
    assert ask(s, "p2", host=True, others=None) is None


def test_the_request_never_names_a_hidden_card(cards):
    s = build(cards)
    draw_all(s)
    mana(s, G=2)
    visionary = hand(s, "p1", "Elvish Visionary")
    hand_before = set(zone(s.state, "p1", "hand"))
    act(s, "p1", type="cast_spell", card_id=visionary.id)
    drawn = [s.state.cards[c] for c in zone(s.state, "p1", "hand") if c not in hand_before]
    assert len(drawn) == 1
    req = request(s, "p2", host=False, others=["p1"])
    assert req.label == "cast Elvish Visionary" and req.shown == "draw"  # the cast card is public now; the drawn one isn't
    text = json.dumps(req.public(s.state)) + json.dumps(s.view("p2")["log"][-1])
    assert drawn[0].name not in text and drawn[0].id not in text
    s2 = make_session(cards)
    act(s2, "p1", type="draw")
    secret = s2.state.cards[zone(s2.state, "p1", "hand")[0]]
    act(s2, "p1", type="move", card_ids=[secret.id], to={"zone": "library"})  # put back: no name either
    act(s2, "p1", type="draw")
    req2 = request(s2, "p2", host=False, others=["p1"])
    assert req2.label == "draw" and secret.name not in json.dumps(req2.public(s2.state))
    answer(s2, "p1", "approve")
    replay_matches(s)
    replay_matches(s2)


def test_what_an_action_showed_survives_save_and_load(cards):
    s = make_session(cards)
    act(s, "p1", type="draw")
    act(s, "p1", type="life", delta=-2)
    s.undo("p1", others=["p2"])  # the life change: direct
    data = json.loads(json.dumps({"state": s.state.model_dump(mode="json"), "history": s.history.to_dict()}))
    assert data["history"]["actions"][0]["shown"] == "draw" and "shown" not in data["history"]["actions"][1]
    loaded = GameSession(GameState.model_validate(data["state"]), cards=cards, history=History.from_dict(data["history"]))
    with pytest.raises(ActionError, match="draw"):
        loaded.undo("p2", others=["p1"])
    request(loaded, "p2", host=False, others=["p1"])
    answer(loaded, "p1", "approve")
    assert zone(loaded.state, "p1", "hand") == []
    replay_matches(loaded)
    # a save from before this: the draw has no note, its type still says it
    del data["history"]["actions"][0]["shown"]
    old = GameSession(GameState.model_validate(data["state"]), cards=cards, history=History.from_dict(data["history"]))
    with pytest.raises(ActionError, match="draw"):
        old.undo("p2", others=["p1"])


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
    return {"gid": gid, "host": game["seat"]["token"], "host_computer": game["host_token"], "bob": bob, "cleo": cleo, "code": code}


def post(client, t, path, token, json_body=None, *, remote=True):
    return client.post(f"/api/games/{t['gid']}/{path}", json=json_body or {},
                       headers={"X-Seat-Token": token, **(REMOTE if remote else {})})


def view_of(client, t, token, *, remote=True):
    return client.get(f"/api/games/{t['gid']}/view", headers={"X-Seat-Token": token, **(REMOTE if remote else {})}).json()


def hand_size(view, pid="p1"):
    return next(p for p in view["players"] if p["id"] == pid)["hand_count"]


def test_lan_request_approve_and_the_views(client, lan):
    assert post(client, lan, "actions", lan["host"], {"action": {"type": "draw"}}, remote=False).status_code == 200
    res = post(client, lan, "undo", lan["bob"])
    assert res.status_code == 409 and "take back a draw" in res.json()["detail"]
    assert view_of(client, lan, lan["bob"])["game"]["undo_ask"] == "This undo would take back a draw that players already saw."
    assert view_of(client, lan, lan["host"], remote=False)["game"]["undo_ask"] is not None  # Alice's own draw asks too
    assert post(client, lan, "undo-request", lan["bob"], {"op": "request"}).status_code == 200
    for token, remote in ((lan["host"], False), (lan["bob"], True), (lan["cleo"], True), (lan["host_computer"], False)):
        pending = view_of(client, lan, token, remote=remote)["game"]["undo_request"]
        assert pending["by"] == "p2" and pending["label"] == "draw" and pending["waiting"] == ["p1", "p3"]
    assert post(client, lan, "undo-request", lan["host_computer"], {"op": "approve"}, remote=False).status_code == 403
    assert post(client, lan, "undo-request", lan["bob"], {"op": "approve"}).status_code == 409
    assert post(client, lan, "undo-request", lan["host"], {"op": "approve"}, remote=False).status_code == 200
    assert hand_size(view_of(client, lan, lan["cleo"])) == 1
    res = post(client, lan, "undo-request", lan["cleo"], {"op": "approve"})
    assert res.status_code == 200 and hand_size(res.json()) == 0 and res.json()["game"]["undo_request"] is None
    log = ["".join(p.get("t", "") for p in e["parts"]) for e in res.json()["log"]]
    assert any("Bob undid: draw (with the table's approval)" in line for line in log)


def test_lan_decline_withdraw_and_a_new_action(client, lan):
    post(client, lan, "actions", lan["host"], {"action": {"type": "roll", "sides": 6}}, remote=False)
    post(client, lan, "undo-request", lan["bob"], {"op": "request"})
    assert view_of(client, lan, lan["cleo"])["game"]["undo_request"]["shown"] == "random"
    assert post(client, lan, "undo-request", lan["cleo"], {"op": "decline"}).json()["game"]["undo_request"] is None
    post(client, lan, "undo-request", lan["bob"], {"op": "request"})
    assert post(client, lan, "undo-request", lan["cleo"], {"op": "withdraw"}).status_code == 409
    assert post(client, lan, "undo-request", lan["bob"], {"op": "withdraw"}).json()["game"]["undo_request"] is None
    post(client, lan, "undo-request", lan["bob"], {"op": "request"})
    res = post(client, lan, "actions", lan["cleo"], {"action": {"type": "life", "delta": -1}})
    assert res.json()["game"]["undo_request"] is None
    # the life change shows nothing: Bob undoes it directly (default setting unchanged); the roll still asks
    assert view_of(client, lan, lan["bob"])["game"]["undo_ask"] is None
    assert post(client, lan, "undo", lan["bob"]).status_code == 200
    assert post(client, lan, "undo", lan["bob"]).status_code == 409


def test_lan_websocket_undo_asks_too(client, lan):
    post(client, lan, "actions", lan["host"], {"action": {"type": "coin"}}, remote=False)
    with client.websocket_connect(f"/ws/games/{lan['gid']}?token={lan['bob']}", headers=REMOTE) as ws:
        assert ws.receive_json()["type"] == "state"
        ws.send_json({"type": "undo", "id": 1})
        while (msg := ws.receive_json())["type"] == "state":
            pass
        assert msg["type"] == "error" and "random result" in msg["message"]


def test_lan_unclaimed_seats_are_not_asked(client):
    a = client.post("/api/decks", json={"text": KRENKO}).json()["id"]
    body = {"name": "Two of three", "mode": "lan", "players": [{"name": "Alice", "deck_id": a}, {"name": "Bob", "deck_id": a},
                                                               {"name": "Cleo", "deck_id": a}]}
    game = client.post("/api/games", json=body).json()
    t = {"gid": game["game"]["id"]}
    bob = client.post("/api/join", json={"code": game["game"]["code"], "name": "Bob"}, headers=REMOTE).json()["token"]
    post(client, t, "actions", bob, {"action": {"type": "draw"}})
    post(client, t, "undo-request", bob, {"op": "request"})
    assert view_of(client, t, bob)["game"]["undo_request"]["voters"] == ["p1"]  # Cleo's seat is empty


@pytest.fixture()
def local(client):
    a = client.post("/api/decks", json={"text": KRENKO}).json()["id"]
    b = client.post("/api/decks", json={"text": ATRAXA}).json()["id"]
    body = {"name": "Hot seat", "players": [{"name": "Alice", "deck_id": a}, {"name": "Bob", "deck_id": b}]}
    return client.post("/api/games", json=body).json()["game"]["id"]


def test_hot_seat_undoes_directly(client, local):
    client.post(f"/api/games/{local}/actions", json={"action": {"type": "draw"}, "as": "p1", "viewer": "p1"})
    view = client.get(f"/api/games/{local}/view", params={"viewer": "p2"}).json()
    assert view["game"]["undo_ask"] is None and view["game"]["undo_request"] is None
    res = client.post(f"/api/games/{local}/undo-request", json={"op": "request", "as": "p2", "viewer": "p2"})
    assert res.status_code == 409 and "hot-seat" in res.json()["detail"]
    res = client.post(f"/api/games/{local}/undo", json={"as": "p2", "viewer": "p2"})
    assert res.status_code == 200 and hand_size(res.json()) == 0
