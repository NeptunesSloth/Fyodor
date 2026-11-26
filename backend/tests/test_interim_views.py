"""-- resolving progress -- a long automatic chain inside one action (Kiki-Jiki copies sacrificed one by one at the end step) is shown as
it goes: every connection gets interim views of the action's scratch table, each built for its own viewer by the same view builders
(hands and libraries stay hidden), then the action's own update. The action stays one history entry and replays the same."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.game.visibility import SPECTATOR
from app.multiplayer import hub as hub_mod
from app.multiplayer.hub import Connection, GameHub, InterimStream
from tests import test_rules_playtest_kiki_end_step_batch as kiki
from tests.test_rules_playtest_kiki_end_step_batch import card_db  # noqa: F401 - (the fixture: Kiki-Jiki and Pestermite)
from tests.wave9c_kit import check, reloaded, to_hand


@pytest.fixture()
def eager(monkeypatch):
    """Interim views after every resolution (the real pacing is wall-clock: a few a second)."""
    monkeypatch.setattr(hub_mod, "INTERIM_FIRST", 0.0)
    monkeypatch.setattr(hub_mod, "INTERIM_EVERY", 0.0)
    monkeypatch.setattr(hub_mod, "INTERIM_SHARE", 0.0)
    monkeypatch.setattr(kiki, "COPIES", 4)


def _seated(session):
    hub = GameHub()
    room = hub.create_room(session, mode="lan")
    inbox: dict[str, list[dict[str, Any]]] = {"p1": [], "p2": [], SPECTATOR: []}
    for viewer in inbox:
        async def send(message, viewer=viewer):
            inbox[viewer].append(json.loads(json.dumps(message)))  # (what goes over the wire)

        hub.connect(room, Connection(viewer=viewer, send=send, actor=viewer if viewer != SPECTATOR else None))
    return hub, room, inbox


def _next(session) -> dict[str, Any]:
    d = session.state.rules.decision
    if d is not None and d.kind == "declare_attackers":
        return {"type": "declare_attackers", "attackers": []}
    if d is not None:
        return {"type": "choose", "decision_id": d.id, "option_ids": [o.id for o in d.options][: max(1, d.min_choices)]}
    return {"type": "pass_priority", "until": "next_turn"}


def test_a_long_chain_streams_interim_views_per_viewer_and_stays_one_action(cards, eager):
    s = kiki._board(cards)
    mine, theirs = to_hand(s, "Forest"), to_hand(s, "Island", "p2")
    hub, room, inbox = _seated(s)

    async def play() -> tuple[int, int, int]:
        """Play on through the end step; returns (history length before / after, revision before) of the action that streamed."""
        for _ in range(40):
            if s.state.turn.number > 3:
                break
            payload = _next(s)
            actor = s.state.rules.decision.player if s.state.rules.decision else s.state.rules.priority
            before, revision, seen = len(s.history.actions), room.revision, len(inbox["p2"])
            twin = reloaded(s)  # the same action worked out the old way, on the loop, with nobody watching
            await hub.perform(room, actor, payload)
            twin.perform(actor, payload)
            assert {c.id: c.zone for c in twin.state.cards.values()} == {c.id: c.zone for c in s.state.cards.values()}
            assert [p.life for p in twin.state.players.values()] == [p.life for p in s.state.players.values()]
            await hub.broadcast(room)
            if any(m["type"] == "interim" for m in inbox["p2"][seen:]):
                return before, len(s.history.actions), revision
        raise AssertionError("no action showed interim views")

    before, after, revision = asyncio.run(play())
    assert after == before + 1  # one action in the history, however many views went out while it ran
    check(s)  # (the replay gives the same table)

    for viewer, messages in inbox.items():
        interim = [m for m in messages if m["type"] == "interim"]
        assert len(interim) >= 3, viewer  # (four sacrifices: a view after each)
        assert [m["progress"]["resolved"] for m in interim] == sorted(m["progress"]["resolved"] for m in interim)
        for m in interim:
            assert m["revision"] == revision and m["view"]["game"]["revision"] == revision  # on top of the last update, not a new one
            assert m["view"]["viewer"] == viewer
        # the action's own update comes after them, and nothing interim after it
        last = max(i for i, m in enumerate(messages) if m["type"] == "interim")
        assert messages[last + 1]["type"] == "state" and messages[last + 1]["revision"] == revision + 1
        # the board shrinks as the copies are sacrificed
        counts = [sum(1 for c in m["view"]["cards"].values() if c.get("zone") == "p1:battlefield") for m in interim]
        assert counts == sorted(counts, reverse=True) and counts[0] > counts[-1]

    # hidden information: each viewer's interim views are built for that viewer
    def hand(m, pid):
        return m["view"]["zones"][f"{pid}:hand"]

    for m in (m for m in inbox["p1"] if m["type"] == "interim"):
        assert mine.id in hand(m, "p1") and m["view"]["cards"][mine.id]["name"] == "Forest"
        assert theirs.id not in json.dumps(m)
    for viewer, own, other in (("p2", theirs, mine), (SPECTATOR, None, mine)):
        for m in (m for m in inbox[viewer] if m["type"] == "interim"):
            raw = json.dumps(m)
            assert other.id not in raw  # not even the real instance id of a card in another player's hand
            assert all(m["view"]["cards"][cid].get("hidden") and "name" not in m["view"]["cards"][cid] for cid in hand(m, "p1"))
            if own is None:
                assert theirs.id not in raw
            assert isinstance(m["view"]["zones"]["p1:library"], dict)  # a library is a count, never its cards


def test_interim_views_never_use_a_reveal_list_the_action_has_outdated(cards, eager, monkeypatch):
    """Who may see a hand or a library top is worked out again at the end of an action (and as it begins): part way through, the list
    may still name a source that no longer reveals anything. An interim view is built from a copy brought up to date the same way."""
    from app.game.rules_state import TopReveal
    from app.rules import progress

    s = kiki._board(cards)
    mine = to_hand(s, "Forest")
    kiki_card = next(c for c in s.state.cards.values() if c.name == kiki.KIKI)
    hub, room, inbox = _seated(s)
    stale = TopReveal(source=kiki_card.id, player="p1", to="all", zone="hand", whose="players")
    resolved = progress.resolved

    def outdated(plan):  # (as if Kiki-Jiki had said "Players play with their hands revealed" until a moment ago, in the chain)
        plan.state.rules.top_reveals = [stale]
        assert mine.id in json.dumps(s.view("p2", state=plan.state))  # (the outdated list would reveal Alice's hand)
        resolved(plan)

    monkeypatch.setattr(progress, "resolved", outdated)

    async def play() -> None:
        for _ in range(40):
            if s.state.turn.number > 3 or any(m["type"] == "interim" for m in inbox["p2"]):
                return
            actor = s.state.rules.decision.player if s.state.rules.decision else s.state.rules.priority
            await hub.perform(room, actor, _next(s))
            assert not s.state.rules.top_reveals  # (the action's end worked it out again)
            await hub.broadcast(room)

    asyncio.run(play())
    interim = [m for m in inbox["p2"] if m["type"] == "interim"]
    assert interim and all("view" in m for m in interim)
    assert not any(mine.id in json.dumps(m) for m in interim)


def test_interim_views_offered_after_the_action_are_dropped():
    sent: list[dict[str, Any]] = []

    async def run() -> None:
        hub = GameHub()

        class Room:
            revision, connections = 3, {}

        room = Room()

        async def send(message):
            sent.append(message)

        room.connections = {"c": Connection(viewer="p1", send=send, actor="p1", id="c")}
        stream = InterimStream(hub, room, asyncio.get_running_loop(), "p1")  # type: ignore[arg-type]
        stream._offer({"p1:False": {"type": "interim", "revision": 3, "progress": {"resolved": 1}}})
        await asyncio.sleep(0)
        await stream.close()
        stream._offer({"p1:False": {"type": "interim", "revision": 3, "progress": {"resolved": 2}}})  # (late: the action is done)
        await asyncio.sleep(0)
        assert stream.task is None

    asyncio.run(run())
    assert [m["progress"]["resolved"] for m in sent] == [1]


def test_quick_actions_and_tables_without_listeners_are_performed_as_before(cards):
    s = kiki._board(cards)
    hub = GameHub()
    room = hub.create_room(s, mode="lan")
    before = len(s.history.actions)

    async def play() -> None:
        await hub.perform(room, s.state.rules.priority, {"type": "pass_priority"})
        assert room.acting is None

    asyncio.run(play())
    assert len(s.history.actions) == before + 1
