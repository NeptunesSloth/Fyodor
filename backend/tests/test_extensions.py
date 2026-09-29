from __future__ import annotations

import json

from app.assistant import build_context
from app.game.actions import Draw
from app.rules import RulesRegistry, Suggestion
from tests.game_helpers import act, find, make_session


class LethalDamageSpotter:
    name = "demo"

    def after_action(self, state, action):
        return [Suggestion(module=self.name, message=f"{action.type} happened")]


class Broken:
    name = "broken"

    def after_action(self, state, action):
        raise RuntimeError("boom")


def test_rules_registry_is_advisory_and_isolated(cards):
    s = make_session(cards)
    registry = RulesRegistry()
    registry.register(LethalDamageSpotter())
    registry.register(Broken())
    before = s.state.model_dump_json()
    out = registry.after_action(s.state, Draw(actor="p1"))
    assert [x.message for x in out] == ["draw happened"]
    assert s.state.model_dump_json() == before


def test_assistant_context_contains_only_visible_information(cards):
    s = make_session(cards, shuffle=True)
    act(s, "p1", type="draw", count=7)
    act(s, "p2", type="draw", count=7)
    atraxa = find(s.state, "Atraxa, Praetors' Voice")
    act(s, "p2", type="move", card_ids=[atraxa.id], to={"zone": "battlefield"})
    ctx = build_context(s.view("p1"), cards)
    text = json.dumps(ctx)
    assert "Atraxa" in text and "proliferate" in text  # public card with oracle text
    for cid in s.state.zones["p2:hand"]:
        name = s.state.cards[cid].name
        if name not in ("Island",):  # appears nowhere public
            assert name not in text
    assert len(ctx["your_hand"]) == 7


def test_assistant_disabled_by_default(client):
    assert client.get("/api/health").json()["assistant_enabled"] is False
    deck = client.post("/api/decks", json={"text": "1 Sol Ring"}).json()["id"]
    gid = client.post("/api/games", json={"players": [{"name": "A", "deck_id": deck}]}).json()["game"]["id"]
    assert client.post(f"/api/games/{gid}/assistant", json={"question": "Can I respond?"}).status_code == 404


def test_assistant_receives_sanitized_context(client, monkeypatch):
    captured = {}

    class FakeAssistant:
        def ask(self, question, context):
            captured.update(question=question, context=context)
            return "Yes, you can respond."

    client.app.state.services.assistant = FakeAssistant()
    deck = client.post("/api/decks", json={"text": "1 Sol Ring\n20 Mountain"}).json()["id"]
    gid = client.post("/api/games", json={"players": [{"name": "A", "deck_id": deck}, {"name": "B", "deck_id": deck}]}).json()["game"]["id"]
    client.post(f"/api/games/{gid}/actions", json={"action": {"type": "draw", "count": 5}, "as": "p2"})
    res = client.post(f"/api/games/{gid}/assistant", json={"question": "Can I respond?", "viewer": "p1"})
    assert res.json() == {"answer": "Yes, you can respond."}
    assert captured["context"]["you"] == "A"
    assert captured["context"]["your_hand"] == []  # p2's drawn cards are not visible to p1
