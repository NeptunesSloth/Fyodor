"""-- controlling another player (wave 18H) -- who makes a player's choices (CR 723), read from the table alone.

723.5: the controller makes every choice and decision the controlled player is allowed to make; 723.3: only the
player is controlled, never their objects; 723.4: whatever the controlled player may see, the controller sees too
(``visibility.can_see``). Control comes from ``RulesState.player_control`` ("active": during that player's turn, 723.1)
and, for a search, from a decision's ``decider`` (Opposition Agent, set when the search is asked).
"""

from __future__ import annotations

from app.game.state import GameState


def _live(state: GameState, pid: str) -> bool:
    r = state.rules
    return r is None or (pid not in r.conceded and pid not in r.lost)  # 800.4a: a departed controller's effect ended


def controller_of(state: GameState, pid: str) -> str:
    """The player making ``pid``'s choices now (``pid`` itself when nobody controls them, 723.9)."""
    r = state.rules
    if r is not None:
        for c in reversed(r.player_control):
            if c.status == "active" and c.controlled == pid and _live(state, c.controller):
                return c.controller
    return pid


def controlled_by(state: GameState, viewer: str) -> list[str]:
    """The players ``viewer`` controls right now (not themselves)."""
    if state.rules is None or not state.rules.player_control:
        return []
    return [p for p in state.seat_order if p != viewer and controller_of(state, p) == viewer]


def acting_as(state: GameState, client: str) -> str:
    """The seat ``client``'s rules intent is for (723.5, 723.8): the pending decision's player when ``client`` makes it,
    else the player holding priority when ``client`` controls them, else the client's own seat. Raises ValueError for a
    client who is being controlled where it is the controller's call."""
    r = state.rules
    if r is None:
        return client
    d = r.decision
    if d is not None:
        decider = d.decider or controller_of(state, d.player)
        if client == d.player != decider:
            raise ValueError(f"{state.players[decider].name} is making this choice for you")
        return d.player if client == decider else client
    p = r.priority
    if p is not None:
        decider = controller_of(state, p)
        if client == p != decider:
            raise ValueError(f"{state.players[decider].name} is controlling you this turn")
        return p if client == decider else client
    return client
