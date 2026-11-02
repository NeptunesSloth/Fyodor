"""REPEAT LAST VALIDATED SEQUENCE, EXPORT RULES SCENARIO, and containment of rules-engine bugs."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.game.errors import ActionError, AutomationError
from app.rules import engine as rules_engine
from app.rules import scenario
from tests.game_helpers import act, find, turn_on
from tests.test_rules_combat import table


def pool(s, pid="p1"):
    p = s.state.players[pid]
    return sum(p.mana.values()) + len(p.mana_units)  # (mana remembered by source is in the pool too)


def fountain(s):
    """A test permanent with a free, repeatable mana ability (a stand-in for a combo piece)."""
    act(s, "p1", type="create_token", player="p1",
        token={"name": "Fountain", "type_line": "Token Artifact", "text": "{0}: Add {C}."})
    return find(s.state, "Fountain", "p1")


def test_repeat_last_sequence_uses_the_engine_every_time(cards):
    s = table(cards)
    turn_on(s)
    act(s, "p1", type="pass_priority")
    f = fountain(s)
    act(s, "p1", type="activate_ability", card_id=f.id, ability=0)  # done once by hand
    assert pool(s) == 1
    seq = s.state.seq
    act(s, "p1", type="repeat_sequence", count=1, times=9)
    assert pool(s) == 10 and s.state.seq == seq + 1  # one history entry for the whole repeat
    log = s.view("p1")["log"]
    assert "repeated the sequence ×9" in json.dumps(log[-1], ensure_ascii=False)
    assert sum(1 for e in log if e.get("folded")) >= 9  # the nine iterations fold under the summary line
    s.undo("p1")
    assert pool(s) == 1  # undone as one


def test_repeat_until_a_condition(cards):
    s = table(cards)
    turn_on(s)
    act(s, "p1", type="pass_priority")
    f = fountain(s)
    act(s, "p1", type="activate_ability", card_id=f.id, ability=0)
    act(s, "p1", type="repeat_sequence", count=1, times=500, until={"kind": "mana", "value": 30})
    assert pool(s) == 30
    assert "stopped: the condition was reached" in json.dumps(s.view("p1")["log"][-1], ensure_ascii=False)


def test_repeat_stops_when_an_iteration_is_no_longer_legal(cards):
    s = table(cards)
    turn_on(s)
    act(s, "p1", type="pass_priority")
    forest = find(s.state, "Forest", "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "battlefield"})
    act(s, "p1", type="activate_ability", card_id=forest.id, ability=0)  # {T}: Add {G}
    with pytest.raises(ActionError, match="can't be repeated: Forest is tapped"):
        act(s, "p1", type="repeat_sequence", count=1, times=3)
    assert pool(s) == 1  # nothing applied
    with pytest.raises(ActionError, match="once first"):
        act(s, "p1", type="repeat_sequence", count=5)


def well(s):
    """A stand-in combo piece with a choice in it: "you may pay {1}. If you do, you gain 1 life" (an optional payment, 118.12)."""
    act(s, "p1", type="create_token", player="p1",
        token={"name": "Well", "type_line": "Token Artifact", "text": "{0}: You may pay {1}. If you do, you gain 1 life."})
    return find(s.state, "Well", "p1")


def answer_pay(s):
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])


def test_repeat_replays_the_choices_made_the_first_time(cards):
    """REPEAT with a choice in the loop: each iteration gets the same answer the player gave (here "Pay {1}"), checked by the engine
    like a click; the Repeat panel lists the player's own actions in words, and only to them."""
    s = table(cards)
    turn_on(s)
    act(s, "p1", type="pass_priority")
    f, w = fountain(s), well(s)
    life = s.state.players["p1"].life
    act(s, "p1", type="activate_ability", card_id=f.id, ability=0)  # add {C}
    act(s, "p1", type="activate_ability", card_id=w.id, ability=0)  # you may pay {1} …
    answer_pay(s)
    assert s.state.players["p1"].life == life + 1 and pool(s) == 0
    labels = s.view("p1")["rules"]["repeatable"]
    assert labels[-3:] == ["Activate Fountain", "Activate Well", "Choose: Pay {1}"]
    assert s.view("p2")["rules"]["repeatable"] == []  # (nobody else's)
    act(s, "p1", type="repeat_sequence", count=3, times=5)
    assert s.state.players["p1"].life == life + 6 and pool(s) == 0 and s.state.rules.decision is None
    assert "repeated the sequence ×5" in json.dumps(s.view("p1")["log"][-1], ensure_ascii=False)
    s.undo("p1")
    assert s.state.players["p1"].life == life + 1  # undone as one


def test_repeat_stops_when_the_choice_made_the_first_time_doesnt_come_up(cards):
    s = table(cards)
    turn_on(s)
    act(s, "p1", type="pass_priority")
    f, w = fountain(s), well(s)
    act(s, "p1", type="activate_ability", card_id=f.id, ability=0)
    act(s, "p1", type="activate_ability", card_id=w.id, ability=0)
    answer_pay(s)
    with pytest.raises(ActionError, match="choice from the first time didn't come up"):  # (without the Fountain's {C}: nothing to pay with)
        act(s, "p1", type="repeat_sequence", count=2, times=3)
    with pytest.raises(ActionError, match="Start the sequence with an action"):
        act(s, "p1", type="repeat_sequence", count=1, times=3)


def test_scenario_export_redacts_and_replays(cards):
    s = table(cards)
    turn_on(s)
    act(s, "p1", type="pass_priority")
    f = fountain(s)
    act(s, "p1", type="activate_ability", card_id=f.id, ability=0)
    data = scenario.export(s, cards)
    assert data["format"] == "fyodor-rules-scenario" and data["build"]["rules_engine_version"] >= 2
    assert [a["type"] for a in data["actions"]] == ["activate_ability"]
    hidden = [c for c in data["state"]["cards"].values() if c["zone"].endswith(":library")]
    assert hidden and all(c["name"] == "" and c["card_id"] is None for c in hidden)  # redacted
    assert data["state"]["log"] == [] and data["state"]["hidden_salt"] == s.state.hidden_salt  # (renumbering replays from it)
    assert scenario.replay(json.loads(json.dumps(data)), cards) == []  # the current engine agrees


def test_scenario_export_endpoint_is_a_developer_tool(client, monkeypatch):
    body = client.post("/api/games", json={"mode": "local", "automation": "full",
                                           "players": [{"name": "Alice"}, {"name": "Bob"}]}).json()
    gid = body["game"]["id"]
    assert client.get(f"/api/games/{gid}/rules/scenario").status_code == 403  # off unless FYODOR_DEV_TOOLS=1
    services = client.app.state.services
    monkeypatch.setattr(services, "settings", replace(services.settings, dev_tools=True))
    res = client.get(f"/api/games/{gid}/rules/scenario")
    assert res.status_code == 200 and "attachment" in res.headers["content-disposition"]
    assert res.json()["format"] == "fyodor-rules-scenario"


def test_an_engine_bug_changes_nothing_and_is_reported(cards, monkeypatch):
    s = table(cards)
    turn_on(s)
    before = s.state.model_dump(mode="json")

    def broken(plan, intent):
        raise KeyError("oops")

    monkeypatch.setitem(rules_engine.INTENTS, "pass_priority", broken)
    with pytest.raises(AutomationError, match="AUTOMATION ERROR.*Nothing changed"):
        act(s, "p1", type="pass_priority")
    assert s.state.model_dump(mode="json") == before
    assert s.rules_failure["intent"]["type"] == "pass_priority" and "KeyError" in s.rules_failure["error"]
    assert s.view("p2")["rules"]["failure"]["intent"] == "pass_priority"
    act(s, "p1", type="configure", automation_paused=True)  # the table goes on by hand
    act(s, "p1", type="draw")
