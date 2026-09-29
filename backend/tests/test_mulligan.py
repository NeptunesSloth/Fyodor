"""Guided opening hands: policies, simultaneous decisions, exact bottoming, privacy, overrides."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.mulligan import BOSTON_CUSTOM, COMMANDER_LONDON, LONDON, resolve_policy, to_bottom
from app.game.session import GameSession
from app.game.state import GameSettings, MulliganPolicy
from tests.game_helpers import act, deck, zone


def session_with(cards, policy: MulliganPolicy | None, *, players: int = 2) -> GameSession:
    decks = [
        deck(cards, "Krenko, Mob Boss", [(1, "Sol Ring"), (1, "Lightning Bolt"), (1, "Llanowar Elves"), (1, "Fire // Ice"),
                                          (1, "Delver of Secrets"), (20, "Mountain")]),
        deck(cards, "Atraxa, Praetors' Voice", [(1, "Counterspell"), (1, "Arcane Signet"), (1, "Command Tower"),
                                                 (1, "Bonecrusher Giant"), (20, "Island")]),
        deck(cards, "Krenko, Mob Boss", [(24, "Mountain")]),
    ]
    setups = [PlayerSetup(name, cards=d) for name, d in zip(["Alice", "Bob", "Cara"], decks, strict=False)][:players]
    state = new_game(setups, name="T", settings=GameSettings(mulligan=policy), shuffle=True)
    return GameSession(state, cards=cards)


def seat(s, pid):
    return s.state.pregame.seats[pid]


def test_policies_are_data():
    assert to_bottom(LONDON, 0) == 0 and to_bottom(LONDON, 2) == 2
    assert to_bottom(COMMANDER_LONDON, 1) == 0 and to_bottom(COMMANDER_LONDON, 3) == 2
    assert resolve_policy("none") is None
    assert resolve_policy("boston_custom").needs_definition
    defined = resolve_policy("boston_custom", MulliganPolicy(display_name="Boston", set_aside_rejected_hands=True))
    assert defined.id == "boston_custom" and not defined.needs_definition and defined.set_aside_rejected_hands
    with pytest.raises(ValueError):
        resolve_policy("vancouver")


def test_opening_hands_are_dealt_and_nobody_needs_to_mulligan(cards):
    s = session_with(cards, COMMANDER_LONDON)
    assert all(len(zone(s.state, p, "hand")) == 7 for p in ("p1", "p2"))
    act(s, "p1", type="mulligan_keep")
    assert seat(s, "p1").status == "kept" and not s.state.pregame.finished
    act(s, "p2", type="mulligan_keep")
    assert s.state.pregame.finished
    assert "Everyone has kept" in json.dumps(s.view("p1")["log"])
    assert s.view("p1")["pregame"] is None


def test_commander_london_first_mulligan_is_free_then_bottom_exactly_n(cards):
    s = session_with(cards, COMMANDER_LONDON)
    first_hand = set(zone(s.state, "p1", "hand"))
    act(s, "p1", type="mulligan_take")
    assert len(zone(s.state, "p1", "hand")) == 7 and not first_hand & set(zone(s.state, "p1", "hand"))  # re-keyed ids
    act(s, "p1", type="mulligan_take")
    act(s, "p1", type="mulligan_take")
    act(s, "p1", type="mulligan_keep")
    assert seat(s, "p1").status == "bottoming" and seat(s, "p1").to_bottom == 2
    hand = list(zone(s.state, "p1", "hand"))
    for wrong in (hand[:1], hand[:3], [hand[0], hand[0]]):
        with pytest.raises(ActionError, match="exactly 2|own hand"):
            act(s, "p1", type="mulligan_bottom", card_ids=wrong)
    # someone else can't choose for Alice
    with pytest.raises(ActionError, match="own mulligan"):
        act(s, "p2", type="mulligan_bottom", player="p1", card_ids=hand[:2])
    act(s, "p1", type="mulligan_bottom", card_ids=[hand[4], hand[1]])
    lib = zone(s.state, "p1", "library")
    assert lib[-2:] == [hand[4], hand[1]]  # in the order chosen
    assert len(zone(s.state, "p1", "hand")) == 5 and seat(s, "p1").kept == 5
    assert s.state.players["p1"].mulligans == 3


def test_london_every_mulligan_counts_and_decisions_are_independent(cards):
    s = session_with(cards, LONDON, players=3)
    act(s, "p1", type="mulligan_take")
    act(s, "p1", type="mulligan_keep")  # Alice bottoms 1 ...
    act(s, "p3", type="mulligan_keep")  # ... while Cara already kept and Bob is still thinking
    view = s.view("p2")["pregame"]["seats"]
    assert view["p1"] == {"status": "bottoming", "mulligans": 1, "to_bottom": 1, "kept": None}
    assert view["p2"]["status"] == "deciding" and view["p3"]["status"] == "kept"
    act(s, "p2", type="mulligan_keep")
    assert not s.state.pregame.finished
    act(s, "p1", type="mulligan_bottom", card_ids=[zone(s.state, "p1", "hand")[0]])
    assert s.state.pregame.finished


def test_opponents_learn_counts_but_never_which_cards(cards):
    s = session_with(cards, LONDON)
    act(s, "p1", type="mulligan_take")
    act(s, "p1", type="mulligan_take")
    act(s, "p1", type="mulligan_keep")
    hand = list(zone(s.state, "p1", "hand"))
    bottomed = [s.state.cards[hand[0]], s.state.cards[hand[1]]]
    act(s, "p1", type="mulligan_bottom", card_ids=hand[:2])
    for viewer in ("p2", "__spectator__"):
        v = s.view(viewer)
        text = json.dumps(v)
        assert "kept 7 and put 2 cards on the bottom" in text
        for c in bottomed + [s.state.cards[i] for i in zone(s.state, "p1", "hand")]:
            assert c.id not in text
        assert v["zones"]["p1:library"]["known"] == []
    # Alice herself doesn't get to keep tracking what she bottomed: it's library now
    assert s.view("p1")["zones"]["p1:library"]["known"] == []


def test_undo_and_redo_replay_the_same_hands(cards):
    s = session_with(cards, LONDON)
    act(s, "p1", type="mulligan_take")
    hand = [s.state.cards[i].name for i in zone(s.state, "p1", "hand")]
    s.undo("p1")
    assert seat(s, "p1").mulligans == 0
    s.redo("p1")
    assert [s.state.cards[i].name for i in zone(s.state, "p1", "hand")] == hand


def test_undefined_boston_slot_refuses_to_guess(cards):
    s = session_with(cards, BOSTON_CUSTOM)
    assert "not defined yet" in json.dumps(s.view("p1")["log"])
    with pytest.raises(ActionError, match="isn't defined yet"):
        act(s, "p1", type="mulligan_take")
    act(s, "p1", type="mulligan_keep")  # keeping 7 is always possible


def test_configured_custom_policy_set_aside_partial_and_final_shuffle(cards):
    policy = resolve_policy("boston_custom", MulliganPolicy(
        display_name="Boston (Custom Pod)", partial_hand_selection=True, set_aside_rejected_hands=True,
        final_shuffle=True, cards_to_bottom=0, max_mulligans=2))
    s = session_with(cards, policy)
    lib_before = len(zone(s.state, "p1", "library"))
    hand = list(zone(s.state, "p1", "hand"))
    act(s, "p1", type="mulligan_take", card_ids=hand[:3])  # send back three, draw three
    assert len(zone(s.state, "p1", "hand")) == 7
    assert sorted(zone(s.state, "p1", "setaside")) == sorted(hand[:3])
    assert len(zone(s.state, "p1", "library")) == lib_before - 3
    # the set-aside cards are private to Alice
    bob = s.view("p2")
    assert all(i not in json.dumps(bob) for i in hand[:3])
    assert len(bob["zones"]["p1:setaside"]) == 3
    assert all(s.view("p1")["cards"][i]["name"] for i in hand[:3])
    act(s, "p1", type="mulligan_take", card_ids=[zone(s.state, "p1", "hand")[0]])
    with pytest.raises(ActionError, match="No more mulligans"):
        act(s, "p1", type="mulligan_take", card_ids=[zone(s.state, "p1", "hand")[0]])
    act(s, "p1", type="mulligan_keep")
    assert zone(s.state, "p1", "setaside") == []
    assert len(zone(s.state, "p1", "library")) == lib_before  # shuffled back in
    assert "4 set-aside cards were shuffled" in json.dumps(s.view("p2")["log"])


def test_partial_selection_only_when_the_policy_allows_it(cards):
    s = session_with(cards, LONDON)
    with pytest.raises(ActionError, match="whole hand"):
        act(s, "p1", type="mulligan_take", card_ids=[zone(s.state, "p1", "hand")[0]])


def test_minimum_hand_size(cards):
    s = session_with(cards, LONDON.model_copy(update={"minimum_hand_size": 6}))
    act(s, "p1", type="mulligan_take")  # would keep 6
    with pytest.raises(ActionError, match="fewer than 6"):
        act(s, "p1", type="mulligan_take")


def test_host_override_ends_the_phase(cards):
    s = session_with(cards, LONDON)
    act(s, "p1", type="mulligan_take")
    act(s, "p1", type="mulligan_keep")
    act(s, "p2", type="mulligan_finish")
    assert s.state.pregame.finished and seat(s, "p1").status == "kept" and seat(s, "p1").kept == 7
    assert "started the game (Alice, Bob kept what they held)" in json.dumps(s.view("p1")["log"])
    with pytest.raises(ActionError, match="already settled"):
        act(s, "p1", type="mulligan_keep")


def test_no_policy_means_sandbox(cards):
    s = session_with(cards, None)
    assert s.state.pregame is None and zone(s.state, "p1", "hand") == []
    with pytest.raises(ActionError, match="already settled"):
        act(s, "p1", type="mulligan_keep")
    act(s, "p1", type="draw", count=7)
    act(s, "p1", type="mulligan")  # the manual action still works


# ------------------------------------------------------------------------------------------ API


def test_api_mulligan_rules_and_host_only_override(client):
    res = client.post("/api/games", json={"mode": "local", "players": [{"name": "A"}], "mulligan_rule": "boston_custom"})
    assert res.status_code == 422 and "Define" in res.json()["detail"]
    res = client.post("/api/games", json={"mode": "local", "players": [{"name": "A"}], "mulligan_rule": "nope"})
    assert res.status_code == 422

    body = client.post("/api/games", json={"mode": "lan", "lobby": True, "players": [{"name": "Alice"}],
                                            "mulligan_rule": "boston_custom"}).json()
    gid, code, alice = body["game"]["id"], body["game"]["code"], body["seat"]["token"]
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    lobby = client.get(f"/api/games/{gid}/lobby", headers={"X-Seat-Token": alice}).json()
    assert lobby["mulligan"]["needs_definition"]
    assert any("Boston (Custom Pod) mulligan isn't defined" in b for b in lobby["start_blockers"])
    definition = {"display_name": "Boston (Custom Pod)", "free_mulligans": 1, "set_aside_rejected_hands": True}
    res = client.post(f"/api/games/{gid}/lobby/settings", json={"mulligan_policy": definition}, headers={"X-Seat-Token": alice})
    assert res.status_code == 200 and not res.json()["mulligan"]["needs_definition"]
    assert not any("mulligan" in b for b in res.json()["start_blockers"])
    assert client.post(f"/api/games/{gid}/lobby/start", json={"force": True}, headers={"X-Seat-Token": alice}).status_code == 200
    view = client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": bob}).json()
    assert view["game"]["settings"]["mulligan"]["set_aside_rejected_hands"]
    assert view["game"]["host_seat"] == "p1"
    finish = {"action": {"type": "mulligan_finish"}}
    assert client.post(f"/api/games/{gid}/actions", json=finish, headers={"X-Seat-Token": bob}).status_code == 403
    assert client.post(f"/api/games/{gid}/actions", json=finish, headers={"X-Seat-Token": alice}).status_code == 200
