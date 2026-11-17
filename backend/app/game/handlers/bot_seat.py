"""-- test opponent -- Sandbox's opponent that plays a deck ("Add an opponent"): a seat nobody sits in, with a deck of its own. It takes
turns like any player; with rules automation at Full the server plays for it through the same intents a player sends (app/game/bot.py,
paced by app/multiplayer/bots.py). Its deck arrives like ``load_deck``'s (the server builds the action from a saved deck, with every
card's id and the library's shuffle recorded), so history replays it exactly.

* A table seats at most ``autoseat.MAX_NON_HUMAN`` dummies and opponents together, beside the player testing a deck.
* Seated while the opening hands are being decided, it gets an opening hand and decides on it like anyone (the server decides for it).
"""

from __future__ import annotations

from app.game import actions as A
from app.game.autoseat import MAX_NON_HUMAN, non_human
from app.game.errors import ActionError
from app.game.handlers import solo
from app.game.handlers.dummy import MAX_SEATS
from app.game.handlers.zones import draw_cards
from app.game.ops import log, pname, text
from app.game.state import PLAYER_ZONES, GameState, PlayerState, PregameSeat, zone_key

NAME = "Opponent"
COLOR = "#7d6b9e"  # muted violet: a seat colour no pod seat starts with (its name and the bot mark say what it is)
POLICIES = {"simple": "Simple"}


def add_bot(state: GameState, a: A.AddBot) -> None:
    if not state.settings.allow_test_objects:
        raise ActionError("A test opponent is a solo tool: test cards are off at this table (the host can enable them)")
    if a.r is None:
        raise ActionError("unresolved deck")
    if not any(c.section in ("main", "commander") for c in a.cards):
        raise ActionError("That deck has no cards")
    seated = [pid for pid in state.seat_order if non_human(state, pid) and not state.players[pid].left]
    if len(seated) >= MAX_NON_HUMAN:
        raise ActionError(f"This table already has {MAX_NON_HUMAN} dummies and opponents")
    if len(state.seat_order) >= MAX_SEATS:
        raise ActionError(f"The table is full ({MAX_SEATS} seats)")
    n = len(state.players) + 1  # (a removed player keeps their id: never reused)
    while f"p{n}" in state.players:
        n += 1
    pid = f"p{n}"
    bots = sum(1 for p in state.players.values() if p.bot is not None)
    name = (a.name or "").strip() or (NAME if not bots else f"{NAME} {bots + 1}")
    life = state.settings.starting_life
    state.players[pid] = PlayerState(id=pid, name=name, color=COLOR, life=life, bot=a.policy, deck_id=a.deck_id,
                                     deck_name=a.deck_name)
    state.seat_order.append(pid)
    for zone in PLAYER_ZONES:
        state.zones.setdefault(zone_key(pid, zone), [])
    state.collections.setdefault(pid, [])
    if state.turn.starting_life is not None:
        state.turn.starting_life[pid] = life
    pregame = state.pregame is not None and not state.pregame.finished and state.settings.mulligan is not None
    hand = state.settings.mulligan.starting_hand_size if pregame and state.settings.mulligan is not None else 7
    deck = A.LoadDeck(player=pid, deck_name=a.deck_name, deck_id=a.deck_id, cards=a.cards, draw=0, r=a.r, actor=a.actor, ts=a.ts)
    solo.load_deck(state, deck)
    hand = min(hand, len(state.zones.get(zone_key(pid, "library"), [])))
    if hand:
        draw_cards(state, pid, hand)
    if state.turn.starting_hand is not None:
        state.turn.starting_hand[pid] = hand
    if pregame:
        assert state.pregame is not None
        state.pregame.seats[pid] = PregameSeat()  # it decides on its opening hand like anyone (app/game/bot.py)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" added an opponent: "), pname(state, pid),
                               text(f" plays {a.deck_name} ({POLICIES[a.policy]})")])
