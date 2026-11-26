"""-- saved rows -- a deck remembers which battlefield row its owner moved a card into, and the card enters there next time."""

from __future__ import annotations

import contextlib

import pytest

from app.game.errors import ActionError
from app.game.placement import ROWS, row_at
from app.game.state import BATTLEFIELD_H
from tests.game_helpers import act, find, make_session


@pytest.fixture()
def s(cards):
    return make_session(cards)


def onto_battlefield(s, name, pid="p1"):
    card = find(s.state, name, pid)
    act(s, pid, type="move", card_ids=[card.id], to={"zone": "battlefield", "player": pid})
    return s.state.cards[card.id]


def test_rows_are_read_from_the_top_edge_with_the_stacked_layers_counted():
    assert row_at(ROWS["other"]) == "other" and row_at(ROWS["creature"]) == "creature" and row_at(ROWS["land"]) == "land"
    assert row_at(ROWS["creature"] + 5 * 22) == "creature"  # a full creature row's last layer is still the creature row
    assert row_at(BATTLEFIELD_H - 1) == "land" and row_at(0) == "other"


def test_a_saved_row_places_the_card_on_entry(s):
    s.state.players["p1"].row_overrides["Sol Ring"] = "land"
    assert onto_battlefield(s, "Sol Ring").y == ROWS["land"]
    assert onto_battlefield(s, "Llanowar Elves").y == ROWS["creature"]  # other cards keep their type's row
    # only its owner's deck counts: the same name in another player's rows changes nothing for p1's cards
    s.state.players["p2"].row_overrides["Arcane Signet"] = "creature"
    assert onto_battlefield(s, "Arcane Signet", "p2").y == ROWS["creature"]


def test_moving_a_permanent_into_another_row_teaches_the_deck(s):
    ring = onto_battlefield(s, "Sol Ring")
    assert ring.y == ROWS["other"]
    act(s, "p1", type="set_position", moves=[[ring.id, ring.x, ring.y + 4]])  # a nudge within its row teaches nothing
    assert s.state.players["p1"].row_overrides == {}
    done = act(s, "p1", type="set_position", moves=[[ring.id, 300, ROWS["land"] + 10]])
    assert done.learned_rows == {"Sol Ring": "land"}
    assert s.state.players["p1"].row_overrides == {"Sol Ring": "land"}
    act(s, "p1", type="set_position", moves=[[ring.id, 300, ROWS["other"]]])  # back in its type's row: forgotten
    assert s.state.players["p1"].row_overrides == {}


def test_only_the_owner_teaches_and_a_client_cant_forge_a_lesson(s):
    signet = onto_battlefield(s, "Arcane Signet", "p2")
    with contextlib.suppress(ActionError):  # (the table may refuse moving another player's card outright: nothing is learned either way)
        act(s, "p1", type="set_position", moves=[[signet.id, 300, ROWS["land"]]])
    assert s.state.players["p2"].row_overrides == {} and s.state.players["p1"].row_overrides == {}
    ring = onto_battlefield(s, "Sol Ring")
    act(s, "p1", type="set_position", moves=[[ring.id, ring.x + 30, ring.y]], learned_rows={"Mountain": "other"})
    assert s.state.players["p1"].row_overrides == {}  # resolve decides the lesson, never the client


def test_saved_rows_stay_with_their_owner(s):
    s.state.players["p1"].row_overrides["Sol Ring"] = "land"
    p1 = next(p for p in s.view("p2")["players"] if p["id"] == "p1")
    assert "row_overrides" not in p1
    assert next(p for p in s.view("p1")["players"] if p["id"] == "p1")["row_overrides"] == {"Sol Ring": "land"}


def test_undo_and_replay_reproduce_the_lesson(s):
    ring = onto_battlefield(s, "Sol Ring")
    act(s, "p1", type="set_position", moves=[[ring.id, 300, ROWS["land"]]])
    after = s.state.model_dump(mode="json")
    assert s.history.rebuild().model_dump(mode="json") == after  # a replay from the base learns the same row
    s.undo("p1")
    assert s.state.players["p1"].row_overrides == {}
    s.redo("p1")
    assert s.state.players["p1"].row_overrides == {"Sol Ring": "land"}
    assert s.state.model_dump(mode="json") == after
    # the next Sol Ring entry, replayed, lands in the same place
    act(s, "p1", type="move", card_ids=[ring.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[ring.id], to={"zone": "battlefield", "player": "p1"})
    assert s.state.cards[ring.id].y == ROWS["land"]
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


KRENKO = """Commander
1 Krenko, Mob Boss
Deck
1 Sol Ring
1 Llanowar Elves
20 Mountain
"""


def test_rows_are_stored_with_the_saved_deck_and_used_next_game(client):
    deck_id = client.post("/api/decks", json={"text": KRENKO}).json()["id"]
    assert client.get(f"/api/decks/{deck_id}").json()["row_overrides"] == {}
    services = client.app.state.services

    def new_game():
        res = client.post("/api/games", json={"name": "T", "players": [{"name": "Alice", "deck_id": deck_id}]})
        assert res.status_code == 201, res.text
        return res.json()["game"]["id"]

    def ring_onto_battlefield(gid):
        state = services.hub.get(gid).session.state
        ring = next(c for c in state.cards.values() if c.name == "Sol Ring")
        res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "move", "card_ids": [ring.id], "to": {"zone": "battlefield", "player": "p1"}}})
        assert res.status_code == 200, res.text
        return state, ring.id

    gid = new_game()
    state, ring = ring_onto_battlefield(gid)
    assert state.cards[ring].y == ROWS["other"]
    res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "set_position", "moves": [[ring, 200, ROWS["land"]]]}})
    assert res.status_code == 200, res.text
    assert services.decks.row_overrides(deck_id) == {"Sol Ring": "land"}  # stored at once
    assert client.get(f"/api/decks/{deck_id}").json()["row_overrides"] == {"Sol Ring": "land"}
    # an undo takes the lesson back out of the deck too, a redo puts it back
    assert client.post(f"/api/games/{gid}/undo", json={}).status_code in (200, 204)
    assert services.decks.row_overrides(deck_id) == {}
    assert client.post(f"/api/games/{gid}/redo", json={}).status_code in (200, 204)
    assert services.decks.row_overrides(deck_id) == {"Sol Ring": "land"}

    state, ring = ring_onto_battlefield(new_game())  # the next game with the deck
    assert state.players["p1"].row_overrides == {"Sol Ring": "land"} and state.cards[ring].y == ROWS["land"]

    # the deck library's reset forgets them
    assert client.delete(f"/api/decks/{deck_id}/rows").status_code == 200
    assert client.get(f"/api/decks/{deck_id}").json()["row_overrides"] == {}
    state, ring = ring_onto_battlefield(new_game())
    assert state.cards[ring].y == ROWS["other"]
    # a deck loaded at the table from the host's library brings its rows
    services.decks.set_row_overrides(deck_id, {"Llanowar Elves": "other"})
    gid = new_game()
    assert client.post(f"/api/games/{gid}/load-deck", json={"deck_id": deck_id, "draw": 0}).status_code == 200
    assert services.hub.get(gid).session.state.players["p1"].row_overrides == {"Llanowar Elves": "other"}


def test_a_saved_row_places_a_permanent_the_rules_engine_resolves(cards):
    """With the rules on, a cast permanent enters through the engine's own moves (resolve.py): its saved row still holds."""
    from tests.test_rules_bandmate_references import wait_priority
    from tests.test_rules_designations import put, settle
    from tests.test_rules_shared_damage_choices import table

    s = table(cards, ["Sol Ring", "Llanowar Elves"])
    s.state.players["p1"].row_overrides["Sol Ring"] = "land"
    for name in ("Sol Ring", "Llanowar Elves"):
        source = put(s, name, "hand")
        act(s, "p1", type="add_mana", player="p1", mana={"C": 1, "G": 1})
        wait_priority(s, "p1")
        act(s, "p1", type="cast_spell", card_id=source.id, targets=[], sources=[])
        settle(s)
    ring, elves = find(s.state, "Sol Ring", "p1"), find(s.state, "Llanowar Elves", "p1")
    assert ring.zone == elves.zone == "p1:battlefield"
    assert ring.y == ROWS["land"] and elves.y == ROWS["creature"]


def test_tidying_a_mana_base_teaches_nothing(s):
    """ "Tidy my lands" piles lands upward from the near edge in one set_position; its upper piles may reach the creature row's
    height, which isn't the player choosing that row for them."""
    ids = [c.id for c in s.state.cards.values() if c.name == "Mountain"][:3]
    act(s, "p1", type="move", card_ids=ids, to={"zone": "battlefield", "player": "p1"})
    lands = [s.state.cards[i] for i in ids]
    assert all(c.y == ROWS["land"] for c in lands)
    act(s, "p1", type="set_position", moves=[[c.id, 20 + 30 * i, ROWS["creature"] + 20] for i, c in enumerate(lands)])
    assert s.state.players["p1"].row_overrides == {}
