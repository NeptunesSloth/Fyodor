"""The rules part of a player's view: priority, the pending decision, and hints.

Same privacy rules as the table view:

* a decision's options (which may name cards in a hand) go only to the player who decides;
  everyone else sees who is deciding and the public prompt;
* hints ("which of *your* cards can you play") only ever describe the viewer's own cards.
"""

from __future__ import annotations

from typing import Any

from app.game.control import acting_as, controller_of
from app.game.rules_state import preset_name
from app.game.state import GameState, zone_key
from app.game.visibility import OMNISCIENT, can_see, mask_face_down
from app.rules import characteristics as chars
from app.rules.casting import activatable, alt_castable, castable, free_castable, optional_castable
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
        # -- counters & designations (wave 3E): dungeons, venture markers and the Ring (public, 309.2b / 701.54) --
        "designations": designations_view(state),
        # -- controlling another player (wave 18H) -- 723: who controls whom this turn is a public fact
        "control": [{"controlled": c.controlled, "controller": c.controller, "status": c.status} for c in r.player_control],
    }
    d = r.decision
    if d is not None:
        out["decision"] = decision_view(state, d, viewer)
    if viewer in state.players and viewer in live_players(state) and not r.paused:
        try:  # -- controlling another player (wave 18H) -- 723.5: the controller's hints are for the player they act as
            seat = acting_as(state, viewer)
        except ValueError:
            seat = viewer
        out["hints"] = hints(state, seat, info)
        out["acting_as"] = seat if seat != viewer else None
    return out


def designations_view(state: GameState) -> dict[str, Any]:
    """-- counters & designations (wave 3E) -- Each player's dungeon in the command zone and the room their
    venture marker is on, the dungeons they completed, how many times the Ring tempted them and their
    Ring-bearer (a permanent on the battlefield): all public."""
    r = state.rules
    assert r is not None
    out: dict[str, Any] = {}
    for pid in state.players:
        mark = r.dungeons.get(pid)
        bearer = r.ring_bearers.get(pid)
        card = bearer.rsplit(".", 1)[0] if bearer else None
        entry = {"dungeon": mark.model_dump() if mark else None, "completed": list(r.completed_dungeons.get(pid, [])),
                 "ring": r.ring_tempted.get(pid, 0),
                 "ring_bearer": card if card in state.cards and state.cards[card].zone.endswith(":battlefield") else None}
        if entry["dungeon"] or entry["completed"] or entry["ring"]:
            out[pid] = entry
    return out


# Decisions whose existence and nature are public facts of the game (anyone watching knows combat is
# being declared). Every other decision is shown to other players only as "someone is choosing".
_PUBLIC_KINDS = {"declare_attackers": "is declaring attackers", "declare_blockers": "is declaring blockers"}


def decision_view(state: GameState, d: Any, viewer: str) -> dict[str, Any]:
    """The pending decision as ``viewer`` may see it. The chooser (and the omniscient host view)
    gets all of it. Anyone else gets only public facts — who is choosing, and for combat
    declarations what they're declaring — built from structured fields, never from the chooser's
    prompt, options, labels, source card or presentation hints: a decision made while a spell is
    still in its caster's hand (601.2a: its targets, modes, division, costs) or about hidden cards
    (a search, a look, a private cost) must not reveal them (hidden information, 400.2)."""
    decider = d.decider or controller_of(state, d.player)  # -- controlling another player (wave 18H) -- 723.5
    if viewer in (decider, OMNISCIENT):
        # -- keyword actions & face-down (wave 3F) -- 708.5: a face-down card the chooser may not look
        # at is never named in the prompt or an option's label
        options = [o.model_dump() for o in d.options]
        for o in options:
            o["label"] = mask_face_down(state, o["label"], viewer, refs=[o.get("card_id")])
        full: dict[str, Any] = {"id": d.id, "player": d.player if viewer == OMNISCIENT else decider, "kind": d.kind, "prompt": mask_face_down(state, d.prompt, viewer, refs=[d.source_id, *(o.card_id for o in d.options)]),
                                "source_id": d.source_id, "options": options,
                                "min_choices": d.min_choices, "max_choices": d.max_choices,
                                "rememberable": d.memory_key is not None}
        if d.display is not None:
            full["display"] = d.display
        if decider != d.player:
            full["for_player"] = d.player  # the player this choice is made for
        return full
    chooser = state.players[d.player].name if d.player in state.players else "A player"
    doing = _PUBLIC_KINDS.get(d.kind)
    return {"id": d.id, "player": d.player, "kind": d.kind if doing else "waiting",
            "prompt": f"{chooser} {doing or 'is making a choice'}", "source_id": None,
            "public": {"type": "PLAYER_MAKING_CHOICE", "chooser": chooser}}


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
    # Your hand, your commander, your graveyard and exile (flashback, "you may play that card this
    # turn" …) and the top card of your library — that one only when you can see it (601.3f in
    # spirit: a card you can't look at isn't offered, so the hint reveals nothing about it).
    candidates = [cid for key in (zone_key(viewer, "hand"), zone_key(viewer, "command"), zone_key(viewer, "graveyard"),
                                  zone_key(viewer, "exile")) for cid in state.zones.get(key, [])]
    library = state.zones.get(zone_key(viewer, "library"), [])
    if library and can_see(state, state.cards[library[0]], viewer):
        candidates.append(library[0])
    playable = []
    for cid in candidates:
        card = state.cards[cid]
        if land_play_problem(state, viewer, card, chars.of(card, info), info=info) is None:
            playable.append(cid)
    out["playable_lands"] = playable
    out["activatable"] = activatable(state, viewer, info)
    out["castable"] = [cid for cid in candidates if castable(state, viewer, state.cards[cid], info)]
    # (wave 3C) cards a permission lets you cast without paying their mana costs
    out["free_castable"] = [cid for cid in candidates if free_castable(state, viewer, state.cards[cid], info)]
    # -- cost changers (wave 4I) -- alternative costs written on cards (118.9): card id → [{"id", "label"}]
    alt = {cid: found for cid in candidates if (found := alt_castable(state, viewer, state.cards[cid], info))}
    if alt:
        out["alt_castable"] = alt
    optional = {cid: found for cid in candidates if (found := optional_castable(state, viewer, state.cards[cid], info))}
    if optional:
        out["optional_costs"] = optional  # (Defiler of Vigor: card id → [{"id": source, "label"}])
    return out
