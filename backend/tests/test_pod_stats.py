"""Pod win tracker: results are the source of truth; stats are recomputed from them."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import claim_host

DECKS = {
    "Jonathan": "Commander\n1x Atraxa, Praetors' Voice (2x2) 190\nDeck\n10x Island (cmm) 1001\n",
    "Mike": "Commander\n1x Krenko, Mob Boss (ddn) 13\nDeck\n10x Mountain (cmm) 1003\n",
    "Alex": "Deck\n10x Forest (cmm) 1002\n",
    "Chris": "Commander\n1x Krenko, Mob Boss (ddn) 13\n1x Lim-Dûl the Necromancer (tsp) 114\nDeck\n10x Mountain (cmm) 1003\n",
}


def new_game(client, names=("Jonathan", "Mike", "Alex", "Chris")) -> str:
    players = []
    for n in names:
        deck = client.post("/api/decks", json={"text": DECKS[n], "name": f"{n}'s deck"}).json()["id"]
        players.append({"name": n, "deck_id": deck})
    return client.post("/api/games", json={"mode": "local", "players": players}).json()["game"]["id"]


def record(client, gid, result_type, winners=(), notes=""):
    return client.post(f"/api/games/{gid}/result", json={"result_type": result_type, "winners": list(winners), "notes": notes})


def stats(client) -> dict[str, dict]:
    return {p["name"]: p for p in client.get("/api/pod/players").json()}


def test_single_winner_four_player_game(client):
    gid = new_game(client)
    assert client.get(f"/api/games/{gid}/result").json() is None
    res = record(client, gid, "single", ["p2"], "Mike killed everyone with 84 Goblins.")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["winners"] == ["Mike"] and body["notes"].startswith("Mike killed") and body["number"] == 1
    assert body["turns"] == 1 and body["duration_seconds"] is not None
    s = stats(client)
    assert (s["Mike"]["games"], s["Mike"]["wins"], s["Mike"]["losses"], s["Mike"]["win_pct"]) == (1, 1, 0, 100.0)
    for n in ("Jonathan", "Alex", "Chris"):
        assert (s[n]["games"], s[n]["wins"], s[n]["losses"], s[n]["win_pct"]) == (1, 0, 1, 0.0)
    # the view knows the game has a recorded result
    assert client.get(f"/api/games/{gid}/view").json()["game"]["result_id"] == body["id"]


def test_duplicate_submission_is_refused(client):
    gid = new_game(client, ("Jonathan", "Mike"))
    assert record(client, gid, "single", ["p1"]).status_code == 201
    again = record(client, gid, "single", ["p2"])
    assert again.status_code == 409 and "already recorded" in again.json()["detail"]
    assert stats(client)["Jonathan"]["games"] == 1


@pytest.mark.parametrize(("rtype", "winners", "error"), [
    ("single", [], "exactly one"), ("single", ["p1", "p2"], "exactly one"), ("multiple", ["p1"], "at least two"),
    ("draw", ["p1"], "no winners"), ("single", ["p9"], "one of the players"),
])
def test_invalid_results(client, rtype, winners, error):
    gid = new_game(client, ("Jonathan", "Mike", "Alex"))
    res = record(client, gid, rtype, winners)
    assert res.status_code == 422 and error in res.json()["detail"]


def test_multiple_winners_draw_and_no_result(client):
    g1, g2, g3 = (new_game(client, ("Jonathan", "Mike", "Alex")) for _ in range(3))
    record(client, g1, "multiple", ["p1", "p2"])
    record(client, g2, "draw")
    record(client, g3, "no_result")
    s = stats(client)
    assert (s["Jonathan"]["games"], s["Jonathan"]["wins"], s["Jonathan"]["draws"]) == (2, 1, 1)
    assert (s["Alex"]["games"], s["Alex"]["wins"], s["Alex"]["losses"], s["Alex"]["draws"]) == (2, 0, 1, 1)
    assert s["Jonathan"]["win_pct"] == 50.0  # draws count as games played
    history = client.get("/api/pod/results").json()
    assert [r["result_type"] for r in history] == ["no_result", "draw", "multiple"]


def test_correcting_and_deleting_recompute_everything(client):
    gid = new_game(client)
    rid = record(client, gid, "single", ["p1"]).json()["id"]
    res = client.put(f"/api/pod/results/{rid}", json={"winners": ["p3"], "notes": "Alex, not Jonathan"})
    assert res.status_code == 200 and res.json()["winners"] == ["Alex"]
    s = stats(client)
    assert (s["Alex"]["wins"], s["Jonathan"]["wins"], s["Jonathan"]["losses"]) == (1, 0, 1)
    client.put(f"/api/pod/results/{rid}", json={"result_type": "draw"})
    s = stats(client)
    assert all(p["draws"] == 1 and p["wins"] == 0 and p["games"] == 1 for p in s.values())
    client.put(f"/api/pod/results/{rid}", json={"result_type": "no_result"})
    assert all(p["games"] == 0 and p["win_pct"] is None for p in stats(client).values())
    assert client.delete(f"/api/pod/results/{rid}").status_code == 204
    assert client.get("/api/pod/results").json() == []
    # a deleted erroneous result can be recorded again
    assert record(client, gid, "single", ["p2"]).status_code == 201


def test_deck_level_and_multi_commander_stats(client):
    for winner in ("p1", "p1", "p2"):
        gid = new_game(client, ("Jonathan", "Chris"))
        record(client, gid, "single", [winner])
    chris = next(p for p in client.get("/api/pod/players").json() if p["name"] == "Chris")
    detail = client.get(f"/api/pod/players/{chris['id']}").json()
    # each game used a freshly imported copy (a different library deck), so three deck entries
    assert sum(d["games"] for d in detail["decks"]) == 3 and sum(d["wins"] for d in detail["decks"]) == 1
    assert detail["decks"][0]["commanders"] == ["Krenko, Mob Boss", "Lim-Dûl the Necromancer"]
    assert [g["outcome"] for g in detail["recent"]] == ["win", "loss", "loss"]
    assert detail["recent"][0]["commanders"] == ["Krenko, Mob Boss", "Lim-Dûl the Necromancer"]
    assert (detail["games"], detail["wins"], detail["losses"], detail["win_pct"]) == (3, 1, 2, 33.3)


def test_same_deck_across_games_is_one_deck(client):
    deck = client.post("/api/decks", json={"text": DECKS["Mike"], "name": "Goblins"}).json()["id"]
    other = client.post("/api/decks", json={"text": DECKS["Alex"], "name": "Elves"}).json()["id"]
    for winner in ("p1", "p2", "p1"):
        gid = client.post("/api/games", json={"mode": "local", "players": [
            {"name": "Mike", "deck_id": deck}, {"name": "Alex", "deck_id": other}]}).json()["game"]["id"]
        record(client, gid, "single", [winner])
    mike = next(p for p in client.get("/api/pod/players").json() if p["name"] == "Mike")
    decks = client.get(f"/api/pod/players/{mike['id']}").json()["decks"]
    assert len(decks) == 1 and (decks[0]["deck_name"], decks[0]["games"], decks[0]["wins"]) == ("Goblins", 3, 2)


def test_stats_are_separate_from_saves_and_survive_restart(client, settings):
    gid = new_game(client, ("Jonathan", "Mike"))
    client.post(f"/api/games/{gid}/save", json={"name": "s"})
    client.delete(f"/api/games/{gid}")
    assert client.get("/api/pod/players").json() == []  # saving/closing records nothing
    save = client.get("/api/saves").json()[0]
    client.post(f"/api/saves/{save['id']}/load", json={"mode": "local"})
    assert record(client, gid, "single", ["p2"]).status_code == 201
    with TestClient(create_app(settings)) as again:
        claim_host(again)
        s = stats(again)
        assert s["Mike"]["wins"] == 1 and s["Jonathan"]["losses"] == 1
        # a reloaded game still knows it was recorded
        again.post(f"/api/saves/{save['id']}/load", json={"mode": "local"})
        assert again.get(f"/api/games/{gid}/view").json()["game"]["result_id"]
        assert record(again, gid, "single", ["p1"]).status_code == 409
        assert again.get("/api/pod/export").json()["results"][0]["winners"] == ["Mike"]


def test_lan_guests_can_read_but_not_record_or_correct(client):
    body = client.post("/api/games", json={"mode": "lan", "players": [{"name": "Jonathan"}, {"name": "Mike"}]}).json()
    gid, host = body["game"]["id"], body["seat"]["token"]
    mike = client.post("/api/join", json={"code": body["game"]["code"], "name": "Mike"}).json()["token"]
    res = client.post(f"/api/games/{gid}/result", json={"result_type": "single", "winners": ["p2"]}, headers={"X-Seat-Token": mike})
    assert res.status_code == 403
    rid = client.post(f"/api/games/{gid}/result", json={"result_type": "single", "winners": ["p2"]},
                      headers={"X-Seat-Token": host}).json()["id"]
    remote = TestClient(client.app, client=("192.168.1.20", 50000))
    assert remote.get("/api/pod/players").status_code == 200
    assert remote.put(f"/api/pod/results/{rid}", json={"winners": ["p1"]}).status_code == 403
    assert remote.delete(f"/api/pod/results/{rid}").status_code == 403
