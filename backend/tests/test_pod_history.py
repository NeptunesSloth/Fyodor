"""-- pod history -- each recorded game keeps the order players went out and a compact, public final board
(docs/GAME_NIGHT_FLOW.md, "Pod session and game are different objects").

The order is read from public facts after every applied action (``app.game.eliminations``), so a replay and a save/load agree;
it is stored with the result in pod stats and in the night's history (the session recap). The final board is what a spectator
sees on the table when the result is recorded (``app.stats.recap``): never a hand, a library or a face-down card's name.
"""

from __future__ import annotations

import json
import threading

from app.game.eliminations import how
from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.multiplayer.night import Night
from app.stats.recap import FACE_DOWN, MAX_NAMES, final_board
from app.stats.repository import Participant, PodStats
from app.storage.app_db import MIGRATIONS
from app.storage.db import connect, migrate
from tests.game_helpers import act, enable, find, make_session


def replay_matches(s: GameSession) -> None:
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def roundtrip(s: GameSession) -> None:
    replay_matches(s)
    dumped = s.state.model_dump(mode="json")
    assert GameState.model_validate(dumped).model_dump(mode="json") == dumped


def four(cards) -> GameSession:
    cmd, land = cards.resolve("Krenko, Mob Boss"), cards.resolve("Mountain")
    setups = [PlayerSetup(n, cards=[DeckCard("commander", 1, cmd["name"], cmd["id"]), DeckCard("main", 9, land["name"], land["id"])])
              for n in ("Ann", "Ben", "Cat", "Dan")]
    state = new_game(setups, shuffle=False, first_player=0)
    enable(state)
    return GameSession(state, cards=cards)


def next_turn(s: GameSession, limit: int = 300) -> None:
    """Pass priority (no attackers, no blockers) into the next turn."""
    turn = s.state.turn.number
    for _ in range(limit):
        if s.state.turn.number > turn and not s.state.zones.get("stack") and s.state.rules.decision is None:
            return
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached the next turn")


def order(s: GameSession) -> list[tuple[str, int | None, str, int]]:
    return [(e.player, e.turn, e.how, e.seq) for e in s.state.eliminations]


# --------------------------------------------------------------------------- the elimination order


def test_a_concession_a_commander_kill_and_a_draw_are_recorded_in_order_and_kept_with_the_result(client):
    services = client.app.state.services
    s = four(services.cards)
    room = services.hub.create_room(s, mode="local")
    gid = room.id
    act(s, "p4", type="concede")  # Dan concedes on turn 1
    assert order(s) == [("p4", 1, "conceded", s.state.seq)]
    next_turn(s)
    krenko = find(s.state, "Krenko, Mob Boss", "p1")
    act(s, "p3", type="commander_damage", player="p3", commander=krenko.commander_key, delta=21, affect_life=False)
    assert [e.player for e in s.state.eliminations] == ["p4"]  # by hand: nothing yet, the engine checks at the next priority
    act(s, s.state.rules.priority, type="pass_priority")
    turn_cat = s.state.turn.number
    assert s.state.rules.lost == {"p3": "21 combat damage from one commander"}
    assert order(s)[1][:3] == ("p3", turn_cat, "commander_damage") and turn_cat >= 2
    next_turn(s)
    # Ann and Ben both at 0 life: the same state-based check puts both out, and nobody is left (104.4a: a draw)
    act(s, "p1", type="set_life", player="p1", value=0)
    act(s, "p2", type="set_life", player="p2", value=-3)
    act(s, s.state.rules.priority, type="pass_priority")
    r = s.state.rules
    assert r.winner is None and r.draw_reason is not None
    last = order(s)[2:]
    assert [e[0] for e in last] == ["p1", "p2"] and {e[2] for e in last} == {"life"} and last[0][3] == last[1][3]
    assert last[0][1] == s.state.turn.number > turn_cat
    roundtrip(s)  # replayed from the actions alone, and saved and loaded: the same order

    # the rules result, confirmed: pod stats and the night's history keep the order
    services.hub.after_change(room)
    assert client.post(f"/api/games/{gid}/night/answer", json={"agree": True, "as_player": "p1"}).status_code == 200
    result = client.get(f"/api/games/{gid}/result").json()
    assert result["result_type"] == "draw"
    turn_draw = s.state.turn.number
    assert result["eliminations"] == [
        {"seat": "p4", "name": "Dan", "place": 1, "turn": 1, "how": "conceded", "reason": ""},
        {"seat": "p3", "name": "Cat", "place": 2, "turn": turn_cat, "how": "commander_damage", "reason": "21 combat damage from one commander"},
        {"seat": "p1", "name": "Ann", "place": 3, "turn": turn_draw, "how": "life", "reason": "0 or less life"},
        {"seat": "p2", "name": "Ben", "place": 3, "turn": turn_draw, "how": "life", "reason": "0 or less life"},
    ]
    assert [b["name"] for b in result["final_board"]] == ["Ann", "Ben", "Cat", "Dan"]
    assert result["final_board"][1]["life"] == -3
    night = room.night.public(room.seat_name)
    entry = night["history"][0]
    assert [(e["name"], e["place"], e["how"]) for e in entry["eliminations"]] == [
        ("Dan", 1, "conceded"), ("Cat", 2, "commander_damage"), ("Ann", 3, "life"), ("Ben", 3, "life")]
    assert entry["result_id"] == result["id"] and "final_board" not in entry  # the board stays in pod stats: small payloads
    one = client.get(f"/api/pod/results/{result['id']}")
    assert one.status_code == 200 and one.json()["final_board"] == result["final_board"]
    assert client.get("/api/pod/results/nope").status_code == 404
    assert client.get("/api/pod/results").json()[0]["eliminations"] == result["eliminations"]
    # the night's record (crash recovery) keeps it too
    assert Night.from_meta(json.loads(json.dumps(room.night.meta()))).history[0]["eliminations"] == entry["eliminations"]
    replay_matches(s)


def test_an_undo_takes_an_elimination_back_and_a_redo_brings_it_back(cards):
    s = four(cards)
    act(s, "p2", type="concede")
    assert [e.player for e in s.state.eliminations] == ["p2"]
    s.undo("p1")  # (a player still in, or the host: Ben is out, his own undo is refused, tests/test_out_of_game_actions.py)
    assert s.state.eliminations == []
    s.redo("p2")
    assert order(s) == [("p2", 1, "conceded", s.state.seq)]
    roundtrip(s)


def test_a_player_the_host_removes_has_left_the_table(cards):
    s = make_session(cards)
    s.state.players["p3"] = s.state.players["p2"].model_copy(update={"id": "p3", "name": "Cat"})
    s.state.seat_order.append("p3")
    s = GameSession(s.state, cards=cards)
    act(s, "p1", type="remove_player", player="p3")
    assert order(s) == [("p3", 1, "left", s.state.seq)]
    roundtrip(s)


def test_an_older_save_lists_who_was_already_out_with_no_turn(cards):
    s = four(cards)
    act(s, "p3", type="concede")
    dumped = s.state.model_dump(mode="json")
    del dumped["eliminations"]  # saved before the order was kept
    old = GameSession(GameState.model_validate(dumped), cards=cards)
    assert old.state.eliminations == []
    act(old, "p2", type="concede")
    assert [(e.player, e.turn, e.how) for e in old.state.eliminations] == [("p3", None, "conceded"), ("p2", 1, "conceded")]
    roundtrip(old)


def test_how_each_engine_loss_reads():
    assert how("0 or less life") == "life"
    assert how("10 poison counters") == "poison"
    assert how("21 combat damage from one commander") == "commander_damage"
    assert how("drew from an empty library") == "empty_library"
    assert how("an effect") == "effect"
    assert how("Ann won the game") == "opponent_won"
    assert how("something new") == "out"


# --------------------------------------------------------------------------- the final board: public only


def test_the_final_board_is_public_only_and_small(client):
    services = client.app.state.services
    s = make_session(services.cards)  # Alice (Krenko) and Bob (Atraxa); no automation
    room = services.hub.create_room(s, mode="local")
    gid = room.id
    lib = s.state.zones["p1:library"]
    by_name = {s.state.cards[c].name: c for c in lib}
    act(s, "p1", type="move", card_ids=[by_name["Sol Ring"]], to={"zone": "battlefield"})
    mountains = [c for c in lib if s.state.cards[c].name == "Mountain"][:3]
    act(s, "p1", type="move", card_ids=mountains, to={"zone": "battlefield"})
    act(s, "p1", type="move", card_ids=[by_name["Llanowar Elves"]], to={"zone": "battlefield"})
    act(s, "p1", type="face_down", card_ids=[by_name["Llanowar Elves"]], face_down=True)
    act(s, "p1", type="move", card_ids=[by_name["Lightning Bolt"]], to={"zone": "graveyard"})
    act(s, "p1", type="create_token", player="p1", token={"name": "Goblin", "type_line": "Token Creature — Goblin",
                                                         "power": "1", "toughness": "1", "colors": ["R"]})
    act(s, "p1", type="draw", player="p1", count=2)
    act(s, "p2", type="draw", player="p2", count=7)
    act(s, "p2", type="resource", player="p2", key="poison", delta=4)
    act(s, "p2", type="set_life", player="p2", value=17)
    hidden = {s.state.cards[c].name for p in ("p1", "p2") for z in ("hand", "library") for c in s.state.zones[f"{p}:{z}"]}
    shown = {s.state.cards[c].name for p in ("p1", "p2") for c in s.state.zones[f"{p}:battlefield"]
             if not s.state.cards[c].face_down}
    secret = hidden - shown - {"Krenko, Mob Boss", "Atraxa, Praetors' Voice"}
    assert {"Fire // Ice", "Counterspell", "Arcane Signet"} <= secret and any(n.startswith("Delver of Secrets") for n in secret)
    res = client.post(f"/api/games/{gid}/result", json={"result_type": "single", "winners": ["p1"]})
    assert res.status_code == 201, res.text
    result = res.json()
    alice, bob = result["final_board"]
    assert alice["name"] == "Alice" and alice["life"] == 40 and alice["poison"] == 0
    assert alice["commanders"] == ["Krenko, Mob Boss"] and alice["graveyard"] == 1 and alice["exile"] == 0
    assert alice["permanents"] == [{"name": "Goblin", "count": 1}, {"name": "Sol Ring", "count": 1},
                                   {"name": FACE_DOWN, "count": 1}, {"name": "Mountain", "count": 3, "land": True}]
    assert (bob["life"], bob["poison"], bob["permanents"], bob["more"]) == (17, 4, [], 0)
    # privacy: no hand or library card and no face-down card's name, anywhere in the record or the night's history
    everything = json.dumps(result) + json.dumps(room.night.public(room.seat_name)) + json.dumps(client.get("/api/pod/results").json())
    for name in secret | {"Llanowar Elves"}:
        assert name not in everything, name
    assert result["eliminations"] == []  # nobody went out: Alice won by agreement
    replay_matches(s)


def test_the_final_board_keeps_at_most_a_few_names_per_player(cards):
    s = make_session(cards)
    for i in range(MAX_NAMES + 5):
        act(s, "p1", type="create_token", player="p1", token={"name": f"Thing {i:02d}", "type_line": "Token Artifact", "colors": []})
    mine = final_board(s.state, {})[0]
    assert len(mine["permanents"]) == MAX_NAMES and mine["more"] == 5


# --------------------------------------------------------------------------- older results


def test_older_results_load_with_no_order_and_no_board(tmp_path):
    conn = connect(tmp_path / "app.sqlite")
    migrate(conn, MIGRATIONS[:8], name="app")  # pod stats before this change
    conn.execute("INSERT INTO game_results (id, game_id, result_type, recorded_at) VALUES ('r1', 'g1', 'draw', '2026-01-01')")
    conn.execute("INSERT INTO pod_players (id, name, name_key, created_at) VALUES ('a', 'Ann', 'ann', '2026-01-01')")
    conn.execute("INSERT INTO game_result_players (result_id, seat, player_id, player_name, outcome) VALUES ('r1', 'p1', 'a', 'Ann', 'draw')")
    conn.commit()
    migrate(conn, MIGRATIONS, name="app")
    stats = PodStats(conn, threading.RLock())
    old = stats.get("r1")
    assert old["eliminations"] == [] and old["final_board"] == []
    new = stats.record(game_id="g2", result_type="single", participants=[Participant("p1", "Ann"), Participant("p2", "Ben")],
                       winners=["p1"])
    assert new["eliminations"] == [] and new["final_board"] == []
