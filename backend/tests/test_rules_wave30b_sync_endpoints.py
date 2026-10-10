"""Wave 30B: every endpoint that reads the live table runs on the thread that changes it (the event loop), as GET /view has since review 29A.

Actions change the table in ``room.session.perform`` on the event loop with no ``await`` inside, so a read on the loop sees whole tables. A ``def``
endpoint runs on the threadpool instead and could read a table half-way through an action (a card in two zones), the history while trimming re-bases
it in several steps (``History._trim``: base, then actions, then cursor), or the room's connections while a socket joins or leaves ("dictionary
changed size during iteration"). Like wave 29's test, this pins the thread: the spied reads each ran on the thread that performed the action."""

from __future__ import annotations

import threading
from dataclasses import replace

from app.game.history import History
from app.game.session import GameSession
from app.multiplayer.hub import Room


def test_endpoints_that_read_the_table_run_where_actions_change_it(client, monkeypatch):
    seen: list[tuple[str, int]] = []

    def spy(cls, name):
        real = getattr(cls, name)
        monkeypatch.setattr(cls, name, lambda *a, **kw: (seen.append((name, threading.get_ident())), real(*a, **kw))[1])

    for cls, name in ((GameSession, "perform"), (GameSession, "view"), (History, "state_at"), (Room, "summary")):
        spy(cls, name)

    class Assistant:
        def ask(self, question, context):
            seen.append(("ask", threading.get_ident()))
            return "ok"

    services = client.app.state.services
    services.assistant = Assistant()
    monkeypatch.setattr(services, "settings", replace(services.settings, dev_tools=True))
    gid = client.post("/api/games", json={"mode": "local", "automation": "full", "players": [{"name": "Alice"}, {"name": "Bob"}]}).json()["game"]["id"]
    assert client.post(f"/api/games/{gid}/actions", json={"action": {"type": "life", "delta": -1}, "as": "p1", "viewer": "p1"}).status_code == 200
    loop = next(t for name, t in seen if name == "perform")

    def threads(call, name):
        seen.clear()
        assert call().status_code == 200
        return {t for n, t in seen if n == name}

    assert threads(lambda: client.get(f"/api/games/{gid}"), "summary") == {loop}
    assert threads(lambda: client.get("/api/games"), "summary") == {loop}
    assert threads(lambda: client.get(f"/api/games/{gid}/history", params={"viewer": "p1"}), "view") == {loop}
    assert threads(lambda: client.get(f"/api/games/{gid}/history/1", params={"viewer": "p1"}), "state_at") == {loop}
    assert threads(lambda: client.get(f"/api/games/{gid}/rules/scenario"), "state_at") == {loop}
    assert threads(lambda: client.post(f"/api/games/{gid}/assistant", json={"question": "Can I respond?", "viewer": "p1"}), "view") == {loop}
    assert {t for n, t in seen if n == "ask"} not in ({loop}, set())  # (the blocking model call stays off the event loop)
