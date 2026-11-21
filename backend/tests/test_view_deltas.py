"""-- view deltas -- (app/multiplayer/view_delta.py) a client that asks for them gets its full view first, then patches from the last view it
was sent: applying each gives exactly the view the server built for it (key order included), a patch is made of that viewer's own two
views only (so no other viewer's hidden cards can be in one), and a full view comes again on resync, reconnect and seat switch."""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.visibility import SPECTATOR
from app.multiplayer.hub import Connection, GameHub
from app.multiplayer.view_delta import PatchError, apply, checked, diff, freeze
from tests.conftest import connect_game
from tests.game_helpers import act, deck, turn_on
from tests.test_protocol_privacy import (
    P1_DECK,
    P2_DECK,
    assert_hidden,
    cards_in,
    fingerprints,
    state_of,
    view,
)


def same(a: Any, b: Any) -> bool:
    """Equal as JSON text: the same values in the same key order."""
    return json.dumps(a) == json.dumps(b)


# -- the patch ------------------------------------------------------------------------------------------------------------
def test_a_patch_rebuilds_the_new_view_exactly():
    old = {"game": {"seq": 1, "revision": 3, "night": {"n": 1}}, "cards": {"a": {"zone": "hand", "tapped": False}, "b": {"zone": "lib"}},
           "log": [{"seq": i} for i in range(6)], "zones": {"p1:hand": ["a"]}, "gone": 1}
    new = {"game": {"seq": 2, "revision": 4, "night": {"n": 1}}, "cards": {"c": {"zone": "bf"}, "a": {"zone": "bf", "tapped": True}},
           "log": [{"seq": i} for i in range(2, 9)], "zones": {"p1:hand": []}, "rules": None}
    patch = diff(old, new)
    assert same(apply(old, patch), new)
    assert patch["tail"] == {"log": {"drop": 2, "add": [{"seq": 6}, {"seq": 7}, {"seq": 8}]}}  # (the log: what fell off, what came)
    assert patch["del"] == ["gone"] and patch["sub"]["cards"]["del"] == ["b"]
    assert patch["sub"]["cards"]["keys"] == ["c", "a"]  # (a new key ahead of an old one: the order comes along)
    assert "night" not in json.dumps(patch["sub"]["game"])  # (unchanged parts stay out)
    assert diff(new, new) == {} and same(apply(new, {}), new)


def test_patches_of_random_changes_rebuild_them_exactly():
    rng = random.Random(7)

    def value(depth: int) -> Any:
        roll = rng.random()
        if depth < 3 and roll < 0.3:
            return {rng.choice("abcdefgh"): value(depth + 1) for _ in range(rng.randint(0, 5))}
        if depth < 3 and roll < 0.45:
            return [value(depth + 1) for _ in range(rng.randint(0, 5))]
        return rng.choice([None, True, False, 2, 3, 2.5, "x", "y", "", [], {}])  # (no 0 or 1: Python's 1 == True, the test below)

    def mutate(v: Any, depth: int = 0) -> Any:
        if isinstance(v, dict):
            out = {k: (mutate(x, depth + 1) if rng.random() < 0.5 else x) for k, x in v.items() if rng.random() > 0.15}
            for _ in range(rng.randint(0, 2)):
                out[rng.choice("abcdefghij")] = value(depth + 1)
            if rng.random() < 0.2:
                out = dict(rng.sample(list(out.items()), len(out)))
            return out
        if isinstance(v, list):
            if rng.random() < 0.5:  # (a log: some off the front, some on the end)
                return v[rng.randint(0, len(v)):] + [value(depth + 1) for _ in range(rng.randint(0, 3))]
            return [mutate(x, depth + 1) for x in v]
        return value(depth) if rng.random() < 0.5 else v

    whole = 0
    for _ in range(3000):
        old = {k: value(1) for k in "abcdef"}
        new = mutate(old)
        patch = checked(old, new, json.dumps(new, separators=(",", ":")))
        if patch is None:  # (an object whose keys only moved is == to the old one in Python: diff misses it, the check doesn't)
            whole += 1
            assert not same(apply(old, diff(old, new)), new)
            continue
        assert same(apply(old, patch), new), (old, new)
    assert whole < 3000 * 0.2


def test_changes_python_calls_equal_are_not_missed():
    for old, new in (({"a": {"x": 1, "y": [0]}}, {"a": {"x": True, "y": [False]}}),  # (1 == True)
                     ({"a": {"b": {"x": 1, "y": 2}}}, {"a": {"b": {"y": 2, "x": 1}}})):  # (the same keys in another order)
        assert diff(old, new) == {}
        assert checked(old, new, json.dumps(new, separators=(",", ":"))) is None  # (so the whole view is sent)


def test_a_patch_that_does_not_fit_is_refused():
    base = {"cards": {"a": {"z": 1}}, "log": [1, 2]}
    for patch in ({"del": ["nope"]}, {"sub": {"log": {"set": {"x": 1}}}}, {"tail": {"log": {"drop": 3, "add": []}}},
                  {"tail": {"cards": {"drop": 0, "add": []}}}, {"keys": ["cards"]}, {"sub": {"missing": {}}}):
        with pytest.raises(PatchError):
            apply(base, patch)


# -- the hub ---------------------------------------------------------------------------------------------------------------
def _session(cards) -> GameSession:
    a = deck(cards, "Krenko, Mob Boss", [(1, "Llanowar Elves"), (1, "Elvish Visionary"), (1, "Lightning Bolt"), (20, "Forest")])
    b = deck(cards, "Atraxa, Praetors' Voice", [(1, "Merfolk Looter"), (20, "Island")])
    s = GameSession(new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], shuffle=True), cards=cards)
    turn_on(s)
    return s


def _seated(session, *, deltas: bool = True):
    hub = GameHub()
    room = hub.create_room(session, mode="lan")
    inbox: dict[str, list[dict[str, Any]]] = {"p1": [], "p2": [], SPECTATOR: []}
    for viewer in inbox:
        async def send(message, viewer=viewer):
            inbox[viewer].append(json.loads(json.dumps(message)))  # (what goes over the wire)

        conn = Connection(viewer=viewer, send=send, actor=viewer if viewer != SPECTATOR else None, deltas=deltas)
        hub.connect(room, conn)
        asyncio.run(send(hub.full(conn, hub.message(room, viewer))))  # (the socket's first message: games.game_socket)
    return hub, room, inbox


class Client:
    """What the browser keeps: the last view, the number of the last view message (frontend/src/services/viewDelta.ts's rules)."""

    def __init__(self) -> None:
        self.view: dict[str, Any] | None = None
        self.vseq = 0
        self.resyncs = 0

    def take(self, message: dict[str, Any]) -> None:
        if message["type"] == "state":
            self.view, self.vseq = message["view"], message["vseq"]
        elif message["type"] == "delta":
            if self.view is None or message["base"] != self.vseq:
                self.resyncs += 1
                return
            self.view, self.vseq = apply(self.view, message["patch"]), message["vseq"]


def _play(session, hub, room, steps: int = 14) -> None:
    async def run() -> None:
        for i in range(steps):
            st = session.state
            r = st.rules
            if i == 1:  # (a few things by hand as well: a hand card onto the battlefield, a draw)
                elf = next(c for c in st.zones["p1:hand"] + st.zones["p1:library"] if st.cards[c].name == "Llanowar Elves")
                await hub.perform(room, "p1", {"type": "move", "card_ids": [elf], "to": {"player": "p1", "zone": "battlefield"}})
            elif i == 2:
                await hub.perform(room, "p2", {"type": "draw", "count": 2})
            elif r.decision is not None:
                d = r.decision
                answer = ({"type": "declare_attackers", "attackers": []} if d.kind == "declare_attackers" else
                          {"type": "declare_blockers", "blocks": []} if d.kind == "declare_blockers" else
                          {"type": "choose", "decision_id": d.id, "option_ids": [o.id for o in d.options][: max(1, d.min_choices)]})
                await hub.perform(room, d.player, answer)
            else:
                await hub.perform(room, r.priority or st.turn.active_player, {"type": "pass_priority"})
            hub.after_change(room)
            await hub.broadcast(room)

    asyncio.run(run())


def test_every_viewer_rebuilds_its_own_view_from_the_deltas(cards):
    s = _session(cards)
    hub, room, inbox = _seated(s)
    _play(s, hub, room)
    for viewer, messages in inbox.items():
        assert messages[0]["type"] == "state" and {m["type"] for m in messages[1:]} == {"delta"}, viewer
        client = Client()
        for m in messages:
            client.take(m)
        assert client.resyncs == 0
        assert same(client.view, freeze(hub.view(room, viewer))[0]), viewer  # (exactly the view the server builds for it now)
        assert [m["vseq"] for m in messages] == list(range(1, len(messages) + 1))
        full = len(json.dumps(hub.view(room, viewer)))
        assert max(len(json.dumps(m)) for m in messages[1:]) < full / 2, viewer


def test_a_delta_is_made_of_its_own_viewers_views_only(cards):
    """Every string in a patch to a viewer (keys and values) is in that viewer's view before or after it: nothing another viewer sees,
    so the hidden-information guarantees of the full views (tests/test_protocol_privacy.py) hold for the patches too."""
    s = _session(cards)
    hub, room, inbox = _seated(s)
    _play(s, hub, room)
    hidden_p1 = [s.state.cards[c] for c in s.state.zones["p1:hand"] + s.state.zones["p1:library"]]
    hidden_p2 = [s.state.cards[c] for c in s.state.zones["p2:hand"] + s.state.zones["p2:library"]]

    def strings(x: Any) -> set[str]:
        if isinstance(x, dict):
            return set(x) | {s for v in x.values() for s in strings(v)}
        if isinstance(x, list):
            return {s for v in x for s in strings(v)}
        return {x} if isinstance(x, str) else set()

    for viewer, messages in inbox.items():
        client = Client()
        for m in messages:
            before = client.view
            client.take(m)
            if m["type"] != "delta":
                continue
            assert strings(m["patch"]) - {"set", "del", "sub", "tail", "keys", "drop", "add"} <= strings(before) | strings(client.view)
            text = json.dumps(m)
            for card in (hidden_p1 if viewer != "p1" else []) + (hidden_p2 if viewer != "p2" else []):
                for token in fingerprints(card, cards):
                    assert token not in text, (viewer, card.name, token)


def test_mismatched_base_resync_and_seat_switch_send_a_full_view(cards):
    s = _session(cards)
    hub, room, inbox = _seated(s)
    _play(s, hub, room, steps=3)
    conn = next(c for c in room.connections.values() if c.viewer == "p2")
    sent = []

    async def go() -> None:
        sent.append(hub.full(conn, {**hub.message(room, "p2"), "resync": True}))  # (the socket's answer to "resync")
        act(s, "p1", type="draw", count=1)
        await hub.broadcast(room)

    asyncio.run(go())
    resync, after = sent[0], inbox["p2"][-1]
    assert resync["type"] == "state" and resync["resync"] and after["type"] == "delta" and after["base"] == resync["vseq"]
    client = Client()
    client.take(resync)
    client.take(after)
    assert same(client.view, freeze(hub.view(room, "p2"))[0])
    # a client holding another view asks for the whole one
    stale = Client()
    stale.take(inbox["p2"][0])
    stale.take(after)
    assert stale.resyncs == 1
    # a lobby in between: the next view is whole
    hub._update(conn, "p2:False", {"type": "lobby", "lobby": {}}, {}, {}, full=False)
    assert conn.sent is None
    asyncio.run(hub.broadcast(room))
    assert inbox["p2"][-1]["type"] == "state"


def test_a_client_without_deltas_gets_whole_views_as_before(cards):
    s = _session(cards)
    hub, room, inbox = _seated(s, deltas=False)
    _play(s, hub, room, steps=3)
    for messages in inbox.values():
        assert {m["type"] for m in messages} == {"state"} and not any("vseq" in m for m in messages)


# -- over the socket ------------------------------------------------------------------------------------------------------
@pytest.fixture()
def table(client):
    a = client.post("/api/decks", json={"text": P1_DECK}).json()["id"]
    b = client.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    game = client.post("/api/games", json={
        "mode": "lan", "shuffle": True, "automation": "full",
        "players": [{"name": "Alice", "deck_id": a}, {"name": "Bob", "deck_id": b}],
    }).json()
    gid, code, alice = game["game"]["id"], game["game"]["code"], game["seat"]["token"]
    bob = client.post("/api/join", json={"code": code, "name": "Bob"}).json()["token"]
    spec = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    return client, gid, alice, bob, spec


def test_socket_deltas_rebuild_the_view_and_never_carry_hidden_cards(table):
    client, gid, alice, bob, spec = table
    repo = client.app.state.services.cards
    frames: dict[str, list[dict[str, Any]]] = {"bob": [], "spec": []}

    def until(sock, out: list[dict[str, Any]], done) -> dict[str, Any]:
        for _ in range(40):
            msg = sock.receive_json()
            out.append(msg)
            if done(msg):
                return msg
        raise AssertionError("never came")

    with connect_game(client, gid, alice, deltas=True) as wa,             connect_game(client, gid, bob, deltas=True) as wb,             connect_game(client, gid, spec, deltas=True) as ws:
        mine: list[dict[str, Any]] = []

        def action(i: int, step: dict[str, Any]) -> None:
            wa.send_json({"type": "action", "action": step, "id": i})
            answer = until(wa, mine, lambda m: m["type"] in ("ack", "error") and m.get("id") == i)
            if answer["type"] == "error":
                return
            rev = until(wa, mine, lambda m: m["type"] in ("state", "delta"))["revision"]  # (the update after it, to everyone)
            for sock, name in ((wb, "bob"), (ws, "spec")):
                until(sock, frames[name], lambda m: m["type"] in ("state", "delta") and m["revision"] >= rev)

        steps = [{"type": "draw", "count": 7}, {"type": "look_top", "count": 2}, {"type": "pass_priority"}, {"type": "draw", "count": 2}]
        for i, step in enumerate(steps, start=1):
            action(i, step)
        wb.send_json({"type": "resync", "id": 99})  # (a client that lost track: the whole view again, then deltas from it)
        until(wb, frames["bob"], lambda m: bool(m.get("resync")))
        action(100, {"type": "draw", "count": 1})
        rest = {"bob": view(client, gid, bob), "spec": view(client, gid, spec)}  # (while everyone is still connected)
    state = state_of(client, gid)
    hidden = cards_in(state, "p1", "hand") + cards_in(state, "p1", "library")
    for name in ("bob", "spec"):
        got = [m for m in frames[name] if m["type"] in ("state", "delta")]
        assert got[0]["type"] == "state" and any(m["type"] == "delta" for m in got)
        rebuilt = Client()
        for m in got:
            assert_hidden(m.get("view") or m["patch"], hidden, repo)  # (the frame as sent)
            rebuilt.take(m)
            assert_hidden(rebuilt.view, hidden, repo)
        assert rebuilt.resyncs == 0
        assert [k for k in rest[name] if rebuilt.view.get(k) != rest[name][k]] == []
        assert same(rebuilt.view, rest[name])  # (the REST view is whole, and the same)
    assert any(m.get("resync") and m["type"] == "state" for m in frames["bob"])
    assert frames["bob"][-1]["type"] == "delta"
