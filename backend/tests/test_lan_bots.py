"""-- LAN bots -- the host seats bots in a game-night lobby (POST /games/{id}/lobby/bot): a deck from the host's library and a level; the
server plays them (app/game/bot.py, paced by app/multiplayer/bots.py). Nobody can act as a bot, its hidden cards never reach a person,
and it never holds up a result or the rematch vote; pod stats record it as a bot."""

from __future__ import annotations

import json
import time

import pytest

from app.multiplayer import bots
from tests.test_lobby import ALICE_DECK, create_lobby, h

GRUUL = """Commander
1 Krenko, Mob Boss

Deck
14 Forest
6 Mountain
8 Grizzly Bears
6 Llanowar Elves
2 Lightning Bolt
"""


@pytest.fixture()
def lobby(client, monkeypatch):
    monkeypatch.setitem(bots.DELAYS, "normal", 0.0)
    gid, code, alice = create_lobby(client, automation="full", turn_order="seats")
    deck_id = client.post("/api/decks", json={"text": GRUUL, "name": "Gruul"}).json()["id"]
    assert client.post(f"/api/games/{gid}/lobby/deck", json={"text": ALICE_DECK}, headers=h(alice)).status_code == 200
    assert client.post(f"/api/games/{gid}/lobby/ready", json={"ready": True}, headers=h(alice)).status_code == 200
    yield client, gid, code, alice, deck_id
    client.delete(f"/api/games/{gid}", headers=h(alice))


def add_bot(client, gid, alice, deck_id, **extra):
    res = client.post(f"/api/games/{gid}/lobby/bot", json={"deck_id": deck_id, **extra}, headers=h(alice))
    assert res.status_code == 200, res.text
    return res.json()


def view(client, gid, token):
    res = client.get(f"/api/games/{gid}/view", headers=h(token))
    assert res.status_code == 200, res.text
    return res.json()


def start(client, gid, alice):
    res = client.post(f"/api/games/{gid}/lobby/start", json={"first_player": 0}, headers=h(alice))
    assert res.status_code == 200, res.text


def test_the_host_seats_a_bot_in_the_lobby(lobby):
    client, gid, code, alice, deck_id = lobby
    body = add_bot(client, gid, alice, deck_id, level="advanced")
    seat = next(s for s in body["seats"] if s.get("bot"))
    assert seat["bot"] == "advanced" and seat["claimed"] and seat["ready"] and seat["name"] == "Bot" and seat["id"] == "p2"
    assert seat["deck"]["name"] == "Gruul" and "bot:" not in json.dumps(body)
    assert body["start_blockers"] == []
    # (change its level; then Bob joins: he can't take the bot's seat, and he can't seat a bot)
    body = add_bot(client, gid, alice, None, seat="p2", level="simple")
    assert next(s for s in body["seats"] if s["id"] == "p2")["bot"] == "simple"
    bob = client.post("/api/join", json={"code": code, "name": "Bob", "seat": "p2"})
    assert bob.status_code != 200
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    assert client.post(f"/api/games/{gid}/lobby/bot", json={"deck_id": deck_id}, headers=h(bob)).status_code == 403
    assert client.post(f"/api/games/{gid}/host/seat-link", json={"seat": "p2"}, headers=h(alice)).status_code == 409
    # (without rules automation at Full it can't play: the start waits for it)
    client.post(f"/api/games/{gid}/lobby/settings", json={"automation": "off"}, headers=h(alice))
    blockers = client.get(f"/api/games/{gid}/lobby", headers=h(alice)).json()["start_blockers"]
    assert any("bot" in b for b in blockers)
    # (kick frees the seat again)
    body = client.post(f"/api/games/{gid}/lobby/kick", json={"seat": "p2"}, headers=h(alice)).json()
    assert not any(s.get("bot") for s in body["seats"])


def _play_until(client, gid, alice, done, steps=400):
    """Alice passes and declares nothing; the server plays the bot in between."""
    for _ in range(steps):
        v = view(client, gid, alice)
        if done(v):
            return v
        me = v["viewer"]
        d = (v.get("rules") or {}).get("decision")
        action = None
        if d is not None and d.get("player") == me and d.get("options") is not None:
            if d["kind"].startswith("declare_"):
                action = {"type": d["kind"]}
            elif d["kind"] == "reconcile":
                firsts: dict = {}
                for o in d["options"]:
                    firsts.setdefault(o.get("group"), o["id"])
                action = {"type": "choose", "decision_id": d["id"], "option_ids": list(firsts.values())}
            else:
                opts = [o["id"] for o in d["options"] if o.get("group") != "seen"][: max(1, int(d.get("min_choices") or 0))]
                action = {"type": "choose", "decision_id": d["id"], "option_ids": opts}
        elif (v.get("pregame") or {}).get("seats", {}).get(me, {}).get("status") == "deciding":
            action = {"type": "mulligan_keep"}
        elif (v.get("rules") or {}).get("priority") == me:
            action = {"type": "pass_priority"}
        if action is None:
            time.sleep(0.05)
            continue
        client.post(f"/api/games/{gid}/actions", json={"action": action}, headers=h(alice))
    raise AssertionError("never got there")


def test_a_lan_game_with_a_bot_its_turns_and_its_privacy(lobby):
    client, gid, code, alice, deck_id = lobby
    add_bot(client, gid, alice, deck_id, level="intermediate")
    start(client, gid, alice)
    v = view(client, gid, alice)
    them = next(p for p in v["players"] if p["bot"])
    assert them["bot_level"] == "intermediate" and them["name"] == "Bot"
    pid = them["id"]
    v = _play_until(client, gid, alice, lambda v: v["turn"]["number"] >= 3)
    lands = [cid for cid in v["zones"][f"{pid}:battlefield"]]
    assert lands, "the bot played its turn (a land at least)"
    # privacy: its hand reaches Alice only as anonymous cards, its library not at all; no bot token anywhere
    for cid in v["zones"][f"{pid}:hand"]:
        assert v["cards"][cid].get("hidden")
    library = v["zones"][f"{pid}:library"]
    known = library.get("known", []) if isinstance(library, dict) else []
    assert not known
    assert "bot:" not in json.dumps(v)
    guest = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    spectator = view(client, gid, guest)
    assert all(spectator["cards"][cid].get("hidden") for cid in spectator["zones"][f"{pid}:hand"])


def test_a_bot_never_holds_up_the_result_or_the_rematch(lobby):
    client, gid, code, alice, deck_id = lobby
    add_bot(client, gid, alice, deck_id)
    start(client, gid, alice)
    _play_until(client, gid, alice, lambda v: (v.get("rules") or {}).get("priority") == v["viewer"]
                and not (v.get("pregame") and not v["pregame"].get("finished")))
    res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "concede"}}, headers=h(alice))
    assert res.status_code == 200, res.text
    night = view(client, gid, alice)["game"]["night"]
    proposal = night["proposal"]
    assert proposal is not None and proposal["rules"] and proposal["voters"] == ["p1"]  # (Alice confirms; the bot isn't asked)
    assert client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(alice)).status_code == 200
    recorded = client.get(f"/api/games/{gid}/result").json()
    assert recorded["winners"] == ["Bot (bot)"]  # (pod stats: the bot as a bot)
    res = client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(alice))
    assert res.status_code == 200 and res.json()["decision"] == "rematch"
    v = view(client, gid, alice)
    assert v["game"]["night"]["number"] == 2
    assert [p["bot_level"] for p in v["players"] if p["bot"]] == ["intermediate"]


def test_back_to_the_lobby_after_a_restart_keeps_the_table_settings_and_the_bot_level(lobby):
    """The server restarted during the game: the lobby's settings and the seats' setups (in memory only) are gone. Return to lobby
    takes the settings the game was played with (Automation Full, which the bot needs) and the bot's level, not the defaults."""
    client, gid, code, alice, deck_id = lobby
    add_bot(client, gid, alice, deck_id, level="advanced")
    start(client, gid, alice)
    _play_until(client, gid, alice, lambda v: (v.get("rules") or {}).get("priority") == v["viewer"]
                and not (v.get("pregame") and not v["pregame"].get("finished")))
    room = client.app.state.services.hub.get(gid)
    room.lobby, room.night.setups, room.night.infos = None, {}, {}  # (what a restart loses: app/multiplayer/night.py meta)
    assert client.post(f"/api/games/{gid}/actions", json={"action": {"type": "concede"}}, headers=h(alice)).status_code == 200
    assert client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(alice)).status_code == 200
    res = client.post(f"/api/games/{gid}/night/vote", json={"choice": "lobby"}, headers=h(alice))
    assert res.status_code == 200 and res.json()["decision"] == "lobby", res.text
    body = client.get(f"/api/games/{gid}/lobby", headers=h(alice)).json()
    assert body["settings"]["automation"] == "full" and body["settings"]["mulligan_rule"] == "commander_london"
    assert next(s for s in body["seats"] if s.get("bot"))["bot"] == "advanced"
    assert not any("Full" in b for b in body["start_blockers"])


def test_after_a_restart_the_rematch_and_the_lobby_still_know_the_bots_deck(lobby):
    """-- restart rematch -- the crash record keeps the setups: a same-decks rematch works after a restart (the bot's deck too),
    and back in the lobby the bot still has its deck (it used to sit at "choosing a deck" until kicked)."""
    from app.multiplayer.night import Night

    client, gid, code, alice, deck_id = lobby
    add_bot(client, gid, alice, deck_id, level="advanced")
    start(client, gid, alice)
    _play_until(client, gid, alice, lambda v: (v.get("rules") or {}).get("priority") == v["viewer"]
                and not (v.get("pregame") and not v["pregame"].get("finished")))
    room = client.app.state.services.hub.get(gid)
    room.lobby, room.night = None, Night.from_meta(json.loads(json.dumps(room.night.meta())))  # (what a restart keeps)
    assert client.post(f"/api/games/{gid}/actions", json={"action": {"type": "concede"}}, headers=h(alice)).status_code == 200
    assert client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(alice)).status_code == 200
    assert view(client, gid, alice)["game"]["night"]["rematch_missing"] == []
    res = client.post(f"/api/games/{gid}/night/vote", json={"choice": "rematch"}, headers=h(alice))
    assert res.status_code == 200 and res.json()["decision"] == "rematch", res.text
    v = view(client, gid, alice)
    assert [p["bot_level"] for p in v["players"] if p["bot"]] == ["advanced"]
    _play_until(client, gid, alice, lambda v: (v.get("rules") or {}).get("priority") == v["viewer"]
                and not (v.get("pregame") and not v["pregame"].get("finished")))
    room = client.app.state.services.hub.get(gid)
    room.lobby, room.night = None, Night.from_meta(json.loads(json.dumps(room.night.meta())))
    assert client.post(f"/api/games/{gid}/actions", json={"action": {"type": "concede"}}, headers=h(alice)).status_code == 200
    assert client.post(f"/api/games/{gid}/night/answer", json={"agree": True}, headers=h(alice)).status_code == 200
    assert client.post(f"/api/games/{gid}/night/vote", json={"choice": "lobby"}, headers=h(alice)).json()["decision"] == "lobby"
    bot = next(s for s in client.get(f"/api/games/{gid}/lobby", headers=h(alice)).json()["seats"] if s.get("bot"))
    assert bot["deck"]["name"] == "Gruul" and bot["ready"]
