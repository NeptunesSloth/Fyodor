"""-- table permissions -- the host's "Who may change a player's cards" setting (app/game/table_rights.py): "everyone" (the
default) keeps tabletop freedom; "owner" refuses a player's manual table edits on another player's cards (the controller's on
the battlefield and the stack, the owner's or zone holder's elsewhere) while the host can always help. Rules actions, looking,
player counters and the table's procedures are never checked; a hot-seat table ignores the setting."""

from __future__ import annotations

import json
import typing

import pytest

from app.game import actions as A
from app.game import table_rights
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.history import History
from app.game.session import GameSession
from app.game.state import GameState
from tests.conftest import connect_game, guest
from tests.game_helpers import act, deck, find, zone
from tests.test_games_api import ATRAXA, KRENKO
from tests.test_rules_effects import build, draw_all, hand, mana, pass_until_stack_empty

REMOTE = guest()
REFUSED = "only {0} or the host can change them at this table"


def replay_matches(s: GameSession) -> None:
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def table(cards, *, policy: str = "owner") -> GameSession:
    """Alice (p1, the host), Bob (p2) and Cleo (p3), each with a deck; Alice's Sol Ring and Bob's Arcane Signet are out."""
    alice = deck(cards, "Krenko, Mob Boss", [(1, "Sol Ring"), (1, "Lightning Bolt"), (1, "Llanowar Elves"), (6, "Mountain")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(1, "Counterspell"), (1, "Arcane Signet"), (6, "Island")])
    cleo = deck(cards, "Atraxa, Praetors' Voice", [(1, "Counterspell"), (6, "Island")])
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob), PlayerSetup("Cleo", cards=cleo)],
                     name="Perms", shuffle=False)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="move", card_ids=[find(state, "Sol Ring", "p1").id], to={"zone": "battlefield", "player": "p1"})
    act(s, "p2", type="move", card_ids=[find(state, "Arcane Signet", "p2").id], to={"zone": "battlefield", "player": "p2"})
    if policy != "everyone":
        s.perform("p1", {"type": "configure", "card_permissions": policy}, host=True)
    return s


def refused(s: GameSession, actor: str, who: str, **payload) -> None:
    before = (s.state.model_dump(mode="json"), len(s.history.actions))
    with pytest.raises(ActionError, match=REFUSED.format(who)):
        s.perform(actor, payload)
    assert (s.state.model_dump(mode="json"), len(s.history.actions)) == before  # nothing applied, nothing recorded


def ok(s: GameSession, actor: str, *, host: bool = False, **payload) -> None:
    s.perform(actor, payload, host=host)


# ---------------------------------------------------------------------------- the setting


def test_everyone_is_the_default_and_unchanged(cards):
    s = table(cards, policy="everyone")
    assert s.state.settings.card_permissions == "everyone"
    ring = find(s.state, "Sol Ring", "p1")
    ok(s, "p2", type="tap", card_ids=[ring.id])
    ok(s, "p3", type="counter", card_ids=[ring.id], kind="charge")
    ok(s, "p2", type="move", card_ids=[ring.id], to={"zone": "graveyard", "player": "p1"})
    ok(s, "p3", type="draw", player="p1")
    assert s.state.cards[ring.id].zone == "p1:graveyard"
    replay_matches(s)


def test_every_action_type_is_classified_once():
    union = typing.get_args(typing.get_args(A.Action)[0])
    types = {cls.model_fields["type"].default for cls in union}
    checked = table_rights.CARD_IDS | table_rights.CARD_ID | table_rights.PLAYER | table_rights.OTHER
    assert not checked & table_rights.OPEN
    assert types == checked | table_rights.OPEN, types ^ (checked | table_rights.OPEN)


# ---------------------------------------------------------------------------- refused: another player's cards


def test_owner_policy_refuses_manual_edits_of_another_players_cards(cards):
    s = table(cards)
    ring = find(s.state, "Sol Ring", "p1")
    for payload in (
        {"type": "tap", "card_ids": [ring.id]},
        {"type": "counter", "card_ids": [ring.id], "kind": "charge"},
        {"type": "set_counter", "card_id": ring.id, "kind": "charge", "value": 3},
        {"type": "move", "card_ids": [ring.id], "to": {"zone": "graveyard", "player": "p1"}},
        {"type": "set_position", "moves": [[ring.id, 100, 100]]},
        {"type": "note", "card_id": ring.id, "text": "mine now"},
        {"type": "add_effect", "card_ids": [ring.id], "name": "P/T", "value": "4/4"},
        {"type": "set_damage", "card_ids": [ring.id], "value": 2},
        {"type": "flip", "card_id": ring.id},
        {"type": "face_down", "card_ids": [ring.id], "face_down": True},
        {"type": "set_controller", "card_ids": [ring.id], "player": "p2"},
        {"type": "rotate", "card_ids": [ring.id], "delta": 90},
        {"type": "set_lock", "card_ids": [ring.id], "value": True},
        {"type": "attack", "card_ids": [ring.id], "target": {"kind": "player", "id": "p2"}},
        {"type": "set_commander", "card_id": ring.id},
        {"type": "delete_card", "card_ids": [ring.id]},
    ):
        refused(s, "p2", "Alice", **payload)
    # the zone-wide tools on another player's cards, and new objects under their control
    refused(s, "p2", "Alice", type="draw", player="p1")
    refused(s, "p3", "Alice", type="mill", player="p1")
    refused(s, "p2", "Alice", type="shuffle", player="p1")
    refused(s, "p2", "Alice", type="untap_all", player="p1")
    refused(s, "p2", "Alice", type="create_token", player="p1", token={"name": "Goblin"})
    refused(s, "p2", "Alice", type="copy_card", card_id=ring.id, player="p1")


def test_a_refusal_through_a_hidden_placeholder_names_only_the_zone(cards):
    s = table(cards)
    act(s, "p1", type="draw", count=2)
    placeholder = s.view("p2")["zones"]["p1:hand"][0]
    assert placeholder.startswith("hidden:")
    refused(s, "p2", "Alice", type="move", card_ids=[placeholder], to={"zone": "graveyard", "player": "p1"})


def test_a_hidden_zones_cards_are_its_players_whoever_owns_them(cards):
    """Other players' views give a hidden card no owner but its zone's player: the answer, and its words, may not depend on more."""
    s = table(cards)
    bolt = find(s.state, "Lightning Bolt", "p1")
    ok(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "hand", "player": "p2"})  # Alice's own card, into Bob's hand
    in_bobs_hand = s.view("p3")["zones"]["p2:hand"]
    assert s.view("p3")["cards"][in_bobs_hand[0]]["owner"] == "p2"  # what Cleo's view says
    with pytest.raises(ActionError) as refusal:
        s.perform("p3", {"type": "move", "card_ids": [in_bobs_hand[0]], "to": {"zone": "graveyard", "player": "p2"}})
    assert str(refusal.value) == "Bob's cards: only Bob or the host can change them at this table."
    refused(s, "p1", "Bob", type="move", card_ids=[bolt.id], to={"zone": "graveyard", "player": "p1"})
    ok(s, "p2", type="move", card_ids=[s.view("p2")["zones"]["p2:hand"][0]], to={"zone": "graveyard", "player": "p1"})
    assert s.state.cards[bolt.id].zone == "p1:graveyard"
    replay_matches(s)


def test_a_macro_is_checked_step_by_step(cards):
    s = table(cards)
    ring = find(s.state, "Sol Ring", "p1")
    signet = find(s.state, "Arcane Signet", "p2")
    steal = {"name": "Steal", "steps": [{"op": "CHANGE_CONTROLLER", "target": "this", "player": "me"}]}
    refused(s, "p2", "Alice", type="run_macro", macro=steal, card_id=ring.id)
    grow = {"name": "Grow", "steps": [{"op": "ADD_COUNTER", "target": "this", "kind": "charge"}]}
    ok(s, "p2", type="run_macro", macro=grow, card_id=signet.id)
    assert s.state.cards[signet.id].counters == {"charge": 1}


# ---------------------------------------------------------------------------- allowed: owner, controller, host


def test_a_player_changes_their_own_cards(cards):
    s = table(cards)
    ring = find(s.state, "Sol Ring", "p1")
    ok(s, "p1", type="tap", card_ids=[ring.id])
    ok(s, "p1", type="counter", card_ids=[ring.id], kind="charge")
    ok(s, "p1", type="set_position", moves=[[ring.id, 200, 120]])
    ok(s, "p1", type="draw")
    ok(s, "p1", type="create_token", token={"name": "Goblin"})
    assert s.state.cards[ring.id].tapped and s.state.cards[ring.id].counters == {"charge": 1}
    replay_matches(s)


def test_the_host_can_always_help(cards):
    s = table(cards)
    signet = find(s.state, "Arcane Signet", "p2")
    ok(s, "p1", host=True, type="tap", card_ids=[signet.id])
    ok(s, "p1", host=True, type="move", card_ids=[signet.id], to={"zone": "graveyard", "player": "p2"})
    ok(s, "p1", host=True, type="draw", player="p3")
    assert s.state.cards[signet.id].zone == "p2:graveyard" and len(zone(s.state, "p3", "hand")) == 1
    replay_matches(s)


def test_a_stolen_permanent_is_its_controllers_until_it_goes_back(cards):
    s = table(cards)
    ring = find(s.state, "Sol Ring", "p1")
    ok(s, "p1", type="set_controller", card_ids=[ring.id], player="p2")  # Alice gives it away (or a steal, by the host)
    assert s.state.cards[ring.id].controller == "p2"
    ok(s, "p2", type="tap", card_ids=[ring.id])  # Bob's to tap and move while he controls it
    ok(s, "p2", type="set_position", moves=[[ring.id, 300, 200]])
    refused(s, "p1", "Bob", type="tap", card_ids=[ring.id])  # its owner waits for it
    refused(s, "p1", "Bob", type="return_to_owner", card_ids=[ring.id])
    refused(s, "p3", "Bob", type="counter", card_ids=[ring.id], kind="charge")
    ok(s, "p2", type="return_to_owner", card_ids=[ring.id])  # Bob gives it back
    assert s.state.cards[ring.id].controller == "p1"
    ok(s, "p1", type="untap_all")
    replay_matches(s)


def test_my_card_in_your_exile_is_both_of_ours(cards):
    s = table(cards)
    ring = find(s.state, "Sol Ring", "p1")
    ok(s, "p1", type="move", card_ids=[ring.id], to={"zone": "exile", "player": "p2"})  # my own card, into Bob's exile
    assert s.state.cards[ring.id].zone == "p2:exile"
    refused(s, "p3", "Alice, Bob", type="set_exile_group", card_ids=[ring.id], group="Hostage")
    ok(s, "p2", type="set_exile_group", card_ids=[ring.id], group="Hostage")  # the player whose exile holds it
    ok(s, "p1", type="move", card_ids=[ring.id], to={"zone": "graveyard", "player": "p1"})  # and its owner
    assert s.state.cards[ring.id].zone == "p1:graveyard"


def test_an_aura_stays_its_controllers_on_another_players_creature(cards):
    s = table(cards)
    signet = find(s.state, "Arcane Signet", "p2")
    act(s, "p1", type="create_token", token={"name": "Shackles", "type_line": "Token Enchantment — Aura"})
    aura = find(s.state, "Shackles", "p1")
    ok(s, "p1", type="attach", card_ids=[aura.id], to=signet.id)  # my Aura onto Bob's permanent: only my card changes
    assert s.state.cards[aura.id].attached_to == signet.id
    refused(s, "p2", "Alice", type="detach", card_ids=[aura.id])
    refused(s, "p2", "Alice", type="move", card_ids=[aura.id], to={"zone": "exile", "player": "p1"})
    ok(s, "p2", type="set_position", moves=[[signet.id, 400, 250]])  # Bob moves his own permanent, Aura and all
    assert s.state.cards[aura.id].attached_to == signet.id
    ok(s, "p2", type="move", card_ids=[signet.id], to={"zone": "graveyard", "player": "p2"})
    assert s.state.cards[aura.id].attached_to is None
    replay_matches(s)


def test_the_shared_stack_follows_the_spells_controller(cards):
    s = table(cards)
    bolt = find(s.state, "Lightning Bolt", "p1")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "stack"})  # cast by hand
    refused(s, "p2", "Alice", type="move", card_ids=[bolt.id], to={"zone": "graveyard", "player": "p1"})  # "countered" by hand
    refused(s, "p2", "Alice", type="set_stack_info", card_id=bolt.id, x=3)
    ok(s, "p2", type="resolve_top")  # resolving is the table's procedure, not an edit of Alice's card
    assert s.state.cards[bolt.id].zone == "p1:graveyard"


# ---------------------------------------------------------------------------- never checked


def test_looking_pointing_counters_and_table_procedures_stay_open(cards):
    s = table(cards)
    ring = find(s.state, "Sol Ring", "p1")
    ok(s, "p2", type="life", player="p1", delta=-3)  # a Lightning Bolt to the face
    ok(s, "p2", type="commander_damage", player="p1", commander=find(s.state, "Atraxa, Praetors' Voice", "p2").commander_key, delta=2)
    ok(s, "p2", type="resource", player="p1", key="poison")
    ok(s, "p2", type="look_top", player="p1")
    ok(s, "p2", type="end_view")
    ok(s, "p2", type="reveal_top", player="p1")
    ok(s, "p2", type="create_arrow", source=ring.id, targets=[ring.id])
    ok(s, "p2", type="copy_card", card_id=ring.id)  # a copy for myself only reads Alice's card
    ok(s, "p2", type="create_token", token={"name": "Bird"})
    ok(s, "p3", type="cleanup", what=["damage", "effects", "combat", "arrows"])  # damage wears off for everyone (514.2)
    ok(s, "p2", type="phase")
    ok(s, "p3", type="next_turn")
    ok(s, "p2", type="chat", text="gg")
    replay_matches(s)


def test_deleting_every_token_waits_for_their_controllers(cards):
    s = table(cards)
    act(s, "p1", type="create_token", token={"name": "Goblin"})
    act(s, "p2", type="create_token", token={"name": "Bird"})
    refused(s, "p2", "Alice", type="cleanup", what=["tokens"])
    bird = find(s.state, "Bird", "p2")
    ok(s, "p2", type="cleanup", what=["tokens"], card_ids=[bird.id])
    assert bird.id not in s.state.cards and find(s.state, "Goblin", "p1")
    ok(s, "p1", host=True, type="cleanup", what=["tokens"])


def test_rules_actions_are_never_blocked(cards):
    """The engine moves Bob's creature to his graveyard as Alice's Murder resolves: only Alice's intents were sent."""
    s = build(cards)
    draw_all(s)
    s.perform("p1", {"type": "configure", "card_permissions": "owner"}, host=True)
    act(s, "p2", type="create_token", player="p2", token={"name": "Ox", "type_line": "Token Creature — Ox", "power": "2",
                                                          "toughness": "4"})
    ox = find(s.state, "Ox", "p2")
    mana(s, B=3)
    murder = hand(s, "p1", "Murder")
    s.perform("p1", {"type": "cast_spell", "card_id": murder.id, "targets": [ox.id]}, host=False)
    pass_until_stack_empty(s)
    assert ox.id not in s.state.cards and s.state.cards[murder.id].zone == "p1:graveyard"
    refused(s, "p1", "Bob", type="create_token", player="p2", token={"name": "Ox2"})  # by hand it would be refused
    replay_matches(s)


# ---------------------------------------------------------------------------- saves, undo, replays


def test_the_setting_survives_undo_save_and_load(cards):
    s = table(cards)
    ring = find(s.state, "Sol Ring", "p1")
    ok(s, "p1", type="tap", card_ids=[ring.id])
    s.undo("p1")
    s.redo("p1")
    replay_matches(s)
    data = json.loads(json.dumps({"state": s.state.model_dump(mode="json"), "history": s.history.to_dict()}))
    loaded = GameSession(GameState.model_validate(data["state"]), cards=cards, history=History.from_dict(data["history"]))
    assert loaded.state.settings.card_permissions == "owner"
    with pytest.raises(ActionError, match=REFUSED.format("Alice")):
        loaded.perform("p2", {"type": "tap", "card_ids": [ring.id]})
    replay_matches(loaded)
    old = data["state"]  # an old save without the field loads as "everyone"
    del old["settings"]["card_permissions"]
    assert GameState.model_validate(old).settings.card_permissions == "everyone"


def test_changing_the_setting_mid_game_replays(cards):
    s = table(cards, policy="everyone")
    ring = find(s.state, "Sol Ring", "p1")
    ok(s, "p2", type="tap", card_ids=[ring.id])  # allowed then: replays keep it whatever the setting says now
    s.perform("p1", {"type": "configure", "card_permissions": "owner"}, host=True)
    refused(s, "p2", "Alice", type="tap", card_ids=[ring.id])
    replay_matches(s)
    s.undo("p1")
    assert s.state.settings.card_permissions == "everyone"


# ---------------------------------------------------------------------------- API: a LAN room with a host and guests


@pytest.fixture()
def lan(client):
    a = client.post("/api/decks", json={"text": KRENKO}).json()["id"]
    b = client.post("/api/decks", json={"text": ATRAXA}).json()["id"]
    body = {"name": "Perms night", "mode": "lan", "players": [{"name": "Alice", "deck_id": a}, {"name": "Bob", "deck_id": b},
                                                              {"name": "Cleo", "deck_id": b}], "shuffle": False}
    game = client.post("/api/games", json=body).json()
    gid, code = game["game"]["id"], game["game"]["code"]
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}, headers=REMOTE).json()["token"]
    cleo = client.post("/api/join", json={"code": code, "name": "Cleo"}, headers=REMOTE).json()["token"]
    return {"gid": gid, "host": game["seat"]["token"], "bob": bob, "cleo": cleo}


def act_as(client, t, token, action, **headers):
    return client.post(f"/api/games/{t['gid']}/actions", json={"action": action}, headers={"X-Seat-Token": token, **headers})


def view_of(client, t, token, **headers):
    return client.get(f"/api/games/{t['gid']}/view", headers={"X-Seat-Token": token, **headers}).json()


def ring_out(client, t) -> str:
    assert act_as(client, t, t["host"], {"type": "draw", "count": 23}).status_code == 200  # Alice's whole library
    view = view_of(client, t, t["host"])
    ring = next(c["id"] for c in view["cards"].values() if c.get("name") == "Sol Ring")
    assert act_as(client, t, t["host"], {"type": "move", "card_ids": [ring], "to": {"zone": "battlefield"}}).status_code == 200
    return ring


def test_lan_only_the_host_sets_it_and_guests_are_refused(client, lan):
    ring = ring_out(client, lan)
    assert act_as(client, lan, lan["bob"], {"type": "tap", "card_ids": [ring]}, **REMOTE).status_code == 200  # the default
    assert act_as(client, lan, lan["bob"], {"type": "configure", "card_permissions": "everyone"}, **REMOTE).status_code == 403
    assert act_as(client, lan, lan["host"], {"type": "configure", "card_permissions": "owner"}).status_code == 200
    assert view_of(client, lan, lan["cleo"], **REMOTE)["game"]["settings"]["card_permissions"] == "owner"
    res = act_as(client, lan, lan["bob"], {"type": "tap", "card_ids": [ring]}, **REMOTE)
    assert res.status_code == 409 and res.json()["detail"] == "Alice's cards: only Alice or the host can change them at this table."
    assert act_as(client, lan, lan["bob"], {"type": "life", "player": "p1", "delta": -2}, **REMOTE).status_code == 200
    assert act_as(client, lan, lan["host"], {"type": "draw", "player": "p2"}).status_code == 200  # the host helps
    res = act_as(client, lan, lan["cleo"], {"type": "draw", "player": "p2"}, **REMOTE)
    assert res.status_code == 409 and "Bob's cards" in res.json()["detail"]


def test_lan_websocket_actions_obey_it(client, lan):
    ring = ring_out(client, lan)
    act_as(client, lan, lan["host"], {"type": "configure", "card_permissions": "owner"})
    with connect_game(client, lan['gid'], lan['bob'], headers=REMOTE) as ws:
        assert ws.receive_json()["type"] == "state"
        ws.send_json({"type": "action", "id": 1, "action": {"type": "tap", "card_ids": [ring]}})
        while (msg := ws.receive_json())["type"] == "state":
            pass
        assert msg["type"] == "error" and msg["status"] == "REJECTED" and "only Alice or the host" in msg["message"]
    with connect_game(client, lan['gid'], lan['host']) as ws:
        assert ws.receive_json()["type"] == "state"
        ws.send_json({"type": "action", "id": 2, "action": {"type": "tap", "card_ids": [ring]}})
        while (msg := ws.receive_json())["type"] == "state":
            pass
        assert msg["type"] == "ack" and msg["status"] == "ACCEPTED"
    assert view_of(client, lan, lan["host"])["cards"][ring]["tapped"]


def test_lan_lobby_setting_is_the_hosts_and_starts_the_game_with_it(client):
    from tests.test_lobby import ALICE_DECK, BOB_DECK, create_lobby, h

    gid, code, alice = create_lobby(client)
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    assert client.post(f"/api/games/{gid}/lobby/settings", json={"card_permissions": "owner"}, headers=h(bob)).status_code == 403
    for token, text in ((alice, ALICE_DECK), (bob, BOB_DECK)):
        client.post(f"/api/games/{gid}/lobby/deck", json={"text": text}, headers=h(token))
        client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(token))
    res = client.post(f"/api/games/{gid}/lobby/settings", json={"card_permissions": "owner"}, headers=h(alice))
    assert res.status_code == 200 and res.json()["settings"]["card_permissions"] == "owner"
    assert all(s["ready"] for s in res.json()["seats"] if s["claimed"])  # how the table plays: nobody confirms again
    assert client.post(f"/api/games/{gid}/lobby/start", json={}, headers=h(alice)).status_code == 200
    view = client.get(f"/api/games/{gid}/view", headers=h(bob)).json()
    assert view["game"]["settings"]["card_permissions"] == "owner"
    # the host's latest choice, made at the table, holds when the pod goes back to the lobby
    act = {"action": {"type": "configure", "card_permissions": "everyone"}}
    assert client.post(f"/api/games/{gid}/actions", json=act, headers=h(alice)).status_code == 200
    client.post(f"/api/games/{gid}/night/propose", json={"result_type": "draw"}, headers=h(alice))
    client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(bob))
    assert client.post(f"/api/games/{gid}/night/vote", json={"choice": "lobby", "force": True}, headers=h(alice)).json()["decision"] == "lobby"
    lobby = client.get(f"/api/games/{gid}/lobby", headers=h(alice)).json()
    assert lobby["phase"] == "lobby" and lobby["settings"]["card_permissions"] == "everyone"


# ---------------------------------------------------------------------------- API: a hot-seat game ignores it


def test_hot_seat_tables_ignore_it(client):
    a = client.post("/api/decks", json={"text": KRENKO}).json()["id"]
    b = client.post("/api/decks", json={"text": ATRAXA}).json()["id"]
    body = {"name": "Hot seat", "players": [{"name": "Alice", "deck_id": a}, {"name": "Bob", "deck_id": b}],
            "card_permissions": "owner"}
    gid = client.post("/api/games", json=body).json()["game"]["id"]
    view = client.get(f"/api/games/{gid}/view", params={"viewer": "all"}).json()
    assert view["game"]["settings"]["card_permissions"] == "owner"
    ring = next(c["id"] for c in view["cards"].values() if c.get("name") == "Sol Ring")
    res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "draw", "player": "p1"}, "as": "p2", "viewer": "p2"})
    assert res.status_code == 200
    res = client.post(f"/api/games/{gid}/actions",
                      json={"action": {"type": "move", "card_ids": [ring], "to": {"zone": "battlefield", "player": "p1"}},
                            "as": "p2", "viewer": "p2"})
    assert res.status_code == 200
