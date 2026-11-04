"""Solo testing with the rules on: a table seated for one player (a LAN night with only the host, a Sandbox table) is not a
won game. Its turns go on: the steps advance on each pass, the draw step draws, lands are played through the rules. A game of
several players where one is left is still over (104.2a)."""

from __future__ import annotations

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameState
from app.storage.save_format import SAVE_VERSION, decode, encode
from app.storage.saves import load_payload
from tests.game_helpers import act, deck, enable, find


def solo(cards, *, format: str = "commander") -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", [(12, "Mountain"), (1, "Sol Ring"), (1, "Lightning Bolt")])
    state = new_game([PlayerSetup("Alice", cards=alice)], name="Solo", format=format, shuffle=False, first_player=0)
    enable(state, "full")
    return GameSession(state, cards=cards)


def replay_matches(s: GameSession) -> None:
    assert s.history.rebuild().model_dump(mode="json") == s.state.model_dump(mode="json")


def pass_until(s: GameSession, turn: int, phase: str) -> None:
    for _ in range(40):
        if (s.state.turn.number, s.state.turn.phase) == (turn, phase):
            return
        act(s, "p1", type="pass_priority")
    raise AssertionError(f"stuck at turn {s.state.turn.number}, {s.state.turn.phase}")


def test_a_one_seat_rules_table_plays_its_turns(cards):
    s = solo(cards)
    assert s.state.turn.phase == "untap" and s.state.rules.priority == "p1"
    pass_until(s, 1, "main1")  # the old engine took one live player for a finished game and never left the untap step
    assert s.state.rules.winner is None and s.state.rules.draw_reason is None
    act(s, "p1", type="draw", count=3)  # (drawing by hand stays a table action)
    hand = s.state.zones["p1:hand"]
    mountain = next(cid for cid in hand if s.state.cards[cid].name == "Mountain")
    act(s, "p1", type="play_land", card_id=mountain)
    assert s.state.cards[mountain].zone == "p1:battlefield"
    another = next((cid for cid in s.state.zones["p1:hand"] if s.state.cards[cid].name == "Mountain"), None)
    if another is not None:  # one land a turn (305.2): the rules still apply at a table for one
        try:
            act(s, "p1", type="play_land", card_id=another)
        except Exception as exc:  # noqa: BLE001
            assert "land" in str(exc).lower()
        else:
            raise AssertionError("a second land play in one turn was allowed")
    library = len(s.state.zones["p1:library"])
    pass_until(s, 2, "main1")  # through combat (nobody to attack), the end step and cleanup, into the next turn
    assert s.state.turn.active_player == "p1" and len(s.state.zones["p1:library"]) == library - 1  # the draw step drew
    replay_matches(s)

    payload = {"format": "fyodor-save", "version": SAVE_VERSION, "saved_at": 0,
               "state": s.state.model_dump(mode="json"), "history": s.history.to_dict()}
    loaded, restored = load_payload(decode(encode(payload)))
    assert loaded.model_dump(mode="json") == s.state.model_dump(mode="json")
    assert restored is not None and restored.rebuild().model_dump(mode="json") == loaded.model_dump(mode="json")
    again = GameSession(GameState.model_validate(loaded.model_dump(mode="json")), cards=cards)
    act(again, "p1", type="pass_priority")  # and play goes on after loading
    assert (again.state.turn.number, again.state.turn.phase) != (2, "main1")


def test_a_one_seat_sandbox_table_with_the_rules_turned_on(cards):
    """A Sandbox table starts manual; the host turns the rules on at the table and plays on alone."""
    s = solo(cards, format="sandbox")
    pass_until(s, 2, "main1")
    assert s.state.format == "sandbox" and s.state.rules.winner is None
    replay_matches(s)


def test_one_player_left_of_several_is_still_game_over(cards):
    bob = deck(cards, "Atraxa, Praetors' Voice", [(10, "Island")])
    alice = deck(cards, "Krenko, Mob Boss", [(10, "Mountain")])
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False, first_player=0)
    enable(state, "full")
    s = GameSession(state, cards=cards)
    act(s, "p2", type="concede")
    assert s.state.rules.winner == "p1"
    import pytest

    from app.game.errors import ActionError

    with pytest.raises(ActionError, match="The game is over"):  # the game is over: nothing moves on
        act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p1" and find(s.state, "Mountain").zone.startswith("p1:")
    replay_matches(s)
