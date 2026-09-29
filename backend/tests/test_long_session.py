"""A long game night on one table: hundreds of mixed actions stay fast, undo keeps working, and a
crash at the end is recovered exactly (the journal is replayed on top of the last checkpoint)."""

from __future__ import annotations

import random
import time

from fastapi.testclient import TestClient

from app.main import create_app
from tests.test_protocol_privacy import P1_DECK, P2_DECK

ACTIONS = 400


def test_long_session_stays_fast_and_recovers(settings, card_db):
    c = TestClient(create_app(settings))
    a = c.post("/api/decks", json={"text": P1_DECK}).json()["id"]
    b = c.post("/api/decks", json={"text": P2_DECK}).json()["id"]
    game = c.post("/api/games", json={"mode": "local", "players": [
        {"name": n, "deck_id": d} for n, d in (("A", a), ("B", b), ("C", a), ("D", b))]}).json()
    gid = game["game"]["id"]
    rng = random.Random(7)

    def view():
        return c.get(f"/api/games/{gid}/view?viewer=all").json()

    def act(payload, player="p1"):
        return c.post(f"/api/games/{gid}/actions", json={"action": payload, "as": player})

    timings: list[float] = []
    v = view()
    for i in range(ACTIONS):
        player = f"p{rng.randint(1, 4)}"
        if i % 25 == 0:
            v = view()
        hand = v["zones"].get(f"{player}:hand", [])
        field = v["zones"].get(f"{player}:battlefield", [])
        roll = rng.random()
        if roll < 0.25 or not hand:
            payload = {"type": "draw", "player": player, "count": 1}
        elif roll < 0.45:
            payload = {"type": "move", "card_ids": [hand[0]], "to": {"zone": "battlefield", "player": player},
                       "x": rng.randint(0, 900), "y": rng.randint(0, 500)}
        elif roll < 0.6 and field:
            payload = {"type": "tap", "card_ids": [rng.choice(field)]}
        elif roll < 0.8:
            payload = {"type": "life", "player": player, "delta": rng.choice([-3, -1, 1, 2])}
        else:
            payload = {"type": "counter", "card_ids": field[:1], "kind": "+1/+1", "delta": 1} if field else {"type": "shuffle", "player": player}
        start = time.perf_counter()
        res = act(payload, player)
        timings.append(time.perf_counter() - start)
        if res.status_code == 200:
            v = res.json()
        if i % 40 == 39:
            assert c.post(f"/api/games/{gid}/undo", json={"as": player}).status_code == 200
            v = view()
    timings.sort()
    median = timings[len(timings) // 2]
    p95 = timings[int(len(timings) * 0.95)]
    print(f"\n{ACTIONS} actions: median {median * 1000:.1f} ms, p95 {p95 * 1000:.1f} ms")
    assert median < 0.08 and p95 < 0.25  # generous bounds for slow CI runners

    before = {k: view()[k] for k in ("zones", "cards", "players", "turn")}
    # crash: the first app is simply abandoned (no graceful shutdown, no final autosave)
    with TestClient(create_app(settings)) as again:
        after = again.get(f"/api/games/{gid}/view?viewer=all").json()
        assert {k: after[k] for k in ("zones", "cards", "players", "turn")} == before
