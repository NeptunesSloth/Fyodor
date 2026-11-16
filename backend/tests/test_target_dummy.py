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
    with pytest.raises(ActionError, match="already has a target dummy"):
        act(s, "p1", type="add_dummy")
    with pytest.raises(ActionError, match="acts on its own"):  # (a hot-seat table can act as any seat: not as the dummy)
        act(s, "p2", type="life", player="p2", delta=-1)
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
