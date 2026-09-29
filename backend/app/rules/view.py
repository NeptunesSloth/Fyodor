"""The rules part of a player's view: priority, the pending decision, and hints.

Same privacy rules as the table view:

* a decision's options (which may name cards in a hand) go only to the player who decides;
  everyone else sees who is deciding and the public prompt;
* hints ("which of *your* cards can you play") only ever describe the viewer's own cards.
"""

from __future__ import annotations

from typing import Any

from app.game.state import GameState, zone_key
from app.game.visibility import OMNISCIENT
from app.rules import characteristics as chars
from app.rules.casting import castable
from app.rules.characteristics import CardInfo
from app.rules.engine import land_play_problem
from app.rules.plan import live_players


def rules_view(state: GameState, viewer: str, info: CardInfo) -> dict[str, Any] | None:
    r = state.rules
    if state.settings.automation != "rules" or r is None:
        return None
    out: dict[str, Any] = {
        "automation": "rules",
        "paused": r.paused,
        "priority": r.priority,
        "passed": list(r.passed),
        "conceded": list(r.conceded),
        "overrides": r.overrides,
        "decision": None,
        "stops": r.stops_for(viewer).model_dump() if viewer in state.players else None,
        "hints": {},
    }
    d = r.decision
    if d is not None:
        decision: dict[str, Any] = {"id": d.id, "player": d.player, "kind": d.kind, "prompt": d.prompt,
                                    "source_id": d.source_id}
        if viewer in (d.player, OMNISCIENT):
            decision.update(options=[o.model_dump() for o in d.options], min_choices=d.min_choices,
                            max_choices=d.max_choices)
        out["decision"] = decision
    if viewer in state.players and viewer in live_players(state) and not r.paused:
        out["hints"] = hints(state, viewer, info)
    return out


def hints(state: GameState, viewer: str, info: CardInfo) -> dict[str, Any]:
    """What the viewer could do right now, for highlighting. Only about the viewer's own cards."""
    out: dict[str, Any] = {"has_priority": state.rules is not None and state.rules.priority == viewer}
    if not out["has_priority"]:
        return out
    playable = []
    for cid in state.zones.get(zone_key(viewer, "hand"), []):
        card = state.cards[cid]
        if land_play_problem(state, viewer, card, chars.of(card, info)) is None:
            playable.append(cid)
    out["playable_lands"] = playable
    out["castable"] = [
        cid
        for key in (zone_key(viewer, "hand"), zone_key(viewer, "command"))
        for cid in state.zones.get(key, [])
        if castable(state, viewer, state.cards[cid], info)
    ]
    return out
