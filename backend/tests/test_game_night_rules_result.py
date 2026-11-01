"""-- rules result -- when the rules engine ends the game, the game-night flow follows (GAME_NIGHT_FLOW.md §4-6).

The server opens the end-game proposal with the engine's result (``app.multiplayer.night.follow_rules``); the players who were
still in the game when it ended each confirm it with one click, and it is recorded as the engine's result (never as an agreed
one); the spotlight and the rematch vote follow as for any recorded result. Undoing the deciding action withdraws it; a decline
leaves it alone; manual End game works as before. Players the engine eliminates get the eliminated flow (their seat in the
view's ``rules.lost`` while the game goes on) and never a proposal. 104.4a: everyone still in losing at once is a draw.
"""

from __future__ import annotations

import pytest

from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.multiplayer.night import Night
from tests.game_helpers import act, enable, find
from tests.test_lobby import ALICE_DECK, BOB_DECK, h
from tests.test_rules_bandmate_references import mana, wait_priority
from tests.test_rules_designations import settle
from tests.test_rules_wave6c_tokens_pumps import chars


def replay_matches(s: GameSession) -> None:
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def roundtrip(s: GameSession) -> None:
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


# --------------------------------------------------------------------------- a two-player LAN table with full automation


@pytest.fixture()
def lan(client):
    a = client.post("/api/decks", json={"text": ALICE_DECK}).json()["id"]
    b = client.post("/api/decks", json={"text": BOB_DECK}).json()["id"]
    game = client.post("/api/games", json={"mode": "lan", "shuffle": False, "automation": "full", "first_player": 0,
                                           "players": [{"name": "Alice", "deck_id": a}, {"name": "Bob", "deck_id": b}]})
    assert game.status_code == 201, game.text
    body = game.json()
    gid, code, alice = body["game"]["id"], body["game"]["code"], body["seat"]["token"]
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    return client, gid, alice, bob


def view(client, gid, token):
    res = client.get(f"/api/games/{gid}/view", headers=h(token))
    assert res.status_code == 200, res.text
    return res.json()


def action(client, gid, token, payload):
    res = client.post(f"/api/games/{gid}/actions", json={"action": payload}, headers=h(token))
    assert res.status_code == 200, res.text
    return res.json()


def answer(client, gid, token, agree):
    return client.post(f"/api/games/{gid}/night/answer", json={"agree": agree}, headers=h(token))


def kill_bob(client, gid, alice, bob):
    """Bob is at 0 life; Alice passes and the engine checks state-based actions: Bob loses, Alice is the last one in (104.2a)."""
    action(client, gid, bob, {"type": "set_life", "player": "p2", "value": 0})
    action(client, gid, alice, {"type": "pass_priority"})
    state = client.app.state.services.hub.get(gid).session.state
    assert state.rules.winner == "p1" and state.rules.lost == {"p2": "0 or less life"}


def test_the_rules_result_opens_the_proposal_and_each_finalist_confirms_it(lan):
    client, gid, alice, bob = lan
    assert view(client, gid, alice)["viewer"] == "p1" and view(client, gid, bob)["viewer"] == "p2"
    action(client, gid, bob, {"type": "set_life", "player": "p2", "value": 0})
    assert view(client, gid, bob)["game"]["night"]["proposal"] is None  # by hand: nothing happens yet
    action(client, gid, alice, {"type": "pass_priority"})
    night = view(client, gid, bob)["game"]["night"]
    p = night["proposal"]
    assert p["rules"] == "Bob lost (0 or less life)" and p["by_name"] == "The rules"
    assert p["result_type"] == "single" and p["winners"] == ["p1"] and p["winner_names"] == ["Alice"]
    assert p["voters"] == ["p1", "p2"] and p["agreed"] == [] and night["result"] is None
    assert client.get(f"/api/games/{gid}/result").json() is None  # nothing recorded until the players confirm
    assert "The rules ended the game: Alice wins. Bob lost (0 or less life)." in str(view(client, gid, bob)["log"])
    # spectators don't confirm
    code = client.get(f"/api/games/{gid}").json()["code"]
    spectator = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    assert answer(client, gid, spectator, True).status_code == 403
    # Alice confirms; Bob (out of the game since the last action, but in it when it ended) confirms too
    assert answer(client, gid, alice, True).status_code == 200
    night = view(client, gid, alice)["game"]["night"]
    assert night["proposal"]["agreed"] == ["p1"] and night["result"] is None
    assert answer(client, gid, bob, True).status_code == 200
    night = view(client, gid, bob)["game"]["night"]
    assert night["proposal"] is None
    assert night["result"] == {"result_type": "single", "winners": ["p1"], "winner_names": ["Alice"], "agreed": False, "rules": True}
    recorded = client.get(f"/api/games/{gid}/result").json()
    assert recorded["winners"] == ["Alice"] and recorded["notes"] == "Rules result: Bob lost (0 or less life)."
    log = str(view(client, gid, bob)["log"])
    assert "Game over by the rules — Alice won." in log and "agreed by the players" not in log
    assert night["history"][0]["rules"] is True and night["history"][0]["agreed"] is False
    # the rematch vote follows as for any result: the winner goes last
    client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(alice))
    res = client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(bob))
    assert res.json()["decision"] == "rematch"
    night = view(client, gid, alice)["game"]["night"]
    assert night["number"] == 2 and night["order_source"] == "winner_last" and night["previous_winner"] == "p2"
    assert night["proposal"] is None and night["result"] is None
    replay_matches(client.app.state.services.hub.get(gid).session)


def test_undoing_the_deciding_action_withdraws_the_proposal_and_redo_reopens_it(lan):
    client, gid, alice, bob = lan
    kill_bob(client, gid, alice, bob)
    assert view(client, gid, alice)["game"]["night"]["proposal"]["rules"]
    answer(client, gid, alice, True)  # a confirmation is forgotten with the proposal
    assert client.post(f"/api/games/{gid}/undo", json={}, headers=h(bob)).status_code == 200
    v = view(client, gid, alice)
    assert v["rules"]["winner"] is None and v["game"]["night"]["proposal"] is None
    assert "the rules result is withdrawn" in str(v["log"])
    assert client.post(f"/api/games/{gid}/redo", json={}, headers=h(bob)).status_code == 200
    p = view(client, gid, alice)["game"]["night"]["proposal"]
    assert p["rules"] and p["voters"] == ["p1", "p2"] and p["agreed"] == []
    # a player's own proposal that a later undo touches stays: only the rules result is withdrawn
    client.post(f"/api/games/{gid}/undo", json={}, headers=h(bob))
    client.post(f"/api/games/{gid}/night/propose", json={"result_type": "draw"}, headers=h(alice))
    action(client, gid, alice, {"type": "set_life", "player": "p1", "value": 39})
    assert view(client, gid, bob)["game"]["night"]["proposal"]["result_type"] == "draw"
    replay_matches(client.app.state.services.hub.get(gid).session)


def test_the_engine_result_replaces_a_pending_player_proposal(lan):
    client, gid, alice, bob = lan
    client.post(f"/api/games/{gid}/night/propose", json={"result_type": "single", "winners": ["p2"]}, headers=h(alice))
    kill_bob(client, gid, alice, bob)
    p = view(client, gid, alice)["game"]["night"]["proposal"]
    assert p["rules"] and p["winners"] == ["p1"] and p["agreed"] == []


def test_a_decline_leaves_it_to_the_pod_and_manual_end_game_still_works(lan):
    client, gid, alice, bob = lan
    kill_bob(client, gid, alice, bob)
    assert answer(client, gid, bob, False).status_code == 200
    v = view(client, gid, alice)
    assert v["game"]["night"]["proposal"] is None and v["game"]["night"]["result"] is None
    assert "didn't confirm the rules result" in str(v["log"])
    action(client, gid, alice, {"type": "set_life", "player": "p1", "value": 12})  # the table changes: still not asked again
    assert view(client, gid, alice)["game"]["night"]["proposal"] is None
    assert answer(client, gid, alice, True).status_code == 409
    # the host records the result by hand, exactly as before (only the host may)
    body = {"result_type": "single", "winners": ["p1"], "notes": "by hand"}
    assert client.post(f"/api/games/{gid}/result", json=body, headers=h(bob)).status_code == 403
    res = client.post(f"/api/games/{gid}/result", json=body, headers=h(alice))
    assert res.status_code == 201 and res.json()["notes"] == "by hand"
    night = view(client, gid, alice)["game"]["night"]
    assert night["result"]["agreed"] is False and night["result"]["rules"] is False
    # undo after a recorded result changes nothing about it
    client.post(f"/api/games/{gid}/undo", json={}, headers=h(bob))
    client.post(f"/api/games/{gid}/undo", json={}, headers=h(bob))
    assert view(client, gid, alice)["game"]["night"]["result"]["winners"] == ["p1"]


def test_manual_end_game_while_the_rules_result_waits(lan):
    client, gid, alice, bob = lan
    kill_bob(client, gid, alice, bob)
    res = client.post(f"/api/games/{gid}/result", json={"result_type": "single", "winners": ["p1"]}, headers=h(alice))
    assert res.status_code == 201 and res.json()["notes"] == ""
    night = view(client, gid, alice)["game"]["night"]
    assert night["proposal"] is None and night["result"]["rules"] is False
    assert answer(client, gid, bob, True).status_code == 409


def test_a_player_proposal_without_the_engine_is_unchanged(lan):
    client, gid, alice, bob = lan
    client.post(f"/api/games/{gid}/night/propose", json={"result_type": "single", "winners": ["p2"]}, headers=h(alice))
    p = view(client, gid, bob)["game"]["night"]["proposal"]
    assert p["rules"] is None and p["voters"] == [] and p["by_name"] == "Alice"
    answer(client, gid, bob, True)
    night = view(client, gid, bob)["game"]["night"]
    assert night["result"]["agreed"] is True and night["result"]["rules"] is False


def test_concession_ends_it_and_the_conceder_is_not_asked(lan):
    client, gid, alice, bob = lan
    action(client, gid, bob, {"type": "concede"})
    p = view(client, gid, alice)["game"]["night"]["proposal"]
    assert p["rules"] == "Bob conceded" and p["voters"] == ["p1"] and p["winners"] == ["p1"]
    assert answer(client, gid, bob, True).status_code == 403
    answer(client, gid, alice, True)
    assert view(client, gid, alice)["game"]["night"]["result"]["winners"] == ["p1"]


def test_a_saved_or_restored_table_asks_again(lan):
    client, gid, alice, bob = lan
    kill_bob(client, gid, alice, bob)
    hub = client.app.state.services.hub
    room = hub.get(gid)
    # a crash restart: the room comes back from its recovery record and its history
    meta = hub.meta(room)
    session = room.session
    hub.close(gid)
    restored = hub.restore(meta, session, {})
    p = restored.night.proposal
    assert p is not None and p.rules == "Bob lost (0 or less life)" and p.voters == ["p1", "p2"]
    # a save loaded later (as a hot-seat table): the history says who was in the game when it ended
    save = client.post(f"/api/games/{gid}/save", json={"name": "over"}, headers=h(alice)).json()
    loaded = client.post(f"/api/saves/{save['id']}/load", json={"mode": "local"})
    assert loaded.status_code == 201, loaded.text
    lid = loaded.json()["game"]["id"]
    p = client.get(f"/api/games/{lid}/view").json()["game"]["night"]["proposal"]
    assert p["rules"] == "Bob lost (0 or less life)" and p["voters"] == ["p1", "p2"]
    # one person runs a hot-seat table: one click settles it
    res = client.post(f"/api/games/{lid}/night/answer", json={"agree": True, "as_player": "p2"})
    assert res.status_code == 200 and res.json()["result"]["winners"] == ["p1"] and res.json()["result"]["rules"] is True
    room = hub.get(lid)
    roundtrip(room.session)
    # a loaded game whose result is already recorded doesn't ask again
    again = client.post(f"/api/saves/{save['id']}/load", json={"mode": "local"}).json()["game"]["id"]
    assert client.get(f"/api/games/{again}/view").json()["game"]["night"]["proposal"] is None


def test_the_rules_state_is_not_saved_in_the_night_record():
    night = Night()
    night.rules_end = "win:p1"
    assert "rules_end" not in night.meta() and Night.from_meta(night.meta()).rules_end is None


# --------------------------------------------------------------------------- 104.4a: everyone still in loses at once


def test_everyone_losing_at_once_is_a_draw_and_proposes_one(lan):
    client, gid, alice, bob = lan
    action(client, gid, bob, {"type": "set_life", "player": "p2", "value": 0})
    action(client, gid, alice, {"type": "set_life", "player": "p1", "value": -2})
    action(client, gid, alice, {"type": "pass_priority"})
    v = view(client, gid, bob)
    assert set(v["rules"]["lost"]) == {"p1", "p2"} and v["rules"]["winner"] is None
    assert v["rules"]["draw_reason"] == "Every player still in the game lost at the same time (104.4a)"
    p = v["game"]["night"]["proposal"]
    assert p["result_type"] == "draw" and p["winners"] == [] and p["voters"] == ["p1", "p2"]
    assert p["rules"] == "Every player still in the game lost at the same time (104.4a)"
    answer(client, gid, alice, True)
    answer(client, gid, bob, True)
    night = view(client, gid, bob)["game"]["night"]
    assert night["result"]["result_type"] == "draw" and night["result"]["rules"] is True
    # after a draw the next game rolls the d20 again
    client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(alice))
    client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(bob))
    assert view(client, gid, alice)["game"]["night"]["order_source"] == "d20"


# --------------------------------------------------------------------------- the eliminated flow, every engine loss


def six(cards) -> GameSession:
    def deck(commander: str, land: str) -> list[DeckCard]:
        cmd = cards.resolve(commander)
        return [DeckCard("commander", 1, cmd["name"], cmd["id"]), DeckCard("main", 5, land, cards.resolve(land)["id"])]

    setups = [PlayerSetup(n, cards=deck("Krenko, Mob Boss", "Mountain")) for n in ("Ann", "Ben", "Cat", "Dan", "Eve", "Fay")]
    state = new_game(setups, shuffle=False, first_player=0)
    enable(state)
    return GameSession(state, cards=cards)


def ability(s, pid, text):
    act(s, pid, type="create_token", player=pid, token={"name": f"Tool {len(s.state.cards)}", "type_line": "Token Artifact — Test",
                                                        "text": text, "colors": []})
    return max((c for c in s.state.cards.values() if c.name.startswith("Tool ")), key=lambda c: int(c.name.split()[1]))


def use(s, tool, target):
    mana(s, "p1", C=1)
    wait_priority(s, "p1")
    act(s, "p1", type="activate_ability", card_id=tool.id, ability=chars(s, tool).abilities[0].index,
        targets=[target] if target else [], sources=[])
    settle(s)


def test_every_engine_loss_gets_the_eliminated_flow_and_only_the_finalists_confirm(client):
    services = client.app.state.services
    s = six(services.cards)
    room = services.hub.create_room(s, mode="local")
    krenko = find(s.state, "Krenko, Mob Boss", "p1")
    draw = ability(s, "p1", "{1}: Target player draws a card.")
    doom = ability(s, "p1", "{1}: Target player loses the game.")
    act(s, "p2", type="set_life", player="p2", value=0)
    act(s, "p3", type="resource", player="p3", key="poison", delta=10)
    act(s, "p4", type="commander_damage", player="p4", commander=krenko.commander_key, delta=21, affect_life=False)
    act(s, "p5", type="move", card_ids=list(s.state.zones["p5:library"]), to={"zone": "exile"})
    use(s, draw, "p5")
    services.hub.after_change(room)
    r = s.state.rules
    assert r.lost == {"p2": "0 or less life", "p3": "10 poison counters", "p4": "21 combat damage from one commander",
                      "p5": "drew from an empty library"}
    assert r.winner is None and r.draw_reason is None
    # each of them sees themself out (the client's eliminated flow reads rules.lost), and the game goes on: nobody is asked
    for pid in ("p2", "p3", "p4", "p5"):
        assert pid in s.view(pid)["rules"]["lost"]
    assert room.night.proposal is None
    use(s, doom, "p6")
    services.hub.after_change(room)
    assert s.state.rules.lost["p6"] == "an effect" and s.state.rules.winner == "p1"
    assert "p6" in s.view("p6")["rules"]["lost"]
    p = room.night.proposal
    assert p is not None and p.voters == ["p1", "p6"] and p.winners == ["p1"] and p.rules == "Fay lost (an effect)"
    roundtrip(s)


def test_104_4a_in_the_engine_both_ways(client):
    """104.4a in the engine itself: state-based actions (both at 0 life) and an effect ("Each player loses the game.") that
    leaves nobody in end the game as a draw; nothing more can be done, the replay and a save/load round trip agree."""
    from app.game.errors import ActionError

    services = client.app.state.services
    s = six(services.cards)
    for pid in ("p3", "p4", "p5", "p6"):
        act(s, pid, type="concede")
    act(s, "p2", type="set_life", player="p2", value=0)
    act(s, "p1", type="set_life", player="p1", value=0)
    act(s, "p1", type="pass_priority")
    r = s.state.rules
    assert set(r.lost) == {"p1", "p2"} and r.winner is None
    assert r.draw_reason == "Every player still in the game lost at the same time (104.4a)"
    with pytest.raises(ActionError, match="draw"):
        act(s, "p1", type="pass_priority")
    roundtrip(s)
    s = six(services.cards)
    for pid in ("p4", "p5", "p6"):
        act(s, pid, type="concede")
    doom = ability(s, "p1", "{1}: Each player loses the game.")
    use(s, doom, None)
    r = s.state.rules
    assert set(r.lost) == {"p1", "p2", "p3"} and r.winner is None and r.draw_reason is not None
    roundtrip(s)
