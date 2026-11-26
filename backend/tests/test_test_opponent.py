"""-- test opponent -- Sandbox's opponent that plays a deck (app/game/bot.py, app/game/handlers/bot_seat.py): it keeps or mulligans,
plays lands, casts creatures and spells, attacks, blocks sensibly and can win; it acts only through recorded intents (so a whole game
replays the same and survives a save and a load), sees only what its own seat is shown, and never loops."""

from __future__ import annotations

from typing import Any

import pytest

from app.game import actions as A
from app.game import bot
from app.game.control import decider_of
from app.game.errors import ActionError
from app.game.factory import PlayerSetup, new_game
from app.game.history import History
from app.game.mulligan import resolve_policy
from app.game.session import GameSession
from app.game.state import GameSettings, GameState
from tests.game_helpers import act, deck, turn_on

# (in library order, top first: no shuffle) an opening hand of 3 lands, Elves, two Bears and a Bolt, then a land a turn and more creatures
GRUUL = [(1, "Forest"), (1, "Llanowar Elves"), (1, "Forest"), (1, "Grizzly Bears"), (1, "Mountain"), (1, "Grizzly Bears"),
         (1, "Lightning Bolt"), *[(1, n) for _ in range(6) for n in ("Forest", "Grizzly Bears", "Mountain", "Llanowar Elves")],
         (1, "Giant Growth"), (6, "Forest")]


def table(cards, *, life: int = 20, human: list[tuple[int, str]] | None = None, opponent: list[tuple[int, str]] | None = None,
          mulligan: str | None = None) -> GameSession:
    """Alice (the player testing) and an opponent the server plays for, both decks in their order (no shuffle), rules at Full."""
    alice = deck(cards, "Krenko, Mob Boss", human or [(30, "Mountain")])
    gruul = deck(cards, "Krenko, Mob Boss", opponent or GRUUL)
    settings = GameSettings(starting_life=life, allow_test_objects=True,
                            mulligan=resolve_policy(mulligan) if mulligan else None)
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Opponent", cards=gruul)], name="Deck test", format="sandbox",
                     settings=settings, shuffle=False, first_player=0)
    state.players["p2"].bot = "simple"
    if mulligan is None:
        from app.game.handlers.zones import draw_cards

        for pid in ("p1", "p2"):
            draw_cards(state, pid, 7)
    s = GameSession(state, cards=cards)
    if mulligan is None:
        turn_on(s)
    return s


def human_move(s: GameSession, blocks: list[dict[str, str]] | None = None) -> bool:
    """Alice passes and declares nothing (unless told how to block). False when she has nothing to do."""
    st = s.state
    if st.pregame is not None and not st.pregame.finished:
        seat = st.pregame.seats.get("p1")
        if seat is not None and seat.status == "deciding":
            act(s, "p1", type="mulligan_keep")
            return True
        return False
    r = st.rules
    if r is None or r.winner is not None or r.draw_reason is not None:
        return False
    d = r.decision
    if d is not None and decider_of(st, d) == "p1":
        if d.kind == "declare_blockers":
            act(s, "p1", type="declare_blockers", blocks=blocks or [])
        elif d.kind == "declare_attackers":
            act(s, "p1", type="declare_attackers")
        else:
            from app.game import dummy

            for payload in dummy.answers(d, state=st, info=s.cards):
                try:
                    act(s, "p1", **payload)
                    return True
                except ActionError:
                    continue
            raise AssertionError(f"Alice can't answer {d.kind}: {d.prompt}")
        return True
    if r.priority == "p1":
        act(s, "p1", type="pass_priority")
        return True
    return False


def play(s: GameSession, *, until_turn: int, steps: int = 3000) -> None:
    for _ in range(steps):
        r = s.state.rules
        if r is not None and (r.winner is not None or r.draw_reason is not None):
            return
        if s.state.turn.number > until_turn:
            return
        if bot.step(s) is not None:
            continue
        if not human_move(s):
            raise AssertionError(f"nobody can move: turn {s.state.turn.number} {s.state.turn.phase}, priority {r and r.priority}")
    raise AssertionError("the game never got there")


def on_battlefield(s: GameSession, pid: str) -> list[str]:
    return [s.state.cards[c].name for c in s.state.zones[f"{pid}:battlefield"]]


def replay_matches(s: GameSession) -> None:
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")
    again = History.from_dict(s.history.to_dict())
    assert again.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


# ---------------------------------------------------------------------------- playing


def test_it_plays_lands_casts_creatures_and_attacks(cards):
    s = table(cards)
    play(s, until_turn=4)
    mine = on_battlefield(s, "p2")
    assert mine.count("Forest") + mine.count("Mountain") == 2  # (one land on each of its turns)
    assert {"Grizzly Bears", "Llanowar Elves"} & set(mine)
    texts = [" ".join(part.t or part.name or "" for part in e.parts) for e in s.state.log]
    assert any(t.startswith("Opponent") and "Grizzly Bears" in t for t in texts), texts[-30:]
    play(s, until_turn=8)
    assert s.state.players["p1"].life < 20  # (Alice has no creatures: it attacks)
    assert all(a.actor in ("p1", "p2") for a in s.history.actions)
    replay_matches(s)


def test_it_kills_the_player_over_turns_and_the_game_replays_and_survives_a_save(cards):
    s = table(cards, life=8)
    play(s, until_turn=30)
    r = s.state.rules
    assert r.winner == "p2" and "p1" in r.lost
    replay_matches(s)
    loaded = GameState.model_validate(s.state.model_dump(mode="json"))  # save / load
    again = GameSession(loaded, cards=cards, history=History.from_dict(s.history.to_dict()))
    assert again.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")
    assert again.state.players["p2"].bot == "simple"


def put(s: GameSession, pid: str, name: str) -> str:
    """A card of ``pid``'s from their library or hand onto their battlefield (by hand, before the rules start)."""
    card = next(c for c in s.state.cards.values() if c.owner == pid and c.name == name and c.zone in (f"{pid}:library", f"{pid}:hand"))
    act(s, "p1", type="move", card_ids=[card.id], to={"zone": "battlefield", "player": pid})
    return card.id


def attack_with(s: GameSession, *ids: str) -> None:
    """Alice passes to her declare-attackers step and attacks the opponent with ``ids``."""
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, "p1", type="declare_attackers", attackers=[{"card_id": cid, "target": "p2"} for cid in ids])
            return
        act(s, "p1", type="pass_priority")
    raise AssertionError("never got to declare attackers")


def until_it_decides(s: GameSession, kind: str) -> None:
    """Play on (the opponent's other actions included) until the opponent is asked ``kind``."""
    for _ in range(300):
        d = s.state.rules.decision
        if d is not None and d.kind == kind and decider_of(s.state, d) == "p2":
            return
        if bot.step(s) is None and not human_move(s):
            break
    raise AssertionError(f"it was never asked {kind}")


def blocks_declared(s: GameSession) -> list[tuple[str, str]]:
    a = next(a for a in reversed(s.history.actions) if a.type == "declare_blockers" and a.actor == "p2")
    return [(s.state.cards[b.blocker_id].name, s.state.cards[b.attacker_id].name) for b in a.blocks]


def board(cards, *, life: int = 20, mine: tuple[str, ...] = (), theirs: tuple[str, ...] = (),
          top: list[tuple[int, str]] | None = None) -> tuple[GameSession, dict[str, str]]:
    """Alice's creatures ``mine`` and the opponent's ``theirs`` already on the table when the rules start (not summoning sick)."""
    human = [(1, n) for n in mine] + [(30, "Mountain")]
    opponent = [(1, n) for n in theirs] + (top or [(1, "Monastery Swiftspear")]) + [(30, "Forest")]
    alice = deck(cards, "Krenko, Mob Boss", human)
    gruul = deck(cards, "Krenko, Mob Boss", opponent)
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Opponent", cards=gruul)], name="Deck test", format="sandbox",
                     settings=GameSettings(starting_life=life, allow_test_objects=True), shuffle=False, first_player=0)
    state.players["p2"].bot = "simple"
    from app.game.handlers.zones import draw_cards

    for pid in ("p1", "p2"):
        draw_cards(state, pid, 7)
    s = GameSession(state, cards=cards)
    ids = {f"p1:{n}": put(s, "p1", n) for n in mine} | {f"p2:{n}": put(s, "p2", n) for n in theirs}
    turn_on(s)
    return s, ids


def test_it_blocks_when_the_block_kills_the_attacker_and_survives(cards):
    s, ids = board(cards, mine=("Llanowar Elves",), theirs=("Grizzly Bears",))
    attack_with(s, ids["p1:Llanowar Elves"])
    until_it_decides(s, "declare_blockers")
    assert bot.step(s) == "declare_blockers"
    assert blocks_declared(s) == [("Grizzly Bears", "Llanowar Elves")]


def test_it_doesnt_trade_evenly_or_chump_while_the_damage_isnt_lethal(cards):
    s, ids = board(cards, mine=("Grizzly Bears",), theirs=("Grizzly Bears", "Llanowar Elves"))
    attack_with(s, ids["p1:Grizzly Bears"])
    until_it_decides(s, "declare_blockers")
    assert bot.step(s) == "declare_blockers"
    assert blocks_declared(s) == []


def test_it_chump_blocks_when_the_damage_coming_is_lethal(cards):
    s, ids = board(cards, life=2, mine=("Grizzly Bears",), theirs=("Llanowar Elves",))
    attack_with(s, ids["p1:Grizzly Bears"])
    until_it_decides(s, "declare_blockers")
    assert bot.step(s) == "declare_blockers"
    assert blocks_declared(s) == [("Llanowar Elves", "Grizzly Bears")]


def their_attack(s: GameSession) -> list[str]:
    """Play on to the opponent's declare-attackers step (turn 2) and let it declare: the names it attacks with."""
    until_it_decides(s, "declare_attackers")
    assert bot.step(s) == "declare_attackers"
    declared = next(a for a in reversed(s.history.actions) if a.type == "declare_attackers" and a.actor == "p2")
    return sorted(s.state.cards[x.card_id].name for x in declared.attackers)


def test_it_attacks_only_where_no_untapped_blocker_kills_the_attacker(cards):
    """Its Bears and Elves stay home in front of Alice's untapped 2/2 (they would die to it); its 3/3 Krenko would not, so it attacks."""
    s, _ = board(cards, mine=("Grizzly Bears",), theirs=("Grizzly Bears", "Llanowar Elves", "Krenko, Mob Boss"))
    assert their_attack(s) == ["Krenko, Mob Boss"]


def test_it_attacks_with_everything_when_alice_has_no_blockers(cards):
    s, _ = board(cards, theirs=("Grizzly Bears", "Llanowar Elves"))
    assert their_attack(s) == ["Grizzly Bears", "Llanowar Elves"]
    replay_matches(s)


def test_burn_goes_at_the_player_when_it_is_lethal(cards):
    s = table(cards, life=3)
    play(s, until_turn=2)
    while s.state.rules.winner is None and s.state.turn.number == 2:
        if bot.step(s) is None and not human_move(s):
            break
    cast = next(a for a in s.history.actions if a.type == "cast_spell" and a.actor == "p2")
    assert s.state.cards[cast.card_id].name == "Lightning Bolt"
    assert s.state.rules.winner == "p2" and "p1" in s.state.rules.lost
    replay_matches(s)


def test_removal_goes_at_the_biggest_creature_it_kills(cards):
    s, ids = board(cards, mine=("Grizzly Bears", "Llanowar Elves"), top=[(1, "Lightning Bolt"), (1, "Mountain")])
    while s.state.turn.number <= 2 and s.state.turn.phase != "begin_combat" or s.state.turn.number < 2:
        if bot.step(s) is None and not human_move(s):
            break
    assert s.state.cards[ids["p1:Grizzly Bears"]].zone == "p1:graveyard"  # (Bolt at the Bears, not the Elves or the player at 20)
    assert s.state.cards[ids["p1:Llanowar Elves"]].zone == "p1:battlefield"
    assert s.state.players["p1"].life == 20


# ---------------------------------------------------------------------------- opening hand


def test_it_mulligans_a_hand_without_lands_once_then_keeps(cards):
    gruul = [(7, "Grizzly Bears"), *[(1, n) for _ in range(10) for n in ("Forest", "Grizzly Bears", "Forest")]]
    s = table(cards, opponent=gruul, mulligan="london")
    assert s.state.pregame is not None and not s.state.pregame.finished
    for _ in range(10):
        if bot.step(s) is None and not human_move(s):
            break
    seat = s.state.pregame.seats["p2"]
    assert seat.mulligans == 1 and seat.status == "kept" and seat.kept == 6
    assert len(s.state.zones["p2:hand"]) == 6
    assert any(a.type == "mulligan_bottom" and a.actor == "p2" for a in s.history.actions)
    replay_matches(s)


# ---------------------------------------------------------------------------- what it sees


def test_it_decides_from_its_own_seats_view_only(cards, monkeypatch):
    """Hidden information (400.2): every decision is made from the view the opponent's own seat is shown; Alice's hand reaches it only
    as anonymous placeholders (never her cards' ids or names)."""
    import json

    seen: list[dict[str, Any]] = []
    decide = bot.decide

    def spy(view: dict[str, Any], info: Any, memory: Any = None) -> list[dict[str, Any]]:
        seen.append(view)
        return decide(view, info, memory)

    monkeypatch.setattr(bot, "decide", spy)
    s = table(cards, human=[(1, "Sol Ring"), (1, "Monastery Swiftspear"), (28, "Mountain")])
    hand = list(s.state.zones["p1:hand"])
    secret = [s.state.cards[c].name for c in hand if s.state.cards[c].name != "Mountain"]
    assert secret == ["Sol Ring", "Monastery Swiftspear"]
    play(s, until_turn=3)
    assert seen
    for view in seen:
        assert view["viewer"] == "p2"
        assert all(view["cards"][cid].get("hidden") for cid in view["zones"]["p1:hand"])
        dumped = json.dumps(view)
        for cid in hand:
            if s.state.cards[cid].zone == "p1:hand":
                assert cid not in dumped
        assert "Sol Ring" not in dumped and "Monastery Swiftspear" not in dumped


# ---------------------------------------------------------------------------- seating, undo, endings


def test_add_an_opponent_seats_it_with_its_deck(cards):
    alice = deck(cards, "Krenko, Mob Boss", [(30, "Mountain")])
    state = new_game([PlayerSetup("Alice", cards=alice)], name="Deck test", format="sandbox",
                     settings=GameSettings(starting_life=40, allow_test_objects=True, mulligan=resolve_policy("commander_london")),
                     shuffle=False, first_player=0)
    s = GameSession(state, cards=cards)
    gruul = [A.LoadDeckCard(section=c.section, quantity=c.quantity, name=c.name, printing_id=c.printing_id)
             for c in deck(cards, "Krenko, Mob Boss", GRUUL)]
    s.perform("p1", A.AddBot(deck_name="Gruul", cards=gruul), trusted=True)
    st = s.state
    p = st.players["p2"]
    assert p.bot == "simple" and p.name == "Opponent" and p.life == 40 and not p.dummy
    assert len(st.zones["p2:hand"]) == 7 and len(st.zones["p2:command"]) == 1
    assert len(st.zones["p2:library"]) == sum(n for n, _ in GRUUL) - 7
    assert st.pregame.seats["p2"].status == "deciding"
    with pytest.raises(ActionError, match="plays on its own"):
        act(s, "p2", type="life", player="p2", delta=-1)
    with pytest.raises(ActionError):  # (a client can't send one: the server builds it from a saved deck)
        act(s, "p1", type="add_bot", deck_name="x", cards=[c.model_dump() for c in gruul])
    act(s, "p1", type="add_dummy")
    act(s, "p1", type="add_dummy")
    with pytest.raises(ActionError, match="dummies and opponents"):
        act(s, "p1", type="add_dummy")
    act(s, "p1", type="mulligan_keep")
    bot.run(s)
    assert s.state.pregame.finished
    replay_matches(s)


def test_take_it_back_goes_back_to_before_the_players_last_action_and_it_doesnt_replay_at_once(cards):
    from app.game.handlers.dummy import before_the_end

    s = table(cards, life=3)
    play(s, until_turn=2)
    while s.state.rules.winner is None and s.state.turn.number == 2:
        if bot.step(s) is None and not human_move(s):
            break
    assert s.state.rules.winner == "p2"
    position = before_the_end(s.state, s.history, "p1")
    assert position is not None and s.history.actions[position].actor == "p1"
    s.undo_to("p1", position, host=True)  # (the API's Take it back: the host's seat)
    assert s.state.rules.winner is None and "p1" not in s.state.rules.lost
    assert bot.pending(s.state) is None  # (Alice's move again: the opponent waits for it)
    before = s.history.cursor
    s.undo("p1")  # one undo takes Alice's last action back with the opponent's actions after it
    assert s.history.cursor < before and s.history.actions[s.history.cursor].actor == "p1"


def test_start_over_reshuffles_the_opponents_deck_too(cards):
    s = table(cards, life=3)
    play(s, until_turn=2)
    while s.state.rules.winner is None and s.state.turn.number == 2:
        if bot.step(s) is None and not human_move(s):
            break
    assert s.state.rules.winner == "p2"
    act(s, "p1", type="restart_game", draw=7, fresh=True)
    st = s.state
    assert st.rules.winner is None and st.turn.active_player == "p1" and st.turn.number == 1
    assert len(st.zones["p2:hand"]) == 7 and not st.zones["p2:battlefield"] and st.players["p2"].bot == "simple"
    assert st.players["p1"].life == 3 and st.players["p2"].life == 3
    replay_matches(s)


def test_only_dummies_and_opponents_left_ends_the_test(cards):
    from app.multiplayer.night import rules_ending
    from app.rules.dummy_ending import OPPONENTS_WIN

    s = table(cards)
    act(s, "p1", type="add_dummy")
    act(s, "p1", type="concede")
    r = s.state.rules
    assert r.draw_reason == OPPONENTS_WIN
    ending = rules_ending(s.state)
    assert ending is not None and sorted(ending[2]) == ["p2", "p3"]
    assert bot.pending(s.state) is None


# ---------------------------------------------------------------------------- never stuck


def test_it_only_passes_once_a_window_is_used_up(cards):
    s = table(cards)
    for _ in range(100):
        if bot.pending(s.state) == "p2" and s.state.rules.decision is None:
            break
        if bot.step(s) is None:
            human_move(s)
    view = bot.observe(s.state, "p2", cards)
    w = (view["turn"]["number"], view["turn"]["phase"], view["turn"]["active_player"], len(view["stack"]))
    assert bot.decide(view, cards, {"window": w, "count": bot.MAX_PER_WINDOW, "tried": []}) == [{"type": "pass_priority"}]


def test_a_move_the_engine_refuses_never_loops_and_a_broken_policy_passes(cards, monkeypatch):
    s = table(cards)
    play(s, until_turn=2)
    while bot.pending(s.state) is None:
        human_move(s)
    before = s.history.cursor
    monkeypatch.setattr(bot, "decide", lambda view, info, memory=None: [{"type": "cast_spell", "card_id": "nope"}])
    assert bot.step(s) is None and bot.run(s) == 0  # (nothing accepted: it stops, the table goes on by hand)
    assert s.history.cursor == before

    def broken(view, info, memory=None):
        raise RuntimeError("a policy bug")

    monkeypatch.setattr(bot, "decide", broken)
    assert bot.step(s) in ("pass_priority", "choose", "declare_attackers", "declare_blockers")  # (its safe answer)
    assert s.history.cursor == before + 1


def test_a_table_of_only_opponents_is_over_at_once(cards):
    """Two seats the server plays for and nobody else: nothing to test, the game ends (it never plays on by itself)."""
    s = table(cards)
    s.state.players["p1"].bot = "simple"
    s.history = History(s.state)
    s.perform_bot("p1", {"type": "pass_priority"})
    assert s.state.rules.draw_reason is not None and bot.pending(s.state) is None
