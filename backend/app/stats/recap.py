"""-- pod history -- what a recorded game keeps besides who won (docs/GAME_NIGHT_FLOW.md, "Pod session and game are different
objects"): the order players went out (``GameState.eliminations``, ``app.game.eliminations``) and a compact final board.

Both are public only. The final board is what a spectator saw on the table when the result was recorded: each player's life,
poison, commanders, the permanents on their battlefield by name and count (a face-down one the spectator can't look at is a
"face-down card"; 708.9 reveals them only when the engine ended the game), and how many cards are in their graveyard and exile.
Never a hand, a library or anything else a spectator could not see. Small: at most ``MAX_NAMES`` names per player.
"""

from __future__ import annotations

from typing import Any

from app.game.resolve import CardInfo
from app.game.state import CardInstance, GameState
from app.game.visibility import SPECTATOR, can_see

MAX_NAMES = 30  # distinct permanent names kept per player; the rest is counted in "more"
FACE_DOWN = "face-down card"


def elimination_order(state: GameState, names: dict[str, str]) -> list[dict[str, Any]]:
    """Who went out, in order: place (players out in the same action share it), turn (None: not known), how and why."""
    out: list[dict[str, Any]] = []
    place, last_seq = 0, None
    for i, e in enumerate(state.eliminations):
        if e.player not in state.players:
            continue
        if not (e.seq and e.seq == last_seq):
            place = i + 1
        last_seq = e.seq
        out.append({"seat": e.player, "name": names.get(e.player) or state.players[e.player].name, "place": place,
                    "turn": e.turn, "how": e.how, "reason": e.reason})
    return out


def _is_land(card: CardInstance, cards: CardInfo | None) -> bool:
    if card.token is not None:
        token = card.token.back if card.face == 1 and card.token.back is not None else card.token
        return "Land" in token.type_line
    info = cards.get(card.card_id) if cards is not None and card.card_id else None
    if not info:
        return False
    faces = info.get("faces") or []
    line = faces[card.face].get("type_line") if 0 <= card.face < len(faces) else None
    return "Land" in str(line or info.get("type_line") or "")


def final_board(state: GameState, names: dict[str, str], cards: CardInfo | None = None) -> list[dict[str, Any]]:
    """Each seated player's public end-of-game table, in seat order."""
    board: list[dict[str, Any]] = []
    for pid in state.seat_order:
        p = state.players[pid]
        tally: dict[tuple[str, bool], int] = {}
        for cid in state.zones.get(f"{pid}:battlefield", []):
            c = state.cards.get(cid)
            if c is None or c.ability is not None:
                continue
            seen = bool(c.name) and can_see(state, c, SPECTATOR)
            key = (c.name, _is_land(c, cards)) if seen else (FACE_DOWN, False)
            tally[key] = tally.get(key, 0) + (max(1, c.quantity) if c.is_token else 1)
        ordered = sorted(tally.items(), key=lambda kv: (kv[0][1], kv[0][0] == FACE_DOWN, kv[0][0].casefold()))
        kept = ordered[:MAX_NAMES]
        permanents = [{"name": name, "count": n, **({"land": True} if land else {})} for (name, land), n in kept]
        commanders = sorted({c.name for c in state.cards.values() if c.commander_key and c.owner == pid})
        board.append({
            "seat": pid, "name": names.get(pid) or p.name, "life": p.life, "poison": int(p.resources.get("poison", 0) or 0),
            "commanders": commanders, "permanents": permanents, "more": sum(n for _, n in ordered[MAX_NAMES:]),
            "graveyard": len(state.zones.get(f"{pid}:graveyard", [])),
            "exile": len(state.zones.get(f"{pid}:exile", [])) + len(state.zones.get(f"{pid}:foretell", [])),
        })
    return board
