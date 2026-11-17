"""Milestone 14: the rules-engine boundary.

Intents are compiled into ordinary table actions and recorded as one history entry; priority,
stops and the turn structure run by themselves; decisions go to one player; unsupported effects
fall back to manual resolution; sandbox actions stay available and are logged as overrides.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.game.errors import ActionError
from app.game.session import GameSession
from tests.game_helpers import act, enable, find, make_session, turn_on, zone


@pytest.fixture()
def s(cards):
    state = make_session(cards).state
    enable(state)
    return GameSession(state, cards=cards)  # like the API: automation is set before play starts


def rules(s):
    return s.state.rules


def to_main(s):
    """From the start of turn 1, one pass by the active player runs to their first main phase."""
    act(s, "p1", type="pass_priority")
    assert (s.state.turn.number, s.state.turn.phase, rules(s).priority) == (1, "main1", "p1")


def test_intents_are_refused_at_sandbox_tables(cards):
    sandbox = make_session(cards)
    with pytest.raises(ActionError, match="automation is off"):
        act(sandbox, "p1", type="pass_priority")
    with pytest.raises(ActionError, match="Only the rules engine"):
        act(sandbox, "p1", type="rules_sync", rules=None)
    with pytest.raises(ActionError, match="Only the rules engine"):
        act(sandbox, "p1", type="rules_log", text="forged")


def test_turn_one_runs_to_main_phase_skipping_the_first_draw(s):
    to_main(s)
    log = json.dumps(s.view("p1")["log"])
    assert "skips the first draw" in log and zone(s.state, "p1", "hand") == []
    assert s.state.seq == 1  # the whole run through untap, upkeep and draw is one history entry


def test_play_land_follows_the_rules(s):
    to_main(s)
    act(s, "p1", type="draw", count=7)  # sandbox action: allowed, logged as an override
    mountain = find(s.state, "Mountain", "p1")
    sol = find(s.state, "Sol Ring", "p1")
    with pytest.raises(ActionError, match="isn't a land"):
        act(s, "p1", type="play_land", card_id=sol.id)
    with pytest.raises(ActionError, match="from your hand"):
        act(s, "p2", type="play_land", card_id=mountain.id)  # not Bob's card
    act(s, "p2", type="draw", count=7)
    with pytest.raises(ActionError, match="your own turn"):
        act(s, "p2", type="play_land", card_id=find(s.state, "Island", "p2").id)
    act(s, "p1", type="play_land", card_id=mountain.id)
    assert s.state.cards[mountain.id].zone == "p1:battlefield"
    assert "played" in json.dumps(s.view("p2")["log"])
    other = next(cid for cid in zone(s.state, "p1", "hand") if s.state.cards[cid].name == "Mountain")
    with pytest.raises(ActionError, match="already played a land"):
        act(s, "p1", type="play_land", card_id=other)
    assert rules(s).priority == "p1"  # a land doesn't use the stack: you keep priority


def test_land_only_in_your_main_phase_with_an_empty_stack(s):
    act(s, "p1", type="draw", count=7)
    mountain = find(s.state, "Mountain", "p1")
    with pytest.raises(ActionError, match="main phase"):
        act(s, "p1", type="play_land", card_id=mountain.id)  # still in the untap step


def test_passing_runs_the_turn_with_stops_and_draws_for_the_next_player(s):
    to_main(s)
    act(s, "p1", type="pass_priority")
    assert s.state.turn.phase == "main2" and rules(s).priority == "p1"  # own stop
    hand_before = len(zone(s.state, "p2", "hand"))
    act(s, "p1", type="pass_priority")
    st = s.state
    assert (st.turn.number, st.turn.active_player, st.turn.phase) == (2, "p2", "main1")
    assert len(zone(st, "p2", "hand")) == hand_before + 1  # draw step
    assert rules(s).priority == "p2"
    with pytest.raises(ActionError, match="priority"):
        act(s, "p1", type="pass_priority")


def test_custom_stops(s):
    act(s, "p2", type="set_stops", own=["upkeep", "main1"], others=["end"])
    to_main(s)
    act(s, "p1", type="pass_priority")  # → main2
    act(s, "p1", type="pass_priority")  # → end step: Bob asked to stop there
    assert (s.state.turn.phase, rules(s).priority) == ("end", "p2")
    act(s, "p2", type="pass_priority")
    assert (s.state.turn.active_player, s.state.turn.phase, rules(s).priority) == ("p2", "upkeep", "p2")
    with pytest.raises(ValidationError):
        act(s, "p1", type="set_stops", own=["nonsense"])


def test_discard_to_hand_size_is_a_private_decision(s):
    to_main(s)
    act(s, "p1", type="draw", count=9)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="pass_priority")  # → cleanup: 9 cards in hand
    d = rules(s).decision
    assert d and d.player == "p1" and d.kind == "choose_cards" and d.min_choices == d.max_choices == 2
    hand = list(zone(s.state, "p1", "hand"))
    mine = s.view("p1")["rules"]["decision"]
    theirs = s.view("p2")["rules"]["decision"]
    assert {o["card_id"] for o in mine["options"]} == set(hand)
    assert "options" not in theirs and theirs["player"] == "p1" and theirs["kind"] == "waiting"
    assert theirs["public"] == {"type": "PLAYER_MAKING_CHOICE", "chooser": "Alice"}  # only who is choosing
    bob_view = json.dumps(s.view("p2"))
    assert not any(cid in bob_view for cid in hand)  # Alice's hand stays hidden from Bob
    with pytest.raises(ActionError, match="Waiting for Alice"):
        act(s, "p2", type="pass_priority")
    with pytest.raises(ActionError, match="Choose 2"):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=hand[:1])
    with pytest.raises(ActionError, match="Alice's decision"):
        act(s, "p2", type="choose", decision_id=d.id, option_ids=hand[:2])
    act(s, "p1", type="choose", decision_id=d.id, option_ids=hand[:2])
    assert set(hand[:2]) <= set(zone(s.state, "p1", "graveyard"))
    assert len(zone(s.state, "p1", "hand")) == 7
    assert (s.state.turn.active_player, s.state.turn.phase) == ("p2", "main1")


def test_unsupported_effects_resolve_by_hand(s):
    to_main(s)
    act(s, "p1", type="draw", count=7)
    bolt = find(s.state, "Lightning Bolt", "p1")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "stack"})  # cast by hand (M14)
    assert rules(s).overrides == 2
    entry = s.view("p2")["log"][-1]
    assert entry.get("manual") is True
    act(s, "p2", type="set_stops", smart_pass=False)  # Bob wants a say even with nothing to cast
    act(s, "p1", type="pass_priority")
    assert rules(s).priority == "p2"  # something on the stack: Bob really gets priority
    act(s, "p2", type="pass_priority")
    d = rules(s).decision
    assert d and d.kind == "manual_resolution" and d.player == "p1" and "Lightning Bolt" in d.prompt
    assert s.state.cards[bolt.id].zone == "p1:graveyard"
    # the sandbox keeps working while resolving by hand
    act(s, "p1", type="life", player="p2", delta=-3)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["done"])
    assert rules(s).decision is None and rules(s).priority == "p1" and s.state.players["p2"].life == 37


def test_a_manual_step_change_is_picked_up(s):
    to_main(s)
    act(s, "p1", type="phase", to="end")  # override: jump to the end step by hand
    act(s, "p1", type="pass_priority")
    assert (s.state.turn.active_player, s.state.turn.phase) == ("p2", "main1")


def test_undo_takes_back_a_whole_intent_and_replay_matches(s):
    to_main(s)
    act(s, "p1", type="draw", count=7)
    act(s, "p1", type="play_land", card_id=find(s.state, "Mountain", "p1").id)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="pass_priority")
    live = s.state.model_dump(mode="json")
    assert s.history.rebuild().model_dump(mode="json") == live  # replaying the recorded steps
    s.undo("p1")
    assert (s.state.turn.number, s.state.turn.phase) == (1, "main2") and rules(s).priority == "p1"
    s.redo("p1")
    assert s.state.model_dump(mode="json") == live


def test_host_can_pause_and_turn_automation_off(s):
    act(s, "p1", type="configure", automation_paused=True)
    with pytest.raises(ActionError, match="paused"):
        act(s, "p1", type="pass_priority")
    act(s, "p1", type="draw")  # the sandbox still works
    act(s, "p1", type="configure", automation_paused=False)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="configure", automation="off")
    assert s.state.rules is not None and "rules" not in s.view("p1")  # dormant, not destroyed


def test_turning_automation_on_mid_game(cards):
    sandbox = make_session(cards)
    act(sandbox, "p1", type="draw", count=7)
    act(sandbox, "p1", type="move", card_ids=[find(sandbox.state, "Llanowar Elves", "p1").id], to={"zone": "battlefield"})
    turn_on(sandbox)
    r = sandbox.state.rules
    assert r is not None and r.priority == "p1" and sandbox.state.settings.priority_helper == "off"
    elves = find(sandbox.state, "Llanowar Elves", "p1")
    assert r.controlled_since[elves.id].turn == 0  # already there: not summoning sick


def test_concede(s):
    to_main(s)
    act(s, "p2", type="concede")
    assert "p2" in rules(s).conceded and "last player standing" in json.dumps(s.view("p1")["log"])
    with pytest.raises(ActionError, match="left this game"):
        act(s, "p2", type="pass_priority")


def test_not_yet_automated_parts_explain_themselves(s):
    to_main(s)
    with pytest.raises(ActionError, match="declare attackers step"):
        act(s, "p1", type="declare_attackers", attackers=[])  # not in the declare attackers step
    krenko = find(s.state, "Krenko, Mob Boss", "p1")
    act(s, "p1", type="move", card_ids=[krenko.id], to={"zone": "battlefield"})
    with pytest.raises(ActionError, match="summoning sickness"):
        act(s, "p1", type="activate_ability", card_id=krenko.id, ability=0)  # {T} the turn it arrived


def test_hints_are_only_about_your_own_cards(s):
    to_main(s)
    act(s, "p1", type="draw", count=7)
    act(s, "p2", type="draw", count=7)
    alice = s.view("p1")["rules"]["hints"]
    bob = s.view("p2")["rules"]["hints"]
    assert alice["has_priority"] and set(alice["playable_lands"]) <= set(zone(s.state, "p1", "hand"))
    assert alice["playable_lands"] and bob == {"has_priority": False}


def test_rules_tables_over_the_api(client):
    body = client.post("/api/games", json={"mode": "local", "automation": "full",
                                           "players": [{"name": "Alice"}, {"name": "Bob"}]}).json()
    gid = body["game"]["id"]
    view = client.get(f"/api/games/{gid}/view?viewer=p1").json()
    assert view["rules"]["automation"] == "full" and view["rules"]["priority"] == "p1"
    assert view["game"]["settings"]["automation"] == "full"
    # S7: nobody gets priority in the untap step (502.4): a new game is in its first main phase already, before any action
    assert view["turn"]["phase"] == "main1"
    res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "pass_priority"}, "viewer": "p1"})
    assert res.status_code == 200, res.text
    assert res.json()["turn"]["phase"] == "main2"
    forged = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "rules_sync", "rules": None}, "viewer": "p1"})
    assert forged.status_code in (409, 422)


def test_lan_lobby_can_turn_automation_on(client):
    res = client.post("/api/games", json={"mode": "lan", "lobby": True, "automation": "full", "players": [{"name": "Alice"}]})
    assert res.status_code == 201
    lobby = client.get(f"/api/games/{res.json()['game']['id']}/lobby", headers={"X-Seat-Token": res.json()["seat"]["token"]}).json()
    assert lobby["settings"]["automation"] == "full"
