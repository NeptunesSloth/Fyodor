"""The rules part of a player's view: priority, the pending decision, and hints.

Same privacy rules as the table view:

* a decision's options (which may name cards in a hand) go only to the player who decides;
  everyone else sees who is deciding and the public prompt;
* hints ("which of *your* cards can you play") only ever describe the viewer's own cards.
"""

from __future__ import annotations

from typing import Any

from app.game.rules_state import preset_name
from app.game.state import GameState, zone_key
from app.game.visibility import OMNISCIENT, can_see
from app.rules import characteristics as chars
from app.rules.casting import activatable, castable
from app.rules.characteristics import CardInfo
from app.rules.engine import land_play_problem
from app.rules.plan import live_players


def rules_view(state: GameState, viewer: str, info: CardInfo) -> dict[str, Any] | None:
    r = state.rules
    settings = state.settings
    if settings.automation == "off" or r is None:
        return None  # a dormant rules state (automation turned off) isn't shown
    prefs = r.prefs_for(viewer) if viewer in state.players else None
    out: dict[str, Any] = {
        "automation": settings.automation,
        "preset": preset_name(settings.automation, settings.automation_options),
        "options": settings.automation_options.model_dump(),
        # The compact HUD: "AUTO: FULL / RESP: AUTO".
        "status": {"auto": ("paused" if r.paused else settings.automation).upper(),
                   "resp": prefs.response.upper() if prefs else None},
        "paused": r.paused,
        "priority": r.priority,
        "passed": list(r.passed),
        "conceded": list(r.conceded),
        "lost": dict(r.lost),
        "winner": r.winner,
        "overrides": r.overrides,
        "decision": None,
        # Only your own preferences (your yields and payment settings are nobody else's business).
        "prefs": prefs.model_dump(exclude={"pass_mark"}) if prefs else None,
        "reconcile": [i.model_dump() for i in r.reconcile],
        "card_modes": {cid: m for cid, m in r.card_modes.items()
                       if cid in state.cards and (viewer == OMNISCIENT or can_see(state, state.cards[cid], viewer))},
        "hints": {},
        "stats": stats(state, viewer, info),
    }
    d = r.decision
    if d is not None:
        decision: dict[str, Any] = {"id": d.id, "player": d.player, "kind": d.kind, "prompt": d.prompt,
                                    "source_id": d.source_id}
        if viewer in (d.player, OMNISCIENT):
            decision.update(options=[o.model_dump() for o in d.options], min_choices=d.min_choices,
                            max_choices=d.max_choices, rememberable=d.memory_key is not None)
            if d.display is not None:
                decision["display"] = d.display
        out["decision"] = decision
    if viewer in state.players and viewer in live_players(state) and not r.paused:
        out["hints"] = hints(state, viewer, info)
    return out


def stats(state: GameState, viewer: str, info: CardInfo) -> dict[str, dict[str, Any]]:
    """Current power/toughness and keywords of visible battlefield creatures where the rules
    change them (anthems, pumps, counters, crew …), so the table can show the real numbers."""
    from app.rules.layers import derive

    out: dict[str, dict[str, Any]] = {}
    for cid in (c for z, ids in state.zones.items() if z.endswith(":battlefield") for c in ids):
        card = state.cards[cid]
        if card.face_down or not (viewer == OMNISCIENT or can_see(state, card, viewer)):
            continue
        printed = chars.of(card, info)
        now = derive(state, card, printed, info)
        entry: dict[str, Any] = {}
        granted = [{"index": a.index, "text": a.text, "kind": a.kind} for a in now.abilities if a.index >= 100]
        if granted:
            entry["abilities"] = granted  # granted by other permanents (All Slivers have "…")
        if not now.is_creature:
            if entry:
                out[cid] = entry
            continue
        if now.pt is not None and (str(now.pt[0]), str(now.pt[1])) != (printed.power, printed.toughness):
            entry["pt"] = list(now.pt)
            entry["base"] = [printed.power, printed.toughness]
        gained = sorted(now.keywords - printed.keywords)
        lost = sorted(printed.keywords - now.keywords)
        if gained:
            entry["gained"] = gained
        if lost:
            entry["lost"] = lost
        if not printed.is_creature:
            entry["creature"] = True  # e.g. a crewed Vehicle
        if entry:
            out[cid] = entry
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
    out["activatable"] = activatable(state, viewer, info)
    out["castable"] = [
        cid
        for key in (zone_key(viewer, "hand"), zone_key(viewer, "command"), zone_key(viewer, "graveyard"))
        for cid in state.zones.get(key, [])
        if castable(state, viewer, state.cards[cid], info)
    ]
    return out
