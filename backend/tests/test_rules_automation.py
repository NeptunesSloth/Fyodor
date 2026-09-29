"""Automation levels (OFF / ASSISTED / FULL), per-feature options, dormant rules state,
reconciliation after manual play, per-card MANUAL, and ASSISTED confirmations."""

from __future__ import annotations

import json

import pytest

from app.game.errors import ActionError
from app.game.session import GameSession
from tests.game_helpers import act, enable, find, make_session, turn_on, zone
from tests.test_rules_combat import creature, table


def rules(s):
    return s.state.rules


def decision(s):
    return s.state.rules.decision


def test_levels_presets_and_custom_over_the_api(client):
    body = client.post("/api/games", json={"mode": "local", "automation": "assisted",
                                           "players": [{"name": "Alice"}, {"name": "Bob"}]}).json()
    gid = body["game"]["id"]
    view = client.get(f"/api/games/{gid}/view?viewer=p1").json()["rules"]
    assert view["automation"] == "assisted" and view["preset"] == "assisted"
    assert view["status"] == {"auto": "ASSISTED", "resp": "AUTO"}
    assert view["options"]["auto_sba"] is False and view["options"]["auto_priority_pass"] is True
    res = client.post(f"/api/games/{gid}/actions",
                      json={"action": {"type": "configure", "automation_options": {"auto_sba": True}}, "viewer": "p1"})
    assert res.status_code == 200, res.text
    view = client.get(f"/api/games/{gid}/view?viewer=p1").json()["rules"]
    assert view["preset"] == "custom" and view["options"]["auto_sba"] is True
    res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "configure", "automation": "full"}, "viewer": "p1"})
    view = client.get(f"/api/games/{gid}/view?viewer=p1").json()["rules"]
    assert view["preset"] == "full" and view["status"]["auto"] == "FULL"


def test_new_games_default_to_off(client):
    body = client.post("/api/games", json={"mode": "local", "players": [{"name": "Alice"}]}).json()
    view = client.get(f"/api/games/{body['game']['id']}/view?viewer=p1").json()
    assert view["game"]["settings"]["automation"] == "off" and "rules" not in view


def test_full_to_off_keeps_state_and_back_on_reconciles(cards):
    s = GameSession(enable(make_session(cards).state), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main 1
    act(s, "p1", type="draw", count=7)
    act(s, "p1", type="configure", automation="off")
    assert rules(s) is not None and rules(s).priority == "p1"  # nothing destroyed
    mountain = find(s.state, "Mountain", "p1")
    act(s, "p1", type="move", card_ids=[mountain.id], to={"zone": "battlefield"})  # a land played by hand
    assert rules(s).unsynced and "manual" not in json.dumps(s.view("p2")["log"][-1])
    act(s, "p1", type="configure", automation="full")
    assert not rules(s).unsynced and decision(s) is None  # nothing to ask: the table and its log say it all
    assert rules(s).lands_this_turn("p1", 1) == 1  # the land moved by hand counts as the land for the turn
    other = next(cid for cid in zone(s.state, "p1", "hand") if s.state.cards[cid].name == "Mountain")
    with pytest.raises(ActionError, match="already played a land"):
        act(s, "p1", type="play_land", card_id=other)


def test_turning_on_mid_game_asks_what_the_table_cannot_show(cards):
    s = table(cards)
    act(s, "p1", type="phase", to="main1")
    veteran = creature(s, "p1", "Veteran")
    rookie = creature(s, "p1", "Rookie")
    loner = creature(s, "p1", "Loner")
    act(s, "p1", type="configure", automation="full")
    d = decision(s)
    assert d.kind == "reconcile" and d.player == "p1"
    groups = {o.group for o in d.options}
    assert groups == {f"sick:{veteran.id}", f"sick:{rookie.id}", f"sick:{loner.id}", "land"}
    public = s.view("p2")["rules"]
    assert "options" not in public["decision"] and len(public["reconcile"]) == 4  # the list is public, answers aren't
    with pytest.raises(ActionError, match="each question once"):
        act(s, "p1", type="choose", decision_id=d.id,
            option_ids=[f"{veteran.id}:old", f"{veteran.id}:new", f"{rookie.id}:new", "land:no"])
    act(s, "p1", type="choose", decision_id=d.id,
        option_ids=[f"{veteran.id}:old", f"{rookie.id}:new", f"{loner.id}:manual", "land:yes"])
    r = rules(s)
    assert r.controlled_since[veteran.id].turn == 0 and r.controlled_since[rookie.id].turn == s.state.turn.number
    assert r.card_modes[loner.id] == "manual" and r.lands_this_turn("p1", s.state.turn.number) == 1
    assert r.reconcile == [] and r.priority == "p1"
    act(s, "p1", type="pass_priority")  # → declare attackers
    eligible = {o.id[2:] for o in decision(s).options if o.id.startswith("a:")}
    assert eligible == {veteran.id, loner.id}  # the rookie is summoning sick; the manual card isn't enforced


def test_pause_manual_changes_and_resume_cancels_a_stale_decision(cards):
    s = table(cards)
    turn_on(s)
    act(s, "p1", type="pass_priority")  # → main 1
    a = creature(s, "p1", "Twin", "2/2")
    a_type = {"name": "Twin", "type_line": "Legendary Token Creature — Test", "power": "2", "toughness": "2"}
    act(s, "p1", type="create_token", player="p1", token=a_type)
    act(s, "p1", type="create_token", player="p1", token=a_type)
    twins = [c for c in s.state.cards.values() if c.name == "Twin" and "Legendary" in (c.token.type_line if c.token else "")]
    act(s, "p1", type="pass_priority")  # SBA check: legend rule decision
    d = decision(s)
    assert d.kind == "choose_one" and "Legend rule" in d.prompt
    act(s, "p1", type="configure", automation_paused=True)
    act(s, "p1", type="delete_card", card_ids=[twins[0].id], force=True)  # solved by hand
    assert rules(s).unsynced
    act(s, "p1", type="configure", automation_paused=False)
    assert decision(s) is None and "no longer matched" in json.dumps(s.view("p1")["log"])
    assert a.id in s.state.cards


def test_card_automation_manual_resolves_by_hand(cards):
    s = GameSession(enable(make_session(cards).state), cards=cards)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="draw", count=7)
    ring = find(s.state, "Sol Ring", "p1")
    with pytest.raises(ActionError, match="controller"):
        act(s, "p2", type="set_card_automation", card_id=ring.id, mode="manual")
    act(s, "p1", type="set_card_automation", card_id=ring.id, mode="manual")
    assert s.view("p1")["rules"]["card_modes"] == {ring.id: "manual"}
    assert s.view("p2")["rules"]["card_modes"] == {}  # a card in Alice's hand: Bob learns nothing
    act(s, "p1", type="play_land", card_id=find(s.state, "Mountain", "p1").id)
    act(s, "p1", type="cast_spell", card_id=ring.id)  # normally just enters: now it resolves by hand
    d = decision(s)
    assert d.kind == "manual_resolution" and "Sol Ring" in d.prompt


def test_assisted_confirms_state_based_actions(cards):
    s = table(cards)
    bear = creature(s, "p1", "Bear", "2/2")
    turn_on(s, "assisted")
    act(s, "p1", type="pass_priority")  # → main 1
    act(s, "p1", type="set_damage", card_ids=[bear.id], delta=2)  # by hand
    act(s, "p1", type="pass_priority")
    d = decision(s)
    assert d.kind == "confirm" and "Bear dies (lethal damage)" in d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["no"])
    assert bear.id in s.state.cards and s.state.cards[bear.id].zone == "p1:battlefield"
    assert decision(s).kind == "declare_attackers"  # play went on; not asked again until something changes
    act(s, "p1", type="configure", automation_options={"auto_sba": True})
    act(s, "p1", type="declare_attackers", attackers=[])
    assert bear.id not in s.state.cards  # a token: died, then ceased to exist


def test_assisted_confirms_combat_damage(cards):
    s = table(cards)
    bear = creature(s, "p1", "Bear", "3/3")
    turn_on(s, "assisted")
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bear.id, "target": "p2"}])
    d = decision(s)
    while d is None or d.kind == "declare_blockers":
        if d is not None:
            act(s, "p2", type="declare_blockers", blocks=[])
        else:
            act(s, rules(s).priority, type="pass_priority")
        d = decision(s)
    assert d.kind == "confirm" and d.prompt == "Combat damage: Bear → Bob 3"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["yes"])
    assert s.state.players["p2"].life == 37
