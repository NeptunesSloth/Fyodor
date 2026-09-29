"""Protocol-level hidden-information tests.

These inspect the exact JSON an opponent/spectator receives over REST and WebSocket, and
assert that nothing identifying a hidden card is present: not the name, printing id,
oracle id, oracle text, set/collector number, image reference, note, categories, or even
the card's real instance id.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.game.state import CardInstance

P1_DECK = """Commander
1x Atraxa, Praetors' Voice (2x2) 190 [Commander{top}]
Deck
1x Counterspell (cmm) 81 [Interaction]
1x Swords to Plowshares (sta) 10 [Removal]
1x Opt (eld) 59 [Cantrip]
1x Delver of Secrets // Insectile Aberration (isd) 51 [Threat]
1x Sol Ring (cmm) 410 [Ramp]
10x Island (cmm) 1001 [Land]
"""
P2_DECK = """Commander
1x Krenko, Mob Boss (ddn) 13
Deck
12x Mountain (cmm) 1003
1x Lightning Bolt (clb) 187
"""
HIDDEN_KEYS = {"id", "hidden", "owner", "controller", "zone", "face_down"}


@pytest.fixture()
def table(client):
    a = client.post("/api/decks", json={"text": P1_DECK}).json()["id"]
    b = client.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    game = client.post("/api/games", json={
        "mode": "lan", "shuffle": True,
        "players": [{"name": "Alice", "deck_id": a}, {"name": "Bob", "deck_id": b}],
    }).json()
    gid, code = game["game"]["id"], game["game"]["code"]
    alice = game["seat"]["token"]
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    spec = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    return client, gid, alice, bob, spec


def act(client, gid, token, action):
    res = client.post(f"/api/games/{gid}/actions", json={"action": action}, headers={"X-Seat-Token": token})
    assert res.status_code == 200, res.text
    return res.json()


def view(client, gid, token):
    return client.get(f"/api/games/{gid}/view", headers={"X-Seat-Token": token}).json()


def fingerprints(card: CardInstance, cards_repo) -> list[str]:
    """Every string that would identify this card."""
    out = [card.id, card.name]
    if card.card_id:
        data = cards_repo.get(card.card_id)
        out += [card.card_id, data["oracle_id"], f"/api/images/{card.card_id}"]
        out += [f["name"] for f in data["faces"]]
        text = (data.get("oracle_text") or "").split("\n")[0]
        if len(text) > 12:
            out.append(text[:40])
    if card.note:
        out.append(card.note)
    out += card.categories
    return [x for x in out if x]


def assert_hidden(payload: dict[str, Any], hidden: list[CardInstance], cards_repo, *, include_log: bool = True) -> None:
    body = payload if include_log else {k: v for k, v in payload.items() if k != "log"}
    text = json.dumps(body)
    for c in hidden:
        for token in fingerprints(c, cards_repo):
            assert token not in text, f"{token!r} of hidden {c.name} leaked"
    # generic: views never carry printing metadata or image references at all
    for forbidden in ('"set_code"', '"collector_number"', '"oracle_id"', '"image_uris"', "scryfall", '"oracle_text"'):
        assert forbidden not in text
    # every hidden object is an opaque placeholder with a fixed, minimal key set
    for card_view in body.get("cards", {}).values():
        if card_view.get("hidden") and card_view["zone"].split(":")[1] in ("hand", "sideboard", "foretell"):
            assert set(card_view) == HIDDEN_KEYS


def state_of(client, gid):
    return client.app.state.services.hub.get(gid).session.state


def cards_in(state, pid, zone_name):
    return [state.cards[i] for i in state.zones[f"{pid}:{zone_name}"]]


def test_hidden_hands_libraries_and_searches_do_not_leak(table):
    client, gid, alice, bob, spec = table
    repo = client.app.state.services.cards
    act(client, gid, alice, {"type": "draw", "count": 5})
    act(client, gid, bob, {"type": "draw", "count": 5})
    state = state_of(client, gid)
    alice_hidden = cards_in(state, "p1", "hand") + cards_in(state, "p1", "library") + cards_in(state, "p1", "sideboard")
    # Alice looks at her top 3 and searches her library: private to Alice
    act(client, gid, alice, {"type": "look_top", "count": 3})
    act(client, gid, alice, {"type": "search_start", "zone": {"zone": "library"}})
    for token in (bob, spec):
        payload = view(client, gid, token)
        assert_hidden(payload, alice_hidden, repo, include_log=False)
        assert payload["searches"] == {"p1": "p1:library"}
        assert "my_views" in payload and payload["my_views"] == []
    mine = view(client, gid, alice)
    assert mine["zones"]["p1:library"]["count"] == len(mine["zones"]["p1:library"]["known"])  # searching
    act(client, gid, alice, {"type": "search_end", "shuffle": True})
    state = state_of(client, gid)
    alice_hidden = cards_in(state, "p1", "hand") + cards_in(state, "p1", "library")
    for token in (bob, spec):
        assert_hidden(view(client, gid, token), alice_hidden, repo)  # log included: nothing was ever public
    assert view(client, gid, alice)["zones"]["p1:library"]["known"] == []  # search over, no lingering view


def test_bounced_and_revealed_cards_become_anonymous_again(table):
    client, gid, alice, bob, spec = table
    repo = client.app.state.services.cards
    act(client, gid, alice, {"type": "search_start", "zone": {"zone": "library"}})
    state = state_of(client, gid)
    sol = next(c for c in cards_in(state, "p1", "library") if c.name == "Sol Ring")
    opt = next(c for c in cards_in(state, "p1", "library") if c.name == "Opt")
    act(client, gid, alice, {"type": "move", "card_ids": [sol.id, opt.id], "to": {"zone": "hand"}})
    act(client, gid, alice, {"type": "search_end", "shuffle": True})
    # Sol Ring: played, then bounced back to hand
    act(client, gid, alice, {"type": "move", "card_ids": [sol.id], "to": {"zone": "battlefield"}})
    assert view(client, gid, bob)["cards"][sol.id]["card_id"] == sol.card_id
    act(client, gid, alice, {"type": "move", "card_ids": [sol.id], "to": {"zone": "hand"}})
    # Opt: revealed to Bob, then hidden again
    act(client, gid, alice, {"type": "reveal", "card_ids": [opt.id], "to": ["p2"]})
    assert view(client, gid, bob)["cards"][opt.id]["card_id"] == opt.card_id
    assert opt.id not in view(client, gid, spec)["cards"]
    act(client, gid, alice, {"type": "hide", "card_ids": [opt.id]})
    state = state_of(client, gid)
    now_hidden = [state.cards[sol.id], state.cards[opt.id]]
    for token in (bob, spec):
        payload = view(client, gid, token)
        # present state is anonymous (the log may still say what happened back then)
        assert_hidden(payload, now_hidden, repo, include_log=False)
        assert len(payload["zones"]["p1:hand"]) == 2
    # rearranging the hand changes nothing an opponent receives
    before = view(client, gid, bob)
    act(client, gid, alice, {"type": "move", "card_ids": [opt.id], "to": {"zone": "hand"}, "index": 0})
    after = view(client, gid, bob)
    assert after["zones"]["p1:hand"] == before["zones"]["p1:hand"]
    assert {k: v for k, v in after["cards"].items() if "p1:hand" in k} == {k: v for k, v in before["cards"].items() if "p1:hand" in k}


def test_face_down_card_identity_stays_with_controller(table):
    client, gid, alice, bob, spec = table
    repo = client.app.state.services.cards
    act(client, gid, alice, {"type": "search_start", "zone": {"zone": "library"}})
    state = state_of(client, gid)
    delver = next(c for c in cards_in(state, "p1", "library") if c.name.startswith("Delver"))
    act(client, gid, alice, {"type": "move", "card_ids": [delver.id], "to": {"zone": "battlefield"}, "face_down": True,
                             "x": 50, "y": 50})
    act(client, gid, alice, {"type": "search_end", "shuffle": True})
    state = state_of(client, gid)
    for token in (bob, spec):
        payload = view(client, gid, token)
        card = payload["cards"][delver.id]  # public object: position is public, identity isn't
        assert card["hidden"] and card["face_down"] and card["x"] == 50
        assert not {"name", "card_id", "note", "categories", "face"} & set(card)
        body = {k: v for k, v in payload.items() if k != "log"}
        for token_ in fingerprints(state.cards[delver.id], repo)[1:]:
            assert token_ not in json.dumps(body)
    assert view(client, gid, alice)["cards"][delver.id]["card_id"] == delver.card_id


def test_websocket_frames_never_contain_hidden_identities(table):
    client, gid, alice, bob, spec = table
    repo = client.app.state.services.cards
    frames: list[dict[str, Any]] = []
    with client.websocket_connect(f"/ws/games/{gid}?token={alice}") as wa, client.websocket_connect(
        f"/ws/games/{gid}?token={bob}"
    ) as wb:
        wa.receive_json()
        frames.append(wb.receive_json())
        wa.receive_json()
        steps = [{"type": "draw", "count": 7}, {"type": "look_top", "count": 2}, {"type": "shuffle"}]
        for i, step in enumerate(steps, start=1):
            wa.send_json({"type": "action", "action": step, "id": i})
        for _ in range(12):
            msg = wb.receive_json()
            frames.append(msg)
            if msg["type"] == "state" and msg["view"]["game"]["seq"] >= 3:
                break
    state = state_of(client, gid)
    hidden = cards_in(state, "p1", "hand") + cards_in(state, "p1", "library")
    for frame in frames:
        if frame["type"] == "state":
            assert_hidden(frame["view"], hidden, repo)


def test_private_categories_and_token_shortcuts_stay_with_the_owner(table):
    client, gid, alice, bob, spec = table
    act(client, gid, alice, {"type": "search_start", "zone": {"zone": "library"}})
    state = state_of(client, gid)
    sol = next(c for c in cards_in(state, "p1", "library") if c.name == "Sol Ring")
    act(client, gid, alice, {"type": "move", "card_ids": [sol.id], "to": {"zone": "battlefield"}})
    act(client, gid, alice, {"type": "search_end", "shuffle": True})
    assert view(client, gid, alice)["cards"][sol.id]["categories"] == ["Ramp"]
    for token in (bob, spec):
        text = json.dumps(view(client, gid, token))
        assert "Ramp" not in text and "Interaction" not in text and "Cantrip" not in text


def test_rules_prompts_and_hints_do_not_leak(client):
    """Rules automation adds a decision (options may be hand cards) and hints (your playable
    cards). Neither may reveal a hidden card to an opponent or spectator, over REST or WS."""
    a = client.post("/api/decks", json={"text": P1_DECK}).json()["id"]
    b = client.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    game = client.post("/api/games", json={
        "mode": "lan", "shuffle": True, "automation": "full",
        "players": [{"name": "Alice", "deck_id": a}, {"name": "Bob", "deck_id": b}],
    }).json()
    gid, code, alice = game["game"]["id"], game["game"]["code"], game["seat"]["token"]
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    spec = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    repo = client.app.state.services.cards
    act(client, gid, alice, {"type": "pass_priority"})  # → Alice's main phase
    act(client, gid, alice, {"type": "draw", "count": 9})
    mine = view(client, gid, alice)["rules"]
    assert mine["hints"]["has_priority"] and mine["hints"]["playable_lands"]
    frames: list[dict[str, Any]] = []
    with client.websocket_connect(f"/ws/games/{gid}?token={bob}") as wb:
        frames.append(wb.receive_json())
        act(client, gid, alice, {"type": "pass_priority"})  # → main 2
        act(client, gid, alice, {"type": "pass_priority"})  # → cleanup: discard 2 (private options)
        for _ in range(2):
            frames.append(wb.receive_json())
    state = state_of(client, gid)
    assert state.rules and state.rules.decision and state.rules.decision.player == "p1"
    hidden = cards_in(state, "p1", "hand") + cards_in(state, "p1", "library")
    assert {o["card_id"] for o in view(client, gid, alice)["rules"]["decision"]["options"]} == {c.id for c in cards_in(state, "p1", "hand")}
    for token in (bob, spec):
        payload = view(client, gid, token)
        assert "options" not in payload["rules"]["decision"]
        assert payload["rules"]["hints"] in ({}, {"has_priority": False})
        assert_hidden(payload, hidden, repo)
    for frame in frames:
        if frame["type"] == "state":
            assert "options" not in (frame["view"]["rules"]["decision"] or {})
            assert_hidden(frame["view"], hidden, repo)
