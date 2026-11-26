"""-- bot decks -- a bot seated without one of the host's decks (app/decks/bot_decks.py): a random deck of the library, a bundled precon,
or a generated 100-card Commander deck for a random commander. Every pick is seeded (the same seed, the same deck), nothing is saved to
the library, and the deck reaches the table like any (its hand never reaches anyone else)."""

from __future__ import annotations

import json
import random
import re
from types import SimpleNamespace

import pytest

from app.decks import bot_decks
from app.decks import service as deck_service
from app.decks.models import DeckImportRequest
from tests.test_lan_bots import GRUUL
from tests.test_lobby import ALICE_DECK, create_lobby, h


def parse(text: str) -> tuple[str, dict[str, int]]:
    commander = re.search(r"Commander\n1 (.+)\n", text).group(1)
    body = text.split("Deck\n", 1)[1]
    counts = {m.group(2): int(m.group(1)) for m in re.finditer(r"^(\d+) (.+)$", body, re.M)}
    return commander, counts


# ---------------------------------------------------------------------------- the picks


def test_a_library_pick_is_seeded():
    decks = [SimpleNamespace(id=f"d{i}") for i in range(9)]
    picks = [bot_decks.pick_library_deck(decks, bot_decks.seeded("game", "p2", "@random")).id for _ in range(3)]
    assert len(set(picks)) == 1
    assert bot_decks.pick_library_deck(list(reversed(decks)), bot_decks.seeded("game", "p2", "@random")).id == picks[0]  # (order-free)
    assert len({bot_decks.pick_library_deck(decks, random.Random(n)).id for n in range(40)}) > 3
    assert bot_decks.pick_library_deck([], random.Random(1)) is None


def test_precons_by_id_and_at_random():
    first = bot_decks.precons()[0]
    assert bot_decks.precon(first["id"], random.Random(1)) == first
    assert bot_decks.precon("nope", random.Random(1)) is None
    a = bot_decks.precon(None, random.Random(5))
    assert a is not None and a == bot_decks.precon(None, random.Random(5))
    found = bot_decks.resolve("@precon:" + first["id"], library=[], cards=None, rng=random.Random(1))
    assert found["kind"] == "precon" and found["name"] == f"{first['name']} (precon)" and "Commander" in found["text"]
    with pytest.raises(bot_decks.DeckSourceError):
        bot_decks.resolve("@precon:nope", library=[], cards=None, rng=random.Random(1))
    with pytest.raises(bot_decks.DeckSourceError):
        bot_decks.resolve("@what", library=[], cards=None, rng=random.Random(1))
    assert bot_decks.resolve("abc123", library=[], cards=None, rng=random.Random(1)) == {"deck_id": "abc123"}


def test_a_generated_deck_is_a_legal_100_card_commander_deck(cards):
    made = bot_decks.generate_commander_deck(cards, bot_decks.seeded("g1", "p2"))
    assert made is not None
    text, name = made
    assert made == bot_decks.generate_commander_deck(cards, bot_decks.seeded("g1", "p2"))  # (seeded: the same deck again)
    commander, counts = parse(text)
    assert commander == name
    assert 1 + sum(counts.values()) == 100
    basics = set(bot_decks.BASICS.values()) | {"Wastes"}
    assert all(n == 1 for c, n in counts.items() if c not in basics)  # singleton
    result = deck_service.import_any(DeckImportRequest(text=text), cards)
    assert all(e.printing_id for e in result.entries)  # (every card is in the database)
    data = cards.get_many([e.printing_id for e in result.entries])
    identity = set(next(d for d in data.values() if d["name"] == commander)["color_identity"])
    for d in data.values():
        assert set(d["color_identity"]) <= identity, d["name"]
    lands = sum(n for c, n in counts.items() if c in basics)
    assert lands >= 36  # (the thin fixture pool is filled with basics: never fewer than the 36 it aims for)
    assert all(bot_decks.BASICS[c] in counts for c in identity if bot_decks.BASICS.get(c))  # (each of its colours has its basics)
    many = {bot_decks.generate_commander_deck(cards, random.Random(n))[1] for n in range(30)}
    assert len(many) > 2  # (a random commander)


# ---------------------------------------------------------------------------- over the API


@pytest.fixture()
def sandbox(client):
    from app.multiplayer import bots

    bots.DELAYS["normal"], old = 30.0, bots.DELAYS["normal"]
    deck = client.post("/api/decks", json={"text": GRUUL, "name": "Gruul"}).json()
    res = client.post("/api/games", json={"name": "Deck test", "format": "sandbox", "mode": "lan", "lobby": False, "seats": 1,
                                          "players": [{"name": "Alice", "deck_id": deck["id"]}], "first_player": 0})
    assert res.status_code == 201, res.text
    gid, host = res.json()["game"]["id"], {"X-Seat-Token": res.json()["seat"]["token"]}
    yield client, gid, host
    client.delete(f"/api/games/{gid}", headers=host)
    bots.DELAYS["normal"] = old


def test_the_sandbox_seats_a_bot_with_a_generated_or_random_deck(sandbox):
    client, gid, host = sandbox
    before = len(client.get("/api/decks").json())
    res = client.post(f"/api/games/{gid}/bot", json={"deck_id": "@generated"}, headers=host)
    assert res.status_code == 201, res.text
    view = res.json()["view"]
    them = next(p for p in view["players"] if p["id"] == "p2")
    assert them["hand_count"] == 7 and them["library_count"] == 100 - 7 - 1
    assert all(view["cards"][c].get("hidden") for c in view["zones"]["p2:hand"])  # (its hand: never shown to Alice)
    res = client.post(f"/api/games/{gid}/bot", json={"deck_id": "@random"}, headers=host)
    assert res.status_code == 201, res.text
    them = next(p for p in res.json()["view"]["players"] if p["id"] == "p3")
    assert them["library_count"] == 37 - 7 - 1  # (the only deck in the library: Gruul)
    assert client.post(f"/api/games/{gid}/bot", json={"deck_id": "@precon:nope"}, headers=host).status_code == 404
    assert client.post(f"/api/games/{gid}/bot", json={"deck_id": "@bogus"}, headers=host).status_code == 422
    assert len(client.get("/api/decks").json()) == before  # (nothing saved to the library)


def test_a_precon_without_known_cards_is_refused_gracefully(sandbox):
    client, gid, host = sandbox
    first = bot_decks.precons()[0]["id"]  # (the fixture card database knows none or few of its cards)
    res = client.post(f"/api/games/{gid}/bot", json={"deck_id": f"@precon:{first}"}, headers=host)
    assert res.status_code in (201, 422), res.text
    if res.status_code == 201:
        them = next(p for p in res.json()["view"]["players"] if p["id"] == "p2")
        assert them["hand_count"] + them["library_count"] > 0


@pytest.fixture()
def lobby(client):
    gid, code, alice = create_lobby(client, automation="full", turn_order="seats")
    assert client.post(f"/api/games/{gid}/lobby/deck", json={"text": ALICE_DECK}, headers=h(alice)).status_code == 200
    client.post("/api/decks", json={"text": GRUUL, "name": "Gruul"})
    yield client, gid, alice
    client.delete(f"/api/games/{gid}", headers=h(alice))


def test_the_lobby_seats_bots_with_random_and_generated_decks(lobby):
    client, gid, alice = lobby
    res = client.post(f"/api/games/{gid}/lobby/bot", json={"deck_id": "@random"}, headers=h(alice))
    assert res.status_code == 200, res.text
    seat = next(s for s in res.json()["seats"] if s.get("bot"))
    assert seat["deck"]["name"] == "Gruul" and seat["ready"]
    res = client.post(f"/api/games/{gid}/lobby/bot", json={"deck_id": "@generated", "level": "advanced"}, headers=h(alice))
    assert res.status_code == 200, res.text
    bots = [s for s in res.json()["seats"] if s.get("bot")]
    gen = next(s for s in bots if s["deck"]["name"].startswith("Generated: "))
    assert gen["deck"]["card_count"] == 100 and gen["bot"] == "advanced"
    assert "bot:" not in json.dumps(res.json())
    assert client.post(f"/api/games/{gid}/lobby/bot", json={"deck_id": "@precon:nope"}, headers=h(alice)).status_code == 404
