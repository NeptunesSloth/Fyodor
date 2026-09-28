"""Hidden-information tests: private cards must never reach a viewer's serialized view."""

from __future__ import annotations

import json

import pytest

from app.game.state import STACK
from app.game.visibility import OMNISCIENT, SPECTATOR
from tests.game_helpers import act, find, make_session, zone


@pytest.fixture()
def s(cards):
    return make_session(cards, shuffle=True)


def dump(s, viewer) -> str:
    return json.dumps(s.view(viewer))


def hidden_identities(s, viewer):
    """card_ids / names of every card the viewer must not be able to identify."""
    from app.game.visibility import can_see

    out = []
    for c in s.state.cards.values():
        if not can_see(s.state, c, viewer):
            out.append(c)
    return out


def assert_no_leaks(s, viewer):
    from app.game.visibility import can_see

    view = s.view(viewer)
    view.pop("log")  # the log may legitimately name cards that were public at the time
    text = json.dumps(view)
    visible_prints = {c.card_id for c in s.state.cards.values() if can_see(s.state, c, viewer)}
    for c in hidden_identities(s, viewer):
        if c.card_id not in visible_prints:  # another, visible copy may share the printing id
            assert c.card_id not in text, f"{c.name} printing id leaked to {viewer}"
        v = view["cards"].get(c.id)
        if v is not None:
            assert v.get("hidden") is True and "name" not in v and "card_id" not in v


def test_opponent_sees_hand_count_not_contents(s):
    act(s, "p1", type="draw", count=7)
    view = s.view("p2")
    hand = view["zones"]["p1:hand"]
    assert len(hand) == 7
    assert all(view["cards"][cid]["hidden"] for cid in hand)
    assert_no_leaks(s, "p2")
    mine = s.view("p1")
    assert all("card_id" in mine["cards"][cid] for cid in hand)


def test_libraries_are_counts_only(s):
    for viewer in ("p1", "p2", SPECTATOR):
        view = s.view(viewer)
        for pid in ("p1", "p2"):
            lib = view["zones"][f"{pid}:library"]
            assert lib["known"] == []
            assert lib["count"] == len(zone(s.state, pid, "library"))
            for cid in zone(s.state, pid, "library"):
                assert cid not in view["cards"]
                assert cid not in json.dumps(view)  # not even the id
        assert_no_leaks(s, viewer)


def test_opponent_log_does_not_name_hidden_cards(s):
    act(s, "p1", type="draw", count=2)
    act(s, "p1", type="search_start", zone={"zone": "library"})
    target = zone(s.state, "p1", "library")[5]
    name = s.state.cards[target].name
    act(s, "p1", type="move", card_ids=[target], to={"zone": "hand"})
    act(s, "p1", type="search_end", shuffle=True)
    p2_log = json.dumps(s.view("p2")["log"])
    p1_log = json.dumps(s.view("p1")["log"])
    if name != "Mountain":  # Mountain appears publicly elsewhere
        assert name not in p2_log
        assert name in p1_log
    assert '"hidden": 1' in p2_log


def test_search_exposes_library_only_to_searcher(s):
    act(s, "p1", type="search_start", zone={"zone": "library"})
    mine = s.view("p1")
    assert len(mine["zones"]["p1:library"]["known"]) == 15
    theirs = s.view("p2")
    assert theirs["zones"]["p1:library"]["known"] == []
    assert theirs["searches"] == {"p1": "p1:library"}
    assert_no_leaks(s, "p2")
    act(s, "p1", type="search_end", shuffle=True)
    assert s.view("p1")["zones"]["p1:library"]["known"] == []


def test_face_down_card_hidden_from_opponent(s):
    act(s, "p1", type="draw", count=15)
    sol = find(s.state, "Sol Ring")
    act(s, "p1", type="move", card_ids=[sol.id], to={"zone": "battlefield"}, face_down=True, x=10, y=10)
    theirs = s.view("p2")["cards"][sol.id]
    assert theirs["hidden"] and theirs["face_down"] and theirs["x"] == 10
    assert "card_id" in s.view("p1")["cards"][sol.id]
    assert_no_leaks(s, "p2")
    act(s, "p1", type="face_down", card_ids=[sol.id], face_down=False)
    assert s.view("p2")["cards"][sol.id]["card_id"] == sol.card_id


def test_bounced_card_stays_known_until_shuffled(s):
    act(s, "p1", type="draw", count=15)
    sol = find(s.state, "Sol Ring")
    act(s, "p1", type="move", card_ids=[sol.id], to={"zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[sol.id], to={"zone": "hand"})
    assert s.view("p2")["cards"][sol.id]["card_id"] == sol.card_id  # everyone saw it bounce
    act(s, "p1", type="move", card_ids=[sol.id], to={"zone": "library"}, position="top")
    lib_view = s.view("p2")["zones"]["p1:library"]
    assert lib_view["known"] == [[0, sol.id]]
    act(s, "p1", type="shuffle")
    assert s.view("p2")["zones"]["p1:library"]["known"] == []
    assert_no_leaks(s, "p2")


def test_reveal_and_private_reveal(s):
    act(s, "p1", type="draw", count=3)
    a, b = zone(s.state, "p1", "hand")[:2]
    act(s, "p1", type="reveal", card_ids=[a])
    act(s, "p1", type="reveal", card_ids=[b], to=["p2"])
    assert "card_id" in s.view("p2")["cards"][a]
    assert "card_id" in s.view("p2")["cards"][b]
    assert s.view(SPECTATOR)["cards"][b]["hidden"]  # only revealed to p2
    assert "card_id" in s.view(SPECTATOR)["cards"][a]


def test_look_top_is_private(s):
    act(s, "p2", type="look_top", player="p1", count=2)
    assert len(s.view("p2")["zones"]["p1:library"]["known"]) == 2
    assert s.view("p1")["zones"]["p1:library"]["known"] == []  # the owner did not look
    assert_no_leaks(s, "p1")


def test_spectator_and_omniscient(s):
    act(s, "p1", type="draw", count=7)
    act(s, "p2", type="draw", count=7)
    assert_no_leaks(s, SPECTATOR)
    everything = s.view(OMNISCIENT)
    assert all("card_id" in everything["cards"][cid] for cid in zone(s.state, "p1", "hand"))
    assert everything["zones"]["p1:library"]["count"] == len(everything["zones"]["p1:library"]["known"])


def test_stack_and_abilities_public(s):
    act(s, "p1", type="draw", count=15)
    bolt = find(s.state, "Lightning Bolt")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"zone": "stack"})
    act(s, "p1", type="create_ability", text="Draw a card")
    view = s.view("p2")
    assert [view["cards"][c].get("name") for c in view["zones"][STACK]] == ["Lightning Bolt", "Ability"]


def test_token_shortcuts_private(s):
    s.state.players["p1"].token_shortcuts = ["x"]
    assert "token_shortcuts" not in s.view("p2")["players"][0]
    assert s.view("p1")["players"][0]["token_shortcuts"] == ["x"]


def test_mixed_game_never_leaks(s):
    """Run a busy sequence and check every viewer after every step."""
    steps = [
        ("p1", {"type": "draw", "count": 7}),
        ("p2", {"type": "draw", "count": 7}),
        ("p1", {"type": "mulligan"}),
        ("p2", {"type": "look_top", "player": "p2", "count": 3}),
        ("p2", {"type": "mill", "count": 2}),
        ("p1", {"type": "reveal_top"}),
        ("p1", {"type": "shuffle"}),
        ("p2", {"type": "search_start", "zone": {"zone": "library"}}),
        ("p2", {"type": "search_end", "shuffle": True}),
    ]
    for actor, payload in steps:
        s.perform(actor, payload)
        for viewer in ("p1", "p2", SPECTATOR):
            assert_no_leaks(s, viewer)
