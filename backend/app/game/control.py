"""-- controlling another player (wave 18H) -- who makes a player's choices (CR 723), read from the table alone.

723.5: the controller makes every choice and decision the controlled player is allowed to make; 723.3: only the
player is controlled, never their objects; 723.4: whatever the controlled player may see, the controller sees too
(``visibility.can_see``). Control comes from ``RulesState.player_control`` ("active": during that player's turn, 723.1)
and, for a search, from a decision's ``decider`` (Opposition Agent, set when the search is asked).
"""

from __future__ import annotations

from typing import Any

from app.game.state import GameState


def _live(state: GameState, pid: str) -> bool:
    r = state.rules  # 800.4a: a departed controller's effect ended (conceded, lost, or removed from the table)
    return pid in state.players and not state.players[pid].left and (r is None or (pid not in r.conceded and pid not in r.lost))


def controller_of(state: GameState, pid: str) -> str:
    """The player making ``pid``'s choices now (``pid`` itself when nobody controls them, 723.9). 723.1: only during the
    turn the effect began on (read from the table, so a turn passed by hand, while paused or undone, ends it too)."""
    r = state.rules
    if r is not None:
        for c in reversed(r.player_control):
            if c.status == "active" and c.controlled == pid and _live(state, c.controller) and (
                    c.obj in state.zones.get("stack", []) if c.obj else pid == state.turn.active_player and c.turn == state.turn.number):  # (wave 110E: obj)
                return c.controller
    return pid


def lands_only(state: GameState, pid: str) -> bool:
    """Word of Command: while its control lasts the controlled player can activate mana abilities of lands only."""
    r = state.rules
    return r is not None and any(c.lands_only and c.controlled == pid and c.status == "active" and c.obj in state.zones.get("stack", []) for c in r.player_control)


def decider_of(state: GameState, d: Any) -> str:
    """Who makes decision ``d`` now: its recorded decider while still in the game (800.4a), else as for any choice."""
    return d.decider if d.decider and _live(state, d.decider) else controller_of(state, d.player)


def controlled_by(state: GameState, viewer: str) -> list[str]:
    """The players ``viewer`` controls right now (not themselves): during their turn (Mindslaver) or while the pending
    decision is made for them (Opposition Agent's search, 723.2)."""
    r = state.rules
    if r is None or not (r.player_control or (r.decision is not None and r.decision.decider)):
        return []
    d = r.decision
    return [p for p in state.seat_order if p != viewer and (
        controller_of(state, p) == viewer or (d is not None and not d.blind and d.player == p and decider_of(state, d) == viewer))]


def is_controlled(state: GameState, pid: str) -> bool:
    """True while another player makes ``pid``'s choices with automation running: ``pid`` may then only concede (723.6)."""
    r = state.rules
    if r is None or r.paused or state.settings.automation == "off":
        return False
    d = r.decision
    return controller_of(state, pid) != pid or (d is not None and d.player == pid and decider_of(state, d) != pid)


def acting_as(state: GameState, client: str) -> str:
    """The seat ``client``'s rules intent is for (723.5, 723.8): the pending decision's player when ``client`` makes it,
    else the player holding priority when ``client`` controls them, else the client's own seat. Raises ValueError for a
    client who is being controlled where it is the controller's call."""
    r = state.rules
    if r is None:
        return client
    d = r.decision
    if d is not None:
        decider = decider_of(state, d)
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
