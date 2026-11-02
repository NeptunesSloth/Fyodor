"""-- pod history -- the order players went out of a game (docs/GAME_NIGHT_FLOW.md, "Pod session and game are different objects").

Read after every applied action (``engine.apply``) from public facts only: a player the host removed from the table
(``PlayerState.left``), a concession (104.3a) or a loss the rules engine recorded (``RulesState.lost``, with its reason: 704.5a-c,
903.10a, 704.5b, an effect, 104.2b another player winning). Applying the same actions again records the same order, so a replay,
an undo (a rebuild) and a save/load all agree. Players who went out in the same action went out together. A player already out
when the table was first tracked (an older save) is listed with no turn: the order they went out in is not known.
"""

from __future__ import annotations

from app.game.state import Elimination, GameState


def how(reason: str) -> str:
    """The engine's loss reason as a short code (``app.rules.sba.find``, ``win_game``, ``replace``); "out" when unknown."""
    text = reason.strip().lower()
    if text == "0 or less life":
        return "life"
    if text.endswith("poison counters"):
        return "poison"
    if "from one commander" in text:
        return "commander_damage"
    if text == "drew from an empty library":
        return "empty_library"
    if text == "an effect":
        return "effect"
    if text.endswith(" won the game"):
        return "opponent_won"
    return "out"


def out_now(state: GameState) -> dict[str, tuple[str, str]]:
    """Every player out of the game right now: (how, reason), in seat order (a removed player keeps their place)."""
    r = state.rules
    out: dict[str, tuple[str, str]] = {}
    for pid, p in state.players.items():
        if p.left:
            out[pid] = ("left", "")
        elif r is not None and pid in r.conceded:
            out[pid] = ("conceded", "")
        elif r is not None and pid in r.lost:
            reason = str(r.lost[pid])[:120]
            out[pid] = (how(reason), reason)
    return out


def note(state: GameState, before: set[str]) -> None:
    """Record who went out with the action just applied (``before``: who was out before it). Changes nothing otherwise."""
    now = out_now(state)
    known = {e.player for e in state.eliminations}
    if known == set(now):
        return
    kept = [e for e in state.eliminations if e.player in now]  # an engine bookkeeping reset brought a player back
    legacy = [pid for pid in now if pid not in known and pid in before]
    fresh = [pid for pid in now if pid not in known and pid not in before]
    # in the order the engine recorded them: concessions, then losses, then removals (ties share the action anyway)
    r = state.rules
    rank = {pid: i for i, pid in enumerate([*(r.conceded if r else []), *(r.lost if r else {})])}
    fresh.sort(key=lambda pid: rank.get(pid, len(rank)))
    state.eliminations = [
        *[Elimination(player=pid, turn=None, how=now[pid][0], reason=now[pid][1], seq=0) for pid in legacy],
        *kept,
        *[Elimination(player=pid, turn=state.turn.number, how=now[pid][0], reason=now[pid][1], seq=state.seq) for pid in fresh],
    ]
