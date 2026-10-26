"""Wave 18H review: controlling another player (CR 723) over the real action path, and its edges.

* A LAN client never acts for a seat it doesn't control (REST and WebSocket, ``as`` ignored); the controlled player can only
  concede (723.6): rules intents, table tools and undo all wait. What the controller sees never reaches anyone else.
* 723.1: the control covers the whole turn, its untap choices too, and ends with that turn even when the turn is passed by hand.
* 800.4a: a controller who leaves gives the player back their own choices, a pending one included.
* Opposition Agent (723.2) also controls and exiles a Gifts Ungiven search and a name search of one's own library.
"""

from __future__ import annotations

import json

import pytest

from app.game.control import controller_of, decider_of
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.visibility import SPECTATOR
from app.rules.view import rules_view
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_protocol_privacy import assert_hidden, cards_in
from tests.test_rules_conditionals import to_hand
from tests.test_rules_effects import mana
from tests.test_rules_wave18h_player_control import (
    EXTRA,
    bobs_turn,
    cast_on,
    drive,
    roundtrip,
    seen_by,
    table,
)
from tests.test_rules_wave18h_search_control import AGENT

MORE = [
    card("Gifts Ungiven", set_code="tst", number="C06", mana_cost="{3}{U}", cmc=4.0, type_line="Instant", oracle_text="Search your library for up to four cards with different names and reveal them. Target opponent chooses two of those cards. Put the chosen cards into your graveyard and the rest into your hand. Then shuffle.", colors=["U"], color_identity=["U"]),  # noqa: E501
    card("Sleepy Relic", set_code="tst", number="C07", mana_cost="{1}", cmc=1.0, type_line="Artifact", oracle_text="You may choose not to untap Sleepy Relic during your untap step.\n{T}: Add {C}."),  # noqa: E501
]


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, *AGENT, *MORE], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


# -- the real action path (REST + WebSocket, LAN seat tokens) -------------------------------------------------------------
def test_over_the_wire_only_the_controller_acts_and_only_they_see(client):
    alice_deck = client.post("/api/decks", json={"text": "Commander\n1x Krenko, Mob Boss\nDeck\n1x Worst Fears (tst) C00\n10x Island\n"}).json()["id"]
    bob_deck = client.post("/api/decks", json={"text": "Commander\n1x Atraxa, Praetors' Voice\nDeck\n1x Hidden Gem (tst) C03\n10x Island\n"}).json()["id"]
    game = client.post("/api/games", json={"mode": "lan", "shuffle": False, "automation": "full", "players": [
        {"name": "Alice", "deck_id": alice_deck}, {"name": "Bob", "deck_id": bob_deck}]}).json()
    gid, code, alice = game["game"]["id"], game["game"]["code"], game["seat"]["token"]
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    spec = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    tokens = {"p1": alice, "p2": bob}
    room = client.app.state.services.hub.get(gid)

    def post(token, action, **extra):
        return client.post(f"/api/games/{gid}/actions", json={"action": action, **extra}, headers={"X-Seat-Token": token})

    def ok(token, action):
        res = post(token, action)
        assert res.status_code == 200, res.text

    def view(token):
        return client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": token}).json()

    def drive_until(until):
        for _ in range(200):
            st = room.session.state
            if until(st):
                return
            d = st.rules.decision
            if d is None:
                ok(tokens[controller_of(st, st.rules.priority)], {"type": "pass_priority"})
            elif d.kind == "declare_attackers":
                ok(tokens[decider_of(st, d)], {"type": "declare_attackers", "attackers": []})
            else:
                ok(tokens[decider_of(st, d)], {"type": "choose", "decision_id": d.id, "option_ids": [o.id for o in d.options][: max(1, d.min_choices)]})
        raise AssertionError("never got there")

    ok(alice, {"type": "pass_priority"})  # → Alice's main phase
    st = room.session.state
    fears = next(c for c in st.cards.values() if c.name == "Worst Fears")
    ok(alice, {"type": "move", "card_ids": [fears.id], "to": {"zone": "hand"}})
    gem = next(c for c in st.cards.values() if c.name == "Hidden Gem")
    ok(bob, {"type": "move", "card_ids": [gem.id], "to": {"zone": "hand"}})
    ok(alice, {"type": "add_mana", "player": "p1", "mana": {"B": 2, "C": 10}})
    ok(alice, {"type": "cast_spell", "card_id": fears.id, "targets": ["p2"]})
    drive_until(lambda st: st.turn.number == 2 and st.turn.phase == "main1" and st.rules.decision is None)
    st = room.session.state
    assert st.rules.priority == "p2" and controller_of(st, "p2") == "p1"
    hand = cards_in(st, "p2", "hand")
    assert gem.id in {c.id for c in hand}
    repo = client.app.state.services.cards
    # Bob can't act: not a rules intent, not a table tool, not an undo, not by claiming another seat
    for action, extra in (({"type": "pass_priority"}, {}), ({"type": "draw"}, {}), ({"type": "pass_priority"}, {"as": "p1"}),
                          ({"type": "set_card_automation", "card_id": gem.id, "mode": "manual"}, {})):
        res = post(bob, action, **extra)
        assert res.status_code == 409, (action, res.text)
    assert client.post(f"/api/games/{gid}/undo", json={}, headers={"X-Seat-Token": bob}).status_code >= 400
    assert room.session.state.turn.number == 2 and room.session.state.rules.priority == "p2"
    # what each one sees: Alice sees Bob's hand (723.4); the spectator doesn't, neither in the view nor over the socket
    mine = view(alice)
    assert gem.id in mine["cards"] and not mine["cards"][gem.id].get("hidden")
    assert mine["rules"]["acting_as"] == "p2" and mine["rules"]["hints"]["has_priority"]
    bobs = view(bob)["rules"]
    assert bobs["controlled_by"] == "p1" and bobs["hints"] == {"has_priority": False} and "acting_as" not in bobs
    assert_hidden(view(spec), hand, repo)
    assert "acting_as" not in view(spec)["rules"]
    with client.websocket_connect(f"/ws/games/{gid}?token={bob}") as wb, client.websocket_connect(f"/ws/games/{gid}?token={spec}") as ws:
        wb.receive_json()
        assert_hidden(ws.receive_json()["view"], hand, repo)
        wb.send_json({"type": "action", "action": {"type": "pass_priority"}, "id": 7, "as": "p1"})
        for _ in range(5):
            msg = wb.receive_json()
            if msg.get("id") == 7:
                break
        assert msg["type"] == "error" and "controlling you" in msg["message"]
        ok(alice, {"type": "pass_priority"})  # Alice passes Bob's priority for him
        frame = ws.receive_json()
        assert frame["type"] == "state" and "acting_as" not in json.dumps(frame["view"]["rules"])
        assert_hidden(frame["view"], hand, repo)
    # 723.6: Bob still concedes for himself
    ok(bob, {"type": "concede"})
    assert "p2" in room.session.state.rules.conceded


# -- 723.1: the whole turn, and only that turn ------------------------------------------------------------------------------
def test_the_untap_choice_of_the_controlled_turn_is_the_controllers_and_the_next_turns_is_not(cards):
    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [(1, "Worst Fears"), (10, "Island")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(1, "Hidden Gem"), (1, "Sleepy Relic"), (10, "Island")])),
              PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(1, "Sleepy Relic"), (10, "Island")]))]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    gem = to_hand(s, "Hidden Gem", "p2")
    for c in [c for c in s.state.cards.values() if c.name == "Sleepy Relic"]:  # a "You may choose not to untap ~" permanent each
        act(s, "p1", type="move", card_ids=[c.id], to={"player": c.owner, "zone": "battlefield"})
    act(s, "p1", type="tap", card_ids=[c.id for c in s.state.cards.values() if c.name == "Sleepy Relic"], tapped=True)
    cast_on(s, "Worst Fears", "p2")
    drive(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get("step") == "untap_keep")
    d = s.state.rules.decision
    assert s.state.turn.active_player == "p2" and d.player == "p2" and d.decider == "p1"  # 723.1: the entire turn
    assert gem.id in seen_by(s, "p1")
    with pytest.raises(ActionError):
        act(s, "p2", type="choose", decision_id=d.id, option_ids=[])
    drive(s, lambda s: s.state.turn.active_player == "p3" and s.state.rules.decision is not None)
    d = s.state.rules.decision
    assert d.player == "p3" and d.decider is None and gem.id not in seen_by(s, "p1")  # over as Carol's turn begins
    roundtrip(s)


def test_a_turn_passed_by_hand_ends_the_control(cards):
    s = table(cards)
    gem = to_hand(s, "Hidden Gem", "p2")
    cast_on(s, "Worst Fears", "p2")
    bobs_turn(s)
    assert gem.id in seen_by(s, "p1")
    act(s, "p1", type="next_turn", force=True)  # a manual override: the table moved on, so did the turn
    assert s.state.turn.active_player == "p3"
    assert controller_of(s.state, "p2") == "p2" and gem.id not in seen_by(s, "p1")
    roundtrip(s)


# -- 800.4a: a controller who leaves -----------------------------------------------------------------------------------------
def test_a_controller_who_concedes_gives_the_pending_choice_back(cards):
    s = table(cards)
    from tests.test_rules_conditionals import creature

    creature(s, "p2", "Ox")
    gem = to_hand(s, "Hidden Gem", "p2")
    cast_on(s, "Worst Fears", "p2")
    bobs_turn(s)
    drive(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    d = s.state.rules.decision
    assert d.decider == "p1"
    act(s, "p1", type="concede")
    assert decider_of(s.state, s.state.rules.decision) == "p2" and gem.id not in seen_by(s, "p1")
    assert "controlled_by" not in rules_view(s.state, "p2", s.cards)
    act(s, "p2", type="declare_attackers", attackers=[])  # Bob decides again
    roundtrip(s)


# -- Opposition Agent on the other library searches ------------------------------------------------------------------------
def agent_table(cards):
    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [(1, "Opposition Agent"), (10, "Island")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(1, "Gifts Ungiven"), (1, "Hidden Gem"), (1, "Mindslaver"), (10, "Island")])),
              PlayerSetup("Carol", cards=deck(cards, "Krenko, Mob Boss", [(10, "Island")]))]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    agent = to_hand(s, "Opposition Agent", "p1")
    act(s, "p1", type="move", card_ids=[agent.id], to={"player": "p1", "zone": "battlefield"})
    drive(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "main1")
    return s


def test_opposition_agent_controls_and_exiles_a_gifts_ungiven_search(cards):
    s = agent_table(cards)
    gifts = to_hand(s, "Gifts Ungiven", "p2")
    found = [next(c for c in s.state.cards.values() if c.name == n and c.owner == "p2").id for n in ("Hidden Gem", "Mindslaver")]
    mana(s, "p2", U=1, C=3)
    act(s, "p2", type="cast_spell", card_id=gifts.id, targets=["p3"])
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d.player == "p2" and d.decider == "p1"
    with pytest.raises(ActionError):
        act(s, "p2", type="choose", decision_id=d.id, option_ids=found)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=found)
    drive(s, lambda s: not s.state.zones.get("stack") and s.state.rules.decision is None)
    assert [s.state.cards[c].zone for c in found] == ["p2:exile", "p2:exile"]  # exiled, never split into piles
    assert sorted(p.card for p in s.state.rules.permissions if p.player == "p1") == sorted(found)
    assert s.state.cards[gifts.id].zone == "p2:graveyard"
    roundtrip(s)


def test_the_controlled_players_hand_and_the_search_reach_nobody_else(cards):
    s = agent_table(cards)
    gifts = to_hand(s, "Gifts Ungiven", "p2")
    own = to_hand(s, "Hidden Gem", "p2")
    mana(s, "p2", U=1, C=3)
    act(s, "p2", type="cast_spell", card_id=gifts.id, targets=["p3"])
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    assert own.id in seen_by(s, "p1") and own.id not in seen_by(s, "p3") and own.id not in seen_by(s, SPECTATOR)
    assert rules_view(s.state, "p3", s.cards)["decision"]["prompt"] == "Alice (for Bob) is making a choice"


def test_opposition_agent_controls_a_name_search_of_ones_own_library(cards):
    from tests.test_rules_effects import token
    from tests.test_rules_wave11d_name_search import SURGICAL

    setups = [PlayerSetup("Alice", cards=deck(cards, "Krenko, Mob Boss", [(1, "Opposition Agent"), (10, "Island")])),
              PlayerSetup("Bob", cards=deck(cards, "Atraxa, Praetors' Voice", [(2, "Hidden Gem"), (10, "Island")]))]
    s = GameSession(enable(new_game(setups, shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")
    agent = next(c for c in s.state.cards.values() if c.name == "Opposition Agent")
    act(s, "p1", type="move", card_ids=[agent.id], to={"player": "p1", "zone": "battlefield"})
    src = token(s, "p2", "Extractor", "1/1", text=f"{{1}}: {SURGICAL}")
    while s.state.rules.priority != "p2":
        act(s, s.state.rules.priority, type="pass_priority")
    in_gy, in_library = [c for c in s.state.cards.values() if c.name == "Hidden Gem"]
    act(s, "p2", type="move", card_ids=[in_gy.id], to={"player": "p2", "zone": "graveyard"})
    act(s, "p2", type="move", card_ids=[in_library.id], to={"player": "p2", "zone": "library"})
    in_library = next(c for c in s.state.cards.values() if c.name == "Hidden Gem" and c.zone == "p2:library")  # (a new id there)
    mana(s, "p2", C=1)
    act(s, "p2", type="activate_ability", card_id=src.id, ability=0, targets=[in_gy.id])
    drive(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.resume.get("step") == "name_search")
    d = s.state.rules.decision
    assert d.player == "p2" and d.decider == "p1"  # 723.2: Bob searches his own library, so Alice chooses
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[in_gy.id, in_library.id])
    drive(s, lambda s: not s.state.zones.get("stack") and s.state.rules.decision is None)
    assert s.state.cards[in_gy.id].zone == "p2:exile" and s.state.cards[in_library.id].zone == "p2:exile"
    # "While an opponent is searching their library, they exile each card they find": one search of graveyard, hand and library together,
    # so every card found in it (name_search.finish)
    assert sorted(p.card for p in s.state.rules.permissions if p.player == "p1") == sorted([in_gy.id, in_library.id])
    roundtrip(s)
