"""-- playtest (nov 17) -- a Sandbox table at Full automation with two opponents the server plays for (the user's report: "Opponent" at
-38 life still on the table). A bot whose life, poison or commander damage reaches a losing total loses at the next state-based check
(704.3: the next time a player would receive priority; a table edit by hand is not an intent, so that is the next intent anyone sends,
the bot's own pass included), leaves the game (800.4a) and never takes another turn; poison counts at ten (704.5c); the view says who is
out and why (the plaque shows it: frontend SeatPlate "Out")."""

from __future__ import annotations

from app.game import bot
from app.game.factory import PlayerSetup, new_game
from app.game.handlers.zones import draw_cards
from app.game.session import GameSession
from app.game.state import GameSettings
from tests.game_helpers import act, deck, turn_on
from tests.test_test_opponent import GRUUL, human_move, replay_matches


def three(cards) -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", [(30, "Mountain")])
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Opponent", cards=deck(cards, "Krenko, Mob Boss", GRUUL)),
                      PlayerSetup("Opponent 2", cards=deck(cards, "Krenko, Mob Boss", GRUUL))],
                     name="Deck test", format="sandbox", settings=GameSettings(starting_life=40, allow_test_objects=True), shuffle=False,
                     first_player=0)
    for pid in ("p2", "p3"):
        state.players[pid].bot = "simple"
    for pid in ("p1", "p2", "p3"):
        draw_cards(state, pid, 7)
    s = GameSession(state, cards=cards)
    turn_on(s)
    return s


def step(s: GameSession) -> bool:
    return bot.step(s) is not None or human_move(s)


def test_a_bot_set_below_zero_by_hand_loses_at_the_next_check_and_never_plays_again(cards):
    s = three(cards)
    for _ in range(30):
        step(s)
    act(s, "p1", type="set_life", player="p2", value=-38)
    assert step(s)  # (the next intent, whoever sends it: its state-based check)
    r = s.state.rules
    assert r.lost.get("p2") == "0 or less life" and r.winner is None
    assert s.view("p1")["rules"]["lost"] == {"p2": "0 or less life"}
    mark, turns = len(s.history.actions), set()
    for _ in range(600):
        if s.state.turn.number > 12:
            break
        turns.add(s.state.turn.active_player)
        if not step(s):
            break
    assert s.state.turn.number > 12 and "p2" not in turns
    assert all(a.actor != "p2" for a in s.history.actions[mark:])
    replay_matches(s)


def test_ten_poison_counters_lose_nine_dont(cards):
    s = three(cards)
    for _ in range(10):
        step(s)
    act(s, "p1", type="resource", player="p3", key="poison", delta=9)
    step(s)
    assert "p3" not in s.state.rules.lost
    act(s, "p1", type="resource", player="p3", key="poison", delta=10)  # (19, as on the user's plaque: lethal either way)
    step(s)
    assert s.state.rules.lost.get("p3") == "10 poison counters"
