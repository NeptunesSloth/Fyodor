"""-- target dummy -- Sandbox's practice opponent (app/game/handlers/dummy.py, app/game/dummy.py): a seat with no deck that never takes
a turn, never holds the game up (the server answers for it, as recorded actions), loses as anyone does, and comes back with Reset
dummy. Everything replays the same through undo, redo and a reload."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.history import History
from app.game.session import GameSession
from app.game.state import GameSettings, GameState
from app.multiplayer.hub import GameHub
from tests.game_helpers import act, deck, enable, engine_pays, find, turn_on


def sandbox(cards, *, rules: bool = False, test_objects: bool = True) -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", [(12, "Mountain"), (2, "Lightning Bolt"), (1, "Grizzly Bears"), (1, "Monastery Swiftspear")])
    settings = GameSettings(starting_life=40, allow_test_objects=test_objects)
    state = new_game([PlayerSetup("Alice", cards=alice)], name="Deck test", format="sandbox", settings=settings, shuffle=False,
                     first_player=0)
    if rules:
        enable(state, "full")
    return GameSession(state, cards=cards)


def with_dummy(cards, *, rules: bool = False) -> GameSession:
    s = sandbox(cards, rules=rules)
    act(s, "p1", type="add_dummy")
    if rules:
        engine_pays(s.state)
    return s


def replay_matches(s: GameSession) -> None:
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")
    again = History.from_dict(s.history.to_dict())
    assert again.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def to_hand(s: GameSession, name: str) -> str:
    card = next(c for c in s.state.cards.values() if c.name == name and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "hand"})
    return card.id


def pass_until(s: GameSession, turn: int, phase: str) -> None:
    for _ in range(60):
        if (s.state.turn.number, s.state.turn.phase) == (turn, phase) and s.state.rules.priority == "p1":
            return
        act(s, "p1", type="pass_priority")
    raise AssertionError(f"stuck at turn {s.state.turn.number}, {s.state.turn.phase}")


def bolt_the_dummy(s: GameSession) -> None:
    """Main phase, priority: play a Mountain and cast Lightning Bolt at the dummy, then pass so it resolves."""
    if not any(s.state.cards[c].name == "Mountain" for c in s.state.zones["p1:battlefield"]):
        act(s, "p1", type="play_land", card_id=to_hand(s, "Mountain"))
    else:
        mountain = next(c for c in s.state.zones["p1:battlefield"] if s.state.cards[c].name == "Mountain")
        act(s, "p1", type="untap_all")  # (another Bolt this turn: the same Mountain, by hand)
        assert not s.state.cards[mountain].tapped
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt"), targets=["p2"])
    if s.state.zones["stack"]:  # (the engine passes once for the caster, Arena-style; the dummy never holds it up)
        act(s, "p1", type="pass_priority")
    assert not s.state.zones["stack"]


# ---------------------------------------------------------------------------- seating it


def test_add_a_target_dummy(cards):
    s = with_dummy(cards)
    st = s.state
    assert st.seat_order == ["p1", "p2"]
    dummy = st.players["p2"]
    assert dummy.dummy and dummy.name == "Target Dummy" and dummy.life == 40
    assert dummy.resources["poison"] == 0 and dummy.commander_damage == {}
    assert st.zones["p2:library"] == [] and st.zones["p2:battlefield"] == []
    act(s, "p1", type="add_dummy")  # (up to three: the second is numbered)
    assert st.players["p3"].name == "Target Dummy 2"
    with pytest.raises(ActionError, match="acts on its own"):  # (a hot-seat table can act as any seat: not as the dummy)
        act(s, "p2", type="life", player="p2", delta=-1)
    replay_matches(s)


def test_up_to_three_dummies_each_with_its_name_blocks_and_life(cards):
    """The Sandbox start seats up to three dummies, each as the host set it up; Reset dummy and Dummy blocks name the one they mean."""
    s = sandbox(cards)
    act(s, "p1", type="add_dummy", name="Wall", blocks="all")
    act(s, "p1", type="add_dummy", blocks="chump", life=20)
    act(s, "p1", type="add_dummy", name="  ")  # (a blank name: the numbered default)
    st = s.state
    assert st.seat_order == ["p1", "p2", "p3", "p4"]
    got = [(st.players[p].name, st.players[p].dummy_blocks, st.players[p].life, st.players[p].dummy) for p in ("p2", "p3", "p4")]
    assert got == [("Wall", "all", 40, True), ("Target Dummy 2", "chump", 20, True), ("Target Dummy 3", "never", 40, True)]
    # (a refused action leaves the session on a restored copy of the state: read s.state from here on)
    with pytest.raises(ActionError, match="already has 3 target dummies"):
        act(s, "p1", type="add_dummy")
    act(s, "p1", type="set_dummy", player="p4", blocks="chump")
    assert s.state.players["p4"].dummy_blocks == "chump" and s.state.players["p2"].dummy_blocks == "all"
    act(s, "p1", type="set_dummy", blocks="never")  # (no player: the first, as older histories recorded it)
    assert s.state.players["p2"].dummy_blocks == "never"
    with pytest.raises(ActionError, match="no such target dummy"):
        act(s, "p1", type="set_dummy", player="p1", blocks="all")
    act(s, "p1", type="set_life", player="p3", value=3)
    act(s, "p1", type="set_life", player="p2", value=5)
    act(s, "p1", type="reset_dummy", player="p3")
    assert s.state.players["p3"].life == 20 and s.state.players["p2"].life == 5  # (its own starting life; the others untouched)
    replay_matches(s)
    loaded = GameState.model_validate(s.state.model_dump(mode="json"))  # save / load
    again = GameSession(loaded, cards=cards, history=History.from_dict(s.history.to_dict()))
    assert again.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")
    assert [again.state.players[p].name for p in ("p2", "p3", "p4")] == ["Wall", "Target Dummy 2", "Target Dummy 3"]


def test_with_the_rules_on_several_dummies_never_hold_the_game_up(cards):
    """Every dummy is answered for (not only the first): turns cycle straight back to Alice, and a reload replays them all."""
    s = sandbox(cards)
    act(s, "p1", type="add_dummy")
    act(s, "p1", type="add_dummy", life=10)
    act(s, "p1", type="add_dummy", blocks="all")
    turn_on(s, "full")
    pass_until(s, 1, "main1")
    pass_until(s, 2, "main1")
    pass_until(s, 3, "main1")
    r = s.state.rules
    assert s.state.turn.active_player == "p1" and r.lost == {} and r.winner is None
    replay_matches(s)
    loaded = GameState.model_validate(s.state.model_dump(mode="json"))
    again = GameSession(loaded, cards=cards, history=History.from_dict(s.history.to_dict()))
    assert again.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")
    pass_until(again, 4, "main1")


def test_the_third_dummy_blocks_as_set(cards):
    """The server answers for every dummy, not only the first: the third declares its own blocks when it is attacked."""
    s = sandbox(cards)
    act(s, "p1", type="add_dummy")
    act(s, "p1", type="add_dummy")
    act(s, "p1", type="add_dummy", blocks="all")
    wall = spawned(s, cards, "Grizzly Bears", "p4")
    bears = spawned(s, cards, "Grizzly Bears")
    turn_on(s, "full")
    engine_pays(s.state)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears, "target": "p4"}])
    declared = [a for a in s.history.actions[:s.history.cursor] if a.type == "declare_blockers"]
    assert [a.actor for a in declared] == ["p4"] and {b.blocker_id: b.attacker_id for b in declared[-1].blocks} == {wall: bears}
    d = s.state.rules.decision
    assert d is None or d.player == "p1"  # (nothing left waiting on a dummy)
    replay_matches(s)


def test_the_dummy_is_a_solo_tool(cards):
    s = sandbox(cards, test_objects=False)
    with pytest.raises(ActionError, match="test cards are off"):
        act(s, "p1", type="add_dummy")


def test_undo_takes_the_dummy_away(cards):
    s = with_dummy(cards)
    s.undo("p1")
    assert s.state.seat_order == ["p1"] and "p2" not in s.state.players
    s.redo("p1")
    assert s.state.players["p2"].dummy


def test_nobody_can_take_the_dummys_seat(cards):
    hub = GameHub()
    s = sandbox(cards)
    room = hub.create_room(s, mode="lan")
    hub.claim_seat(room, name="Alice", seat="p1")
    act(s, "p1", type="add_dummy")
    hub.after_change(room)
    assert "p2" in room.seats and room.seats["p2"].token is None
    with pytest.raises(PermissionError):
        hub.claim_seat(room, name="Eve", seat="p2")
    with pytest.raises(PermissionError, match="full"):
        hub.claim_seat(room, name="Eve", seat=None)
    s.undo("p1")
    hub.after_change(room)
    assert "p2" not in room.seats


# ---------------------------------------------------------------------------- manual table: its turns are skipped


def test_manual_turns_skip_the_dummy(cards):
    s = with_dummy(cards)
    act(s, "p1", type="next_turn", force=True)
    assert (s.state.turn.number, s.state.turn.active_player) == (2, "p1")
    act(s, "p1", type="next_turn", force=True)
    assert (s.state.turn.number, s.state.turn.active_player) == (3, "p1")
    replay_matches(s)


def test_the_response_helper_never_waits_for_the_dummy(cards):
    s = with_dummy(cards)
    s.state.settings.priority_helper = "simple"
    act(s, "p1", type="next_turn")  # (would ask the others first: there are none but the dummy)
    assert s.state.response is None and s.state.turn.number == 2


# ---------------------------------------------------------------------------- rules on: the server answers for it


def test_with_the_rules_on_a_turn_cycle_never_waits_for_the_dummy(cards):
    s = with_dummy(cards, rules=True)
    pass_until(s, 1, "main1")
    library = len(s.state.zones["p1:library"])
    pass_until(s, 2, "main1")  # straight into Alice's next turn: the dummy's is skipped
    assert s.state.turn.active_player == "p1" and len(s.state.zones["p1:library"]) == library - 1
    assert s.state.zones["p2:hand"] == [] and s.state.rules.lost == {} and s.state.rules.winner is None
    bolt_the_dummy(s)
    assert s.state.players["p2"].life == 37
    assert s.state.rules.priority == "p1" and not s.state.zones["stack"]
    replay_matches(s)


def test_a_draw_from_its_empty_library_doesnt_end_the_test(cards):
    """704.5b doesn't apply to the dummy: an effect that makes it draw (Nekusar, a wheel) is not how a damage test should end."""
    s = with_dummy(cards, rules=True)
    pass_until(s, 1, "main1")
    s.state.rules.drew_from_empty.append("p2")  # (as app.rules.replace records a draw from an empty library)
    s.state.rules.drew_from_empty.append("p1")
    act(s, "p1", type="pass_priority")  # the next state-based check
    r = s.state.rules
    assert "p2" not in r.lost and "p2" not in r.drew_from_empty
    assert r.lost.get("p1") == "drew from an empty library"  # (Alice still does: the rule is unchanged for her)


def test_lethal_then_reset_dummy(cards):
    s = with_dummy(cards, rules=True)
    pass_until(s, 1, "main1")
    act(s, "p1", type="set_life", player="p2", value=3)
    bolt_the_dummy(s)
    r = s.state.rules
    assert s.state.players["p2"].life == 0 and "p2" in r.lost and r.winner == "p1"
    assert [e.player for e in s.state.eliminations] == ["p2"]
    act(s, "p1", type="resource", player="p2", key="poison", delta=1)  # (the table tools still work)
    act(s, "p1", type="reset_dummy")
    r = s.state.rules
    assert s.state.players["p2"].life == 40 and r.lost == {} and r.winner is None and s.state.eliminations == []
    bolt_the_dummy(s)  # and testing goes on
    assert s.state.players["p2"].life == 37
    replay_matches(s)


def test_reset_dummy_clears_it_and_returns_what_it_was_given(cards):
    s = with_dummy(cards)
    act(s, "p1", type="spawn_card", card_id=cards.resolve("Grizzly Bears")["id"], player="p2")
    spawned = next(c for c in s.state.cards.values() if c.owner == "p2")
    bears = find(s.state, "Grizzly Bears", "p1")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "battlefield"})
    act(s, "p1", type="set_controller", card_ids=[bears.id], player="p2")
    act(s, "p1", type="life", player="p2", delta=-7)
    act(s, "p1", type="resource", player="p2", key="poison", delta=3)
    act(s, "p1", type="commander_damage", player="p2", commander=next(iter(s.state.players["p1"].commander_tax)), delta=5,
        affect_life=False)
    assert spawned.zone == "p2:battlefield" and s.state.cards[bears.id].controller == "p2"
    act(s, "p1", type="reset_dummy")
    p = s.state.players["p2"]
    assert p.life == 40 and p.resources["poison"] == 0 and p.commander_damage == {}
    assert spawned.id not in s.state.cards and s.state.zones["p2:battlefield"] == []
    assert s.state.cards[bears.id].zone == "p1:battlefield" and s.state.cards[bears.id].controller == "p1"
    s.undo("p1")  # undoable like any table action
    assert s.state.players["p2"].life == 33 and s.state.cards[bears.id].controller == "p2"
    replay_matches(s)


def attack_the_dummy(s: GameSession, cards) -> str:
    """A Grizzly Bears under the dummy's control (Spawn a card for it), Alice's Monastery Swiftspear; on to Alice's next combat."""
    act(s, "p1", type="spawn_card", card_id=cards.resolve("Grizzly Bears")["id"], player="p2")
    swift = to_hand(s, "Monastery Swiftspear")
    act(s, "p1", type="move", card_ids=[swift], to={"zone": "battlefield"})
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            if s.state.turn.number == 2:
                break
            act(s, "p1", type="declare_attackers")  # (haste: not this turn)
        else:
            act(s, "p1", type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_attackers" and d.player == "p1"
    return swift


def test_a_creature_for_the_dummy_never_blocks_and_attacks_go_through(cards):
    s = with_dummy(cards, rules=True)
    swift = attack_the_dummy(s, cards)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": swift, "target": "p2"}])
    assert any(a.actor == "p2" and a.type == "declare_blockers" for a in s.history.actions)  # its answer is a recorded action
    assert not any(c.is_blocking for c in s.state.cards.values())
    for _ in range(20):
        if s.state.turn.phase in ("end_combat", "main2"):
            break
        act(s, "p1", type="pass_priority")
    assert s.state.players["p2"].life == 39
    replay_matches(s)


# ---------------------------------------------------------------------------- undo, redo and a reload


def test_undo_takes_the_dummys_answers_back_with_the_action_they_answered(cards):
    s = with_dummy(cards, rules=True)
    swift = attack_the_dummy(s, cards)
    before = s.state.model_dump(mode="json")
    cursor = s.history.cursor
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": swift, "target": "p2"}])
    assert s.history.cursor > cursor + 1 and s.history.actions[-1].actor == "p2"  # Alice's attack, then the dummy's "no blocks"
    after = s.state.model_dump(mode="json")
    s.undo("p1")  # one undo: Alice's attack and the dummy's answer to it
    assert s.history.cursor == cursor and s.state.model_dump(mode="json") == before
    s.redo("p1")  # and one redo puts both back
    assert s.state.model_dump(mode="json") == after and not s.history.can_redo
    s.state.settings.undo_policy = "own"  # the dummy's answers count as part of the action they answered
    from app.game import undo_rights

    assert undo_rights.view_fields(s.state, s.history, host=False)["undo_by"] == "p1"  # (the client's Undo button stays on)
    s.undo("p1")
    assert s.history.cursor == cursor
    s.redo("p1")
    act(s, "p1", type="pass_priority")
    s.undo_to("p1", cursor + 1)  # "undo back to here" just after Alice's attack: the dummy's answer stays with it
    assert s.state.model_dump(mode="json") == after
    replay_matches(s)


def test_a_reload_replays_the_dummy(cards):
    s = with_dummy(cards, rules=True)
    pass_until(s, 1, "main1")
    bolt_the_dummy(s)
    pass_until(s, 2, "main1")
    loaded = GameState.model_validate(s.state.model_dump(mode="json"))
    again = GameSession(loaded, cards=cards, history=History.from_dict(s.history.to_dict()))
    assert again.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")
    pass_until(again, 3, "main1")  # and play goes on after loading
    assert again.state.players["p2"].life == 37


def test_opening_hands_with_a_dummy(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(20, "Mountain")])
    from app.game.mulligan import resolve_policy

    settings = GameSettings(starting_life=40, allow_test_objects=True, mulligan=resolve_policy("commander_london", None))
    state = new_game([PlayerSetup("Alice", cards=alice)], name="Deck test", format="sandbox", settings=settings, shuffle=False,
                     first_player=0)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="add_dummy")  # during the opening hands: nothing for it to decide
    assert s.state.pregame.seats["p2"].status == "kept"
    act(s, "p1", type="mulligan_keep")
    assert s.state.pregame.finished
    act(s, "p1", type="restart_game", draw=7)  # a restart: the decks reset; the dummy has nothing to draw
    assert s.state.zones["p2:hand"] == [] and len(s.state.zones["p1:hand"]) == 7
    replay_matches(s)


def test_the_dummy_keeps_its_opening_hand_by_itself(cards):
    """(A new pregame with the dummy in it, as a Karn restart deals: app/game/handlers/mulligan.begin.)"""
    alice = deck(cards, "Krenko, Mob Boss", [(20, "Mountain")])
    from app.game.mulligan import resolve_policy

    settings = GameSettings(starting_life=40, allow_test_objects=True, mulligan=resolve_policy("commander_london", None))
    state = new_game([PlayerSetup("Alice", cards=alice)], name="Deck test", format="sandbox", settings=settings, shuffle=False,
                     first_player=0)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="add_dummy")
    s.state.pregame.seats["p2"].status = "deciding"  # (as mulligan.begin deals it)
    act(s, "p1", type="mulligan_keep")
    assert s.state.pregame.finished
    assert s.history.actions[-1].actor == "p2" and s.history.actions[-1].type == "mulligan_keep"


def test_turning_the_rules_on_with_creatures_for_the_dummy(cards):
    """Sandbox starts manual: spawn the dummy's creatures, then turn the rules on. The reconcile questions are the turn player's."""
    s = with_dummy(cards)
    act(s, "p1", type="spawn_card", card_id=cards.resolve("Grizzly Bears")["id"], player="p2")
    turn_on(s, "full")
    assert s.state.rules.decision is None and s.state.rules.priority == "p1"
    pass_until(s, 2, "main1")
    assert s.state.turn.active_player == "p1" and s.state.zones["p2:battlefield"]
    replay_matches(s)


def test_the_dummys_answers_to_a_choice_are_the_most_passive_first():
    from app.game.dummy import answers
    from app.game.rules_state import Decision, DecisionOption

    opts = [DecisionOption(id=f"o{i}", label=f"Option {i}") for i in range(3)]
    may = Decision(id="d1", player="p2", kind="choose_one", prompt="You may", options=opts, min_choices=0, max_choices=1)
    assert [a["option_ids"] for a in answers(may)] == [[], ["o0"], ["o1"], ["o2"]]
    must = Decision(id="d2", player="p2", kind="choose_cards", prompt="Choose two", options=opts, min_choices=2, max_choices=2)
    assert [a["option_ids"] for a in answers(must)] == [["o0", "o1"]]
    blocks = Decision(id="d3", player="p2", kind="declare_blockers", prompt="Declare blockers", options=opts, min_choices=0)
    assert answers(blocks) == [{"type": "declare_blockers"}]
    order = Decision(id="d4", player="p2", kind="order", prompt="Order your triggers", options=opts, min_choices=3, max_choices=3)
    assert answers(order)[0]["option_ids"] == ["o0", "o1", "o2"]


def test_the_play_pages_sandbox_start_with_a_dummy(client):
    """The Play page's Sandbox start (one LAN seat, no lobby), then "Add a target dummy" as the host; then the rules turned on."""
    res = client.post("/api/games", json={"name": "Deck test", "format": "sandbox", "mode": "lan", "lobby": False, "seats": 1,
                                          "players": [{"name": "Alice"}], "first_player": 0})
    assert res.status_code == 201, res.text
    gid, token = res.json()["game"]["id"], res.json()["seat"]["token"]
    code = res.json()["game"]["code"]
    host = {"X-Seat-Token": token}
    res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "add_dummy"}}, headers=host)
    assert res.status_code == 200, res.text
    dummy = next(p for p in res.json()["players"] if p["id"] == "p2")
    assert dummy["dummy"] is True and dummy["name"] == "Target Dummy" and dummy["life"] == 40
    tile = client.get(f"/api/games/{gid}").json()
    assert [p["claimed"] for p in tile["players"]] == [True, True]  # (not a seat to join)
    assert client.post("/api/join", json={"code": code, "name": "Eve"}).status_code != 200
    res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "configure", "automation": "full"}}, headers=host)
    assert res.status_code == 200, res.text
    guest = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    refused = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "reset_dummy"}}, headers={"X-Seat-Token": guest})
    assert refused.status_code == 403
    refused = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "set_dummy", "blocks": "all"}}, headers={"X-Seat-Token": guest})
    assert refused.status_code == 403
    res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "set_dummy", "blocks": "chump"}}, headers=host)
    assert res.status_code == 200, res.text
    assert next(p for p in res.json()["players"] if p["id"] == "p2")["dummy_blocks"] == "chump"  # (in the table's view: the menu marks it)


def test_the_play_pages_sandbox_start_with_three_dummies(client):
    """The Play page's Sandbox start with three dummy seats set up: each added as the host, in order, before the rules start."""
    res = client.post("/api/games", json={"name": "Deck test", "format": "sandbox", "mode": "lan", "lobby": False, "seats": 1,
                                          "players": [{"name": "Alice"}], "first_player": 0, "starting_life": 30})
    assert res.status_code == 201, res.text
    gid, host = res.json()["game"]["id"], {"X-Seat-Token": res.json()["seat"]["token"]}
    for body in ({"name": "Wall", "blocks": "all"}, {"name": "Target Dummy 2", "life": 20}, {"blocks": "chump"}):
        res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "add_dummy", **body}}, headers=host)
        assert res.status_code == 200, res.text
    res = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "configure", "automation": "full"}}, headers=host)
    assert res.status_code == 200, res.text
    seats = [(p["name"], p["life"], p.get("dummy_blocks"), p.get("dummy")) for p in res.json()["players"]]
    assert seats[1:] == [("Wall", 30, "all", True), ("Target Dummy 2", 20, "never", True), ("Target Dummy 3", 30, "chump", True)]
    refused = client.post(f"/api/games/{gid}/actions", json={"action": {"type": "add_dummy"}}, headers=host)
    assert refused.status_code != 200


# ---------------------------------------------------------------------------- how it blocks (the host's setting)


def spawned(s: GameSession, cards, name: str, player: str | None = None) -> str:
    act(s, "p1", type="spawn_card", card_id=cards.resolve(name)["id"], **({"player": player} if player else {}))
    return next(c.id for c in reversed(list(s.state.cards.values())) if c.name == name and c.owner == (player or "p1"))


def combat_with(cards, mine: list[str], theirs: list[str], blocks: str = "never"):
    """Creatures spawned with the rules off (no summoning sickness to wait out, no enter triggers), the dummy set to ``blocks``, the
    rules turned on, and on to Alice's declare attackers."""
    s = with_dummy(cards)
    dummy_cards = [spawned(s, cards, n, "p2") for n in theirs]
    alice = [spawned(s, cards, n) for n in mine]
    if blocks != "never":
        act(s, "p1", type="set_dummy", blocks=blocks)
    turn_on(s, "full")
    engine_pays(s.state)
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            break
        act(s, "p1", type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "declare_attackers" and d.player == "p1"
    return s, alice, dummy_cards


def attack(s: GameSession, attackers: list[str]) -> None:
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": a, "target": "p2"} for a in attackers])


def blocks_of(s: GameSession) -> dict[str, str]:
    """The dummy's last declared blocks, blocker -> attacker (its recorded answer: with nothing else to do, the engine plays the combat
    out at once)."""
    declared = [a for a in s.history.actions[:s.history.cursor] if a.actor == "p2" and a.type == "declare_blockers"]
    return {b.blocker_id: b.attacker_id for b in declared[-1].blocks} if declared else {}


def test_the_dummy_chumps_the_biggest_attacker_with_its_smallest_creature(cards):
    s, (swift, bears), (elves, _big) = combat_with(cards, ["Monastery Swiftspear", "Grizzly Bears"],
                                                   ["Llanowar Elves", "Grizzly Bears"], "chump")
    assert s.state.players["p2"].dummy_blocks == "chump"
    attack(s, [swift, bears])
    assert blocks_of(s) == {elves: bears}
    assert s.state.cards[elves].zone == "p2:graveyard" and s.state.players["p2"].life == 39  # (the Swiftspear got through)
    replay_matches(s)


def test_a_chump_only_blocks_what_it_may_block(cards):
    """The biggest attacker flies: the dummy's Bears can't block it (combat.block_problem), so it chumps the next biggest."""
    s, (swift, flyer), (bears,) = combat_with(cards, ["Monastery Swiftspear", "Hollow Marauder"], ["Grizzly Bears"], "chump")
    attack(s, [swift, flyer])
    assert blocks_of(s) == {bears: swift}
    assert s.state.players["p2"].life == 36  # (the flyer got through)
    replay_matches(s)


def test_the_dummy_blocks_with_everything_it_can(cards):
    s, (swift, bears, flyer), (elves, big) = combat_with(cards, ["Monastery Swiftspear", "Grizzly Bears", "Hollow Marauder"],
                                                         ["Llanowar Elves", "Grizzly Bears"], "all")
    attack(s, [swift, bears, flyer])
    assert blocks_of(s) == {elves: bears, big: bears}  # each on the biggest attacker it can block (not the flyer)
    for _ in range(30):  # and combat goes on (Alice divides her Bears' damage: her choice, not the dummy's)
        if s.state.turn.phase in ("end_combat", "main2"):
            break
        d = s.state.rules.decision
        if d is not None and d.kind == "divide":
            assert d.player == "p1"
            act(s, "p1", type="choose", decision_id=d.id, amounts=[2] + [0] * (len(d.options) - 1))
        elif d is not None and d.player == "p1" and d.kind == "order":
            act(s, "p1", type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])
        else:
            act(s, "p1", type="pass_priority")
    assert s.state.players["p2"].life == 40 - 1 - 4  # the Swiftspear and the flyer weren't blocked
    replay_matches(s)


def test_the_dummy_never_blocks_by_default(cards):
    s, (swift, bears), (_elves,) = combat_with(cards, ["Monastery Swiftspear", "Grizzly Bears"], ["Llanowar Elves"])
    assert s.state.players["p2"].dummy_blocks == "never"
    attack(s, [swift, bears])
    assert blocks_of(s) == {} and any(a.actor == "p2" and a.type == "declare_blockers" for a in s.history.actions)
    assert s.state.players["p2"].life == 37
    replay_matches(s)


def test_how_it_blocks_is_set_mid_game_and_undone_with_the_rest(cards):
    s, (swift, bears), (elves,) = combat_with(cards, ["Monastery Swiftspear", "Grizzly Bears"], ["Llanowar Elves"])
    act(s, "p1", type="set_dummy", blocks="all")  # (mid-game, from Solo tools)
    assert s.state.players["p2"].dummy_blocks == "all"
    with pytest.raises(ActionError, match="already"):
        act(s, "p1", type="set_dummy", blocks="all")
    before = s.state.model_dump(mode="json")
    attack(s, [swift, bears])
    assert blocks_of(s) == {elves: bears}
    after = s.state.model_dump(mode="json")
    s.undo("p1")  # the attack and the dummy's blocks go back together
    assert s.state.model_dump(mode="json") == before
    s.redo("p1")
    assert s.state.model_dump(mode="json") == after
    replay_matches(s)
    loaded = GameSession(GameState.model_validate(s.state.model_dump(mode="json")), cards=cards,
                         history=History.from_dict(s.history.to_dict()))
    assert loaded.history.rebuild().model_dump(mode="json") == after  # (a reload replays the setting and the blocks)
    s.undo("p1")
    s.undo("p1")  # the setting itself is a recorded action
    assert s.state.players["p2"].dummy_blocks == "never"
    attack(s, [swift, bears])
    assert blocks_of(s) == {} and s.state.players["p2"].life == 37
    replay_matches(s)


def test_adding_the_dummy_with_a_block_setting(cards):
    s = sandbox(cards)
    act(s, "p1", type="add_dummy", blocks="chump")
    assert s.state.players["p2"].dummy_blocks == "chump"
    with pytest.raises(ActionError, match="no target dummy"):
        act(sandbox(cards), "p1", type="set_dummy", blocks="all")
    replay_matches(s)


def test_with_automation_off_the_setting_changes_nothing(cards):
    s = with_dummy(cards)
    act(s, "p1", type="spawn_card", card_id=cards.resolve("Grizzly Bears")["id"], player="p2")
    act(s, "p1", type="set_dummy", blocks="all")
    act(s, "p1", type="next_turn", force=True)
    assert not any(a.actor == "p2" for a in s.history.actions)  # (its cards are moved by hand)


# ---------------------------------------------------------------------------- the choices it answers


def test_the_dummy_divides_as_evenly_as_it_may():
    from app.game.dummy import answers
    from app.game.rules_state import Decision, DecisionOption

    def divide(n: int, **resume) -> list:
        opts = [DecisionOption(id=f"t{i}", label=f"Target {i}") for i in range(n)]
        d = Decision(id="d", player="p2", kind="divide", prompt="Divide", options=opts, min_choices=n, max_choices=n,
                     resume={"step": "x", **resume})
        return [a["amounts"] for a in answers(d)]

    assert divide(3, total=5) == [[3, 1, 1]]  # (at least 1 each, the rest on the first)
    assert divide(2, total=4) == [[2, 2]]
    assert divide(3, total=7, least=0) == [[3, 2, 2]]
    assert divide(3, total=5, least=0, lethal=[2, 2], free=2) == [[3, 2, 0]]  # combat damage: none past the blockers (702.19b)
    assert divide(3, total=2) == []  # (can't: left to the table)


def test_the_dummy_answers_a_division_the_engine_accepts(cards):
    """A divide decision put to the dummy (Wildhunt's damage among Wolves: app/rules/wave110c_misc.py) is answered by the server."""
    from app.game.rules_state import Decision, DecisionOption

    s = with_dummy(cards, rules=True)
    pass_until(s, 1, "main1")
    wolves = [spawned(s, cards, "Grizzly Bears", "p2"), spawned(s, cards, "Llanowar Elves", "p2")]
    s.state.rules.decision = Decision(
        id="dv", player="p2", kind="divide", prompt="Divide 3 damage among the Wolves",
        options=[DecisionOption(id=w, label=s.state.cards[w].name or "", card_id=w) for w in wolves], min_choices=2, max_choices=2,
        resume={"step": "wildhunt110c", "ctx": {"controller": "p1", "effects": [], "next": 0, "stack_id": "gone"}, "total": 3, "least": 0,
                "target": "gone", "wolves": wolves})
    s._answer_for_dummy()
    answered = s.history.actions[-1]
    assert answered.actor == "p2" and answered.type == "choose" and answered.amounts == [2, 1]
    assert s.state.rules.decision is None or s.state.rules.decision.id != "dv"


def test_the_dummy_names_a_card_the_engine_accepts(cards):
    """A "choose a creature card name" put to the dummy (Paper Tiger's: app/rules/wave110a_paper.py), then the creature type it asks."""
    from app.game.dummy import answers
    from app.game.rules_state import Decision, DecisionOption
    from app.rules import card_names

    s = with_dummy(cards, rules=True)
    pass_until(s, 1, "main1")
    bears = spawned(s, cards, "Grizzly Bears", "p2")
    s.state.rules.decision = Decision(id="dn", player="p2", kind="choose_one", prompt="Choose a creature card name",
                                      options=[card_names.option("creature card name")], resume={"step": "paper_name110a", "card": bears})
    s._answer_for_dummy()
    named = next(a for a in s.history.actions if a.type == "choose" and a.actor == "p2")
    assert named.name == "Grizzly Bears"
    assert any("Grizzly Bears" in str(v) for v in s.state.cards[bears].choices.values())
    assert s.state.rules.decision is None  # (and the creature type it asks next: the first offered)

    def names(what: str, info=cards, seen=()) -> list[str]:
        opts = [card_names.option(what), *(DecisionOption(id=f"seen:{n}", label=n, group="seen") for n in seen)]
        d = Decision(id="d", player="p2", kind="choose_one", prompt="Name", options=opts)
        return [a["name"] for a in answers(d, info=info)]

    assert names("nonland card name")[0] == "Sol Ring"
    assert names("land card name") == ["Command Tower", "Mountain"]
    assert names("nonbasic land card name") == ["Command Tower"]
    assert names("nonartifact, nonland card name")[0] == "Grizzly Bears"
    assert names("nonland card name", seen=["Mountain", "Lightning Bolt"])[0] == "Lightning Bolt"  # a card it was shown, if it fits
    assert names("card name", info=None)[0] == "Sol Ring"  # (no card database to check against: the engine judges)


def test_the_dummy_types_numbers_and_answers_each_question_of_a_reconcile():
    from app.game.dummy import answers
    from app.game.rules_state import Decision, DecisionOption

    number = Decision(id="d", player="p2", kind="choose_one", prompt="Choose a number",
                      options=[DecisionOption(id="__number__", label="Bid: a number ≥ 1")])
    assert [a["name"] for a in answers(number)] == ["1"]
    count = Decision(id="d", player="p2", kind="choose_one", prompt="Count", options=[DecisionOption(id="__number__", label="Count: 0–1000")])
    assert [a["name"] for a in answers(count)] == ["0"]
    splice = Decision(id="d", player="p2", kind="choose_one", prompt="Splice",
                      options=[DecisionOption(id="__name__", label="Type", group="historical splice names")])
    assert [a["name"] for a in answers(splice)] == ["no cards"]
    history = Decision(id="d", player="p2", kind="choose_one", prompt="Names",
                       options=[DecisionOption(id="__name__", label="Type", group="historical spell names")])
    assert answers(history) == []  # (only the table knows: the session's "can't answer" note)
    opts = [DecisionOption(id=f"{g}{i}", label=f"{g}{i}", group=g) for g in "ab" for i in range(2)]
    reconcile = Decision(id="d", player="p2", kind="reconcile", prompt="Reconcile", options=opts, min_choices=2, max_choices=2)
    assert answers(reconcile)[0]["option_ids"] == ["a0", "b0"]


# ---------------------------------------------------------------------------- the test-table ending (Take it back / Start over)


def lose_as_alice(s: GameSession) -> int:
    """Alice at 0 life, then the next state-based check: she loses and the dummy wins. Returns the history position before the pass."""
    act(s, "p1", type="set_life", player="p1", value=0)
    before = s.history.cursor
    act(s, "p1", type="pass_priority")
    assert "p1" in s.state.rules.lost
    return before


def test_take_it_back_undoes_the_action_that_ended_the_test(cards):
    from app.game.handlers.dummy import before_the_end, test_over

    s = with_dummy(cards, rules=True)
    pass_until(s, 1, "main1")
    assert before_the_end(s.state, s.history, "p1") is None  # (nothing ended)
    before = lose_as_alice(s)
    assert test_over(s.state, "p1") and s.state.rules.winner == "p2"
    position = before_the_end(s.state, s.history, "p1")
    assert position == before
    s.undo_to("p1", position, host=True)
    r = s.state.rules
    assert r.winner is None and r.lost == {} and s.state.players["p1"].life == 0  # (just before the pass that lost it)
    replay_matches(s)


def test_start_over_is_a_new_game_with_the_same_seats(cards):
    s = sandbox(cards)
    act(s, "p1", type="add_dummy")
    act(s, "p1", type="add_dummy", life=20)
    turn_on(s, "full")
    engine_pays(s.state)
    pass_until(s, 1, "main1")
    act(s, "p1", type="set_life", player="p3", value=4)
    lose_as_alice(s)
    library = len([c for c in s.state.cards.values() if c.owner == "p1"])
    act(s, "p1", type="restart_game", draw=7, fresh=True)
    st, r = s.state, s.state.rules
    assert r.winner is None and r.lost == {} and r.conceded == [] and st.eliminations == []
    assert (st.turn.number, st.turn.active_player) == (1, "p1")
    assert [st.players[p].life for p in ("p1", "p2", "p3")] == [40, 40, 20]  # (the second dummy's own starting life)
    assert len(st.zones["p1:library"]) + len(st.zones["p1:hand"]) + len(st.zones["p1:command"]) == library
    assert st.players["p2"].dummy and st.players["p3"].dummy
    replay_matches(s)
    loaded = GameState.model_validate(st.model_dump(mode="json"))
    again = GameSession(loaded, cards=cards, history=History.from_dict(s.history.to_dict()))
    assert again.history.rebuild().model_dump(mode="json") == st.model_dump(mode="json")
    pass_until(s, 1, "main1")  # (and play goes on: the dummies answer for themselves)
    replay_matches(s)


def test_the_test_ending_over_the_api(client):
    """The Sandbox table's ending panel: Take it back (the endpoint), then Start over (restart_game fresh); never a pod result."""
    res = client.post("/api/games", json={"name": "Deck test", "format": "sandbox", "mode": "lan", "lobby": False, "seats": 1,
                                          "players": [{"name": "Alice"}], "first_player": 0})
    gid, code = res.json()["game"]["id"], res.json()["game"]["code"]
    host = {"X-Seat-Token": res.json()["seat"]["token"]}

    def send(action: dict) -> dict:
        res = client.post(f"/api/games/{gid}/actions", json={"action": action}, headers=host)
        assert res.status_code == 200, (action, res.text)
        return res.json()

    assert client.post(f"/api/games/{gid}/test/take-back", json={}, headers=host).status_code == 409  # (no dummy yet)
    send({"type": "add_dummy"})
    view = send({"type": "configure", "automation": "full"})
    for _ in range(30):  # opening hands, then on to Alice's main phase
        if view.get("pregame") and not view["pregame"].get("finished"):
            view = send({"type": "mulligan_keep"})
            continue
        break
    send({"type": "set_life", "player": "p1", "value": 0})
    view = send({"type": "pass_priority"})
    assert view["rules"]["winner"] == "p2" and "p1" in view["rules"]["lost"]
    assert view["game"]["night"]["proposal"] is None and view["game"]["night"]["result"] is None  # (no pod result)
    guest = client.post("/api/join", json={"code": code, "spectate": True}).json()["token"]
    assert client.post(f"/api/games/{gid}/test/take-back", json={}, headers={"X-Seat-Token": guest}).status_code == 403
    res = client.post(f"/api/games/{gid}/test/take-back", json={}, headers=host)
    assert res.status_code == 200, res.text
    assert res.json()["rules"]["winner"] is None and res.json()["rules"]["lost"] == {}
    assert client.post(f"/api/games/{gid}/test/take-back", json={}, headers=host).status_code == 409  # (nothing ended now)
    view = send({"type": "pass_priority"})
    assert view["rules"]["winner"] == "p2"
    view = send({"type": "restart_game", "draw": 7, "fresh": True})
    assert view["rules"]["winner"] is None and view["rules"]["lost"] == {} and view["turn"]["number"] == 1
    assert [p["life"] for p in view["players"]] == [40, 40]
