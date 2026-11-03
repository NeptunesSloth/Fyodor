"""-- table toys -- the dice cannon and the hidden draw bag (app/game/handlers/toys.py, docs/3D_DIRECTION.md §7).

The server decides every outcome and records it on the action (replays and saves keep it); the bag's contents and a hidden
draw never reach another viewer; undoing a volley or a draw asks the table like a roll; a player who is out may still use the
toys (the Bag of Extras' objects are refused: it sends the ordinary token / counter actions)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.game import resolve
from app.game.errors import ActionError
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.game.visibility import OMNISCIENT, SPECTATOR
from tests.game_helpers import act, enable


def replay_matches(s: GameSession) -> None:
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def loaded(s: GameSession) -> GameSession:
    """Saved and loaded: the same table, in a new session (as after a restart)."""
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    state = GameState.model_validate(dumped)
    assert state.model_dump(mode="json") == dumped
    return GameSession(state, cards=s.cards)


def three(cards, *, rules: bool = False) -> GameSession:
    cmd, land = cards.resolve("Krenko, Mob Boss"), cards.resolve("Mountain")
    setups = [PlayerSetup(n, cards=[DeckCard("commander", 1, cmd["name"], cmd["id"]), DeckCard("main", 9, land["name"], land["id"])])
              for n in ("Alice", "Bob", "Cleo")]
    state = new_game(setups, shuffle=False, first_player=0)
    if rules:
        enable(state)
    return GameSession(state, cards=cards)


def script(monkeypatch, values: list[int]) -> list[int]:
    """The server's random numbers, in order (each randint answers the next one)."""
    left = list(values)

    def randint(lo: int, hi: int) -> int:
        v = left.pop(0)
        assert lo <= v <= hi, (lo, v, hi)
        return v

    monkeypatch.setattr(resolve._rng, "randint", randint)
    return left


def last_line(s: GameSession, viewer: str = "p1") -> dict:
    return s.view(viewer)["log"][-1]


def line_text(entry: dict) -> str:
    return "".join(p.get("t", "") for p in entry["parts"])


def last(s: GameSession):
    return s.history.actions[s.history.cursor - 1]


# ---------------------------------------------------------------------------- the dice cannon


def test_a_volley_is_the_servers_dice_landing_in_front_of_the_firer(cards):
    s = three(cards)
    act(s, "p2", type="cannon", sides=6, count=3)
    entry = last_line(s)
    roll = entry["roll"]
    assert entry["kind"] == "dice" and entry["actor"] == "p2"
    assert roll["sides"] == 6 and len(roll["results"]) == 3 and all(1 <= v <= 6 for v in roll["results"])
    assert roll["cannon"] == {"mode": "volley", "players": ["p2"] * 3, "rounds": [0, 0, 0], "winner": None}
    r = roll["results"]
    assert line_text(entry) == f"Bob fired 3d6 from the dice cannon: {r[0]}, {r[1]}, {r[2]} (total {sum(r)})"
    assert last(s).shown == "random"  # undoing it asks the table, as a roll does
    with pytest.raises(ActionError, match="take back a random result"):
        s.undo("p1", others=["p2", "p3"])
    loaded(s)


def test_a_client_cannot_choose_the_numbers(cards, monkeypatch):
    s = three(cards)
    script(monkeypatch, [3])
    act(s, "p1", type="cannon", sides=20, count=1, r={"results": [20], "players": ["p2"], "rounds": [0]})
    assert s.state.log[-1].roll.results == [3] and s.state.log[-1].roll.cannon.players == ["p1"]
    with pytest.raises(ValidationError):
        act(s, "p1", type="cannon", sides=6, count=13)  # twelve dice a volley at most (the tables show twelve)


def test_who_goes_first_fires_a_d20_at_each_player_and_refires_the_tied_highest(cards, monkeypatch):
    s = three(cards)
    rest = script(monkeypatch, [12, 19, 19, 7, 15])
    act(s, "p1", type="cannon", mode="first")
    assert rest == []
    entry = last_line(s, "p2")
    assert entry["roll"]["results"] == [12, 19, 19, 7, 15]
    assert entry["roll"]["cannon"] == {"mode": "first", "players": ["p1", "p2", "p3", "p2", "p3"], "rounds": [0, 0, 0, 1, 1], "winner": "p3"}
    assert line_text(entry) == ("Cleo goes first (15) — Alice fired the dice cannon, a d20 at each player: Alice 12, Bob 19, Cleo 19; "
                                "the tie re-fired: Bob 7, Cleo 15")
    assert last(s).shown == "random"
    # a tie that ties again is fired again, among the tied players only
    script(monkeypatch, [18, 4, 18, 11, 11, 3, 20])
    act(s, "p2", type="cannon", mode="first")
    entry = last_line(s)
    assert entry["roll"]["cannon"]["rounds"] == [0, 0, 0, 1, 1, 2, 2]
    assert entry["roll"]["cannon"]["players"] == ["p1", "p2", "p3", "p1", "p3", "p1", "p3"]
    assert line_text(entry) == ("Cleo goes first (20) — Bob fired the dice cannon, a d20 at each player: Alice 18, Bob 4, Cleo 18; "
                                "the tie re-fired: Alice 11, Cleo 11; the tie re-fired: Alice 3, Cleo 20")
    # a tie below the highest doesn't matter
    s2 = three(cards)
    script(monkeypatch, [4, 4, 18])
    act(s2, "p2", type="cannon", mode="first")
    assert line_text(last_line(s2)) == "Cleo goes first (18) — Bob fired the dice cannon, a d20 at each player: Alice 4, Bob 4, Cleo 18"
    for t in (s, s2):
        loaded(t)


def test_who_goes_first_after_a_double_tie(cards, monkeypatch):
    s = three(cards)
    script(monkeypatch, [20, 20, 20, 9, 9, 9, 3, 17, 17, 2, 6])
    act(s, "p1", type="cannon", mode="first")
    entry = last_line(s)
    assert entry["roll"]["cannon"]["rounds"] == [0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3]
    assert entry["roll"]["cannon"]["winner"] == "p3"
    assert line_text(entry).endswith("the tie re-fired: Alice 9, Bob 9, Cleo 9; the tie re-fired: Alice 3, Bob 17, Cleo 17; "
                                     "the tie re-fired: Bob 2, Cleo 6")
    assert line_text(entry).startswith("Cleo goes first (6)")
    replay_matches(s)


def test_who_goes_first_counts_only_the_players_still_in_the_game(cards, monkeypatch):
    s = three(cards, rules=True)
    act(s, "p3", type="concede")
    script(monkeypatch, [5, 11])
    act(s, "p3", type="cannon", mode="first")  # a player who is out may still fire it (a table toy, like the dice)
    entry = last_line(s)
    assert entry["roll"]["cannon"]["players"] == ["p1", "p2"] and entry["roll"]["cannon"]["winner"] == "p2"
    assert line_text(entry).startswith("Bob goes first (11) — Cleo fired")
    act(s, "p2", type="concede")
    with pytest.raises(ActionError, match="needs two players"):
        act(s, "p1", type="cannon", mode="first")
    loaded(s)


def test_the_cannon_is_a_toy_not_a_rules_roll(cards):
    """With automation on it is no manual override, and the log line isn't marked done by hand."""
    s = three(cards, rules=True)
    before = s.state.rules.overrides
    act(s, "p1", type="cannon", sides=6, count=2)
    assert s.state.rules.overrides == before
    assert not s.state.log[-1].manual
    replay_matches(s)


# ---------------------------------------------------------------------------- the draw bag

SECRET = ["Zephyr Team", "Quokka Team", "Marmot Team", "Ocelot Team"]


def leaks(view: dict, words: list[str]) -> list[str]:
    blob = json.dumps(view)
    return [w for w in words if w in blob]


def test_the_bags_contents_are_never_in_any_view(cards):
    s = three(cards)
    act(s, "p1", type="bag_fill", chits=SECRET, replace=True)
    assert s.state.bag.chits == SECRET
    for viewer in ("p1", "p2", "p3", SPECTATOR, OMNISCIENT):
        view = s.view(viewer)
        assert view["bag"] == {"count": 4, "drawn": [], "drawn_count": 0}
        assert leaks(view, SECRET) == []  # not even the player who filled it
    assert line_text(last_line(s)) == "Alice filled the draw bag with 4 chits"
    assert last(s).shown is None  # filling shows nothing: undone at once
    act(s, "p2", type="bag_fill", chits=["  Wombat Team  ", ""])
    assert s.state.bag.chits[-1] == "Wombat Team" and line_text(last_line(s)) == "Bob put 1 chit in the draw bag (5 inside)"
    s.undo("p3", others=["p1", "p2"])
    assert len(s.state.bag.chits) == 4
    loaded(s)


def test_a_hidden_draw_is_only_its_drawers_and_a_revealed_one_everyones(cards, monkeypatch):
    s = three(cards)
    act(s, "p1", type="bag_fill", chits=SECRET, replace=True)
    script(monkeypatch, [2])
    act(s, "p2", type="bag_draw", reveal=False)
    drawn = SECRET[2]
    assert s.state.bag.chits == [c for c in SECRET if c != drawn]
    for viewer in ("p1", "p3", SPECTATOR):
        view = s.view(viewer)
        assert leaks(view, SECRET) == [], viewer
        assert view["bag"]["count"] == 3 and view["bag"]["drawn"] == [{"player": "p2", "chit": None, "shown": False}]
        entry = view["log"][-1]
        assert line_text(entry) == "Bob drew a chit from the draw bag and kept it hidden (3 left)"
        assert entry["bag"] == {"player": "p2", "hidden": True, "left": 3, "chit": None}
    mine = s.view("p2")
    assert leaks(mine, SECRET) == [drawn]  # the drawer sees their chit, nothing else of the bag
    assert mine["bag"]["drawn"] == [{"player": "p2", "chit": drawn, "shown": False}]
    assert mine["log"][-1]["bag"]["chit"] == drawn
    assert last(s).shown == "random"
    with pytest.raises(ActionError, match="take back a random result"):
        s.undo("p2", others=["p1", "p3"])
    # the drawer shows it: now everyone sees it (the earlier log line stays as it was)
    act(s, "p2", type="bag_show")
    assert line_text(last_line(s, "p3")) == f"Bob showed the chit they drew: “{drawn}”"
    assert s.view("p3")["bag"]["drawn"] == [{"player": "p2", "chit": drawn, "shown": True}]
    assert s.view("p3")["log"][-2]["bag"]["chit"] is None
    assert last(s).shown == "reveal"
    with pytest.raises(ActionError, match="no hidden chit"):
        act(s, "p2", type="bag_show")
    # a draw for everyone
    script(monkeypatch, [0])
    act(s, "p3", type="bag_draw")
    entry = last_line(s, "p1")
    assert line_text(entry) == f"Cleo drew “{SECRET[0]}” from the draw bag (2 left)"
    assert entry["bag"] == {"player": "p3", "hidden": False, "left": 2, "chit": SECRET[0]}
    assert leaks(s.view("p1"), SECRET) == [SECRET[0], drawn]
    loaded(s)


def test_the_draw_is_recorded_and_replayed_not_drawn_again(cards):
    s = three(cards)
    act(s, "p1", type="bag_fill", chits=[str(n) for n in range(1, 21)], replace=True)
    for _ in range(5):
        act(s, "p1", type="bag_draw", reveal=False)
    drawn = [d.chit for d in s.state.bag.drawn]
    assert len(set(drawn)) == 5 and len(s.state.bag.chits) == 15
    rebuilt = s.history.rebuild()
    assert [d.chit for d in rebuilt.bag.drawn] == drawn
    t = loaded(s)
    assert [d.chit for d in t.state.bag.drawn] == drawn


def test_return_empty_and_limits(cards):
    s = three(cards)
    with pytest.raises(ActionError, match="empty"):
        act(s, "p1", type="bag_draw")
    with pytest.raises(ActionError, match="already empty"):
        act(s, "p1", type="bag_empty")
    with pytest.raises(ActionError, match="No chits have been drawn"):
        act(s, "p1", type="bag_return")
    with pytest.raises(ValidationError):
        act(s, "p1", type="bag_fill", chits=["   "])
    act(s, "p1", type="bag_fill", chits=["Ann", "Ben", "Cid"], replace=True)
    act(s, "p2", type="bag_draw")
    act(s, "p3", type="bag_draw", reveal=False)
    act(s, "p1", type="bag_return")
    assert sorted(s.state.bag.chits) == ["Ann", "Ben", "Cid"] and s.state.bag.drawn == []
    assert line_text(last_line(s)) == "Alice put the drawn 2 chits back in the draw bag (3 inside)"
    act(s, "p1", type="bag_fill", chits=[f"c{n}" for n in range(100)])
    act(s, "p1", type="bag_fill", chits=[f"d{n}" for n in range(97)])
    with pytest.raises(ActionError, match="200 chits at most"):
        act(s, "p1", type="bag_fill", chits=["one too many"])
    act(s, "p2", type="bag_empty")
    assert s.state.bag.chits == [] and line_text(last_line(s)) == "Bob emptied the draw bag"
    loaded(s)


def test_an_older_save_without_toys_loads(cards):
    s = three(cards)
    act(s, "p1", type="roll", sides=6, count=2)
    dumped = s.state.model_dump(mode="json")
    dumped.pop("bag")
    for entry in dumped["log"]:
        entry.pop("bag", None)
        if entry.get("roll"):
            entry["roll"].pop("cannon", None)
    state = GameState.model_validate(dumped)
    assert state.bag.chits == [] and state.log[-1].roll is not None and state.log[-1].roll.cannon is None
    t = GameSession(state, cards=cards)
    act(t, "p2", type="bag_fill", chits=["x"])
    act(t, "p2", type="cannon", sides=8, count=2)


# ---------------------------------------------------------------------------- a player who is out


def test_a_player_who_is_out_keeps_the_toys_but_not_the_bag_of_extras(cards):
    s = three(cards, rules=True)
    act(s, "p3", type="concede")
    act(s, "p3", type="cannon", sides=6, count=2)
    act(s, "p3", type="bag_fill", chits=["Red", "Blue"], replace=True)
    act(s, "p3", type="bag_draw", reveal=False)
    act(s, "p3", type="bag_show")
    act(s, "p3", type="bag_return")
    act(s, "p3", type="bag_empty")
    # the Bag of Extras sends the ordinary object actions: a token, a counter, a resource
    for payload in ({"type": "create_token", "token": {"name": "Treasure", "type_line": "Token Artifact — Treasure"}},
                    {"type": "resource", "key": "energy", "delta": 1}):
        with pytest.raises(ActionError, match="You're out of this game"):
            act(s, "p3", **payload)
    loaded(s)
