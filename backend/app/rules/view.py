"""The rules part of a player's view: priority, the pending decision, and hints.

Same privacy rules as the table view:

* a decision's options (which may name cards in a hand) go only to the player who decides;
  everyone else sees who is deciding and the public prompt;
* hints ("which of *your* cards can you play") only ever describe the viewer's own cards.
"""

from __future__ import annotations

from typing import Any

from app.game import ops
from app.game.control import acting_as, controller_of, decider_of
from app.game.rules_state import cancelable, preset_name
from app.game.state import GameState, zone_key
from app.game.visibility import OMNISCIENT, can_see, mask_face_down
from app.rules import characteristics as chars
from app.rules import read_pass, wave110c_chorus
from app.rules.casting import (
    activatable,
    alt_castable,
    announces_kicker_x,
    announces_x,
    castable,
    free_castable,
    optional_castable,
)
from app.rules.characteristics import CardInfo
from app.rules.engine import land_play_problem
from app.rules.plan import live_players


def rules_view(state: GameState, viewer: str, info: CardInfo) -> dict[str, Any] | None:
    with read_pass.scope(state, info):  # (wave 29A) a view only reads the table: what every card shares is worked out once
        return _rules_view(state, viewer, info)


def _rules_view(state: GameState, viewer: str, info: CardInfo) -> dict[str, Any] | None:
    r = state.rules
    settings = state.settings
    if settings.automation == "off" or r is None:
        return None  # a dormant rules state (automation turned off) isn't shown
    prefs = r.prefs_for(viewer) if viewer in state.players else None
    from app.rules import banding

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
        "attacking_bands": banding.live_bands(state),
        "conceded": list(r.conceded),
        "lost": dict(r.lost),
        "winner": r.winner,
        "draw_reason": r.draw_reason,
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
        "control": [{"controlled": c.controlled, "controller": c.controller, "status": c.status} for c in r.player_control
                    if c.status == "pending" or controller_of(state, c.controlled) == c.controller],  # (an ended one: not shown)
    }
    d = r.decision
    if d is not None:
        out["decision"] = decision_view(state, d, viewer)
    if viewer in state.players and viewer in live_players(state) and not r.paused and r.draw_reason is None:
        try:  # -- controlling another player (wave 18H) -- 723.5: the controller's hints are for the player they act as
            seat = acting_as(state, viewer)
        except ValueError:  # the controlled player: nothing to do but concede (723.6)
            out["hints"] = {"has_priority": False}
            out["controlled_by"] = controller_of(state, viewer) if r.decision is None else decider_of(state, r.decision)
        else:
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

# -- public choice wheel (TABLETOP_QOL_MILESTONE.md) -- the rules steps whose single choice is among public values: a named color, creature or
# card type, number, word or player ("choose_value", 105.1 / 205.3m / 607.2; "choose_each" asks each player in turn, 101.4), "an opponent" that
# isn't a target (choose_opponent), a commander's color before the game (903.4b: revealed), which mana a mana ability or effect adds, a
# protection / prevention color, a counter kind, fabricate / endure / tap-or-untap / friend-or-foe, a dungeon, a gift's or assist's player. Never
# a target (chosen on the table), a cost, a secret choice (group_choice "gc_secret" / "gc_bid": revealed later) or anything about hidden cards.
PUBLIC_CHOICE_STEPS = frozenset({
    "choose_value", "choose_each", "choose_opponent", "cmd_color110f",
    "add_mana", "mana_ability", "immediate_mana_production", "mana_composition", "mana_symbol_production",
    "prevent_color", "protection_choice", "become_pick", "counter_kind_choice",
    "fabricate", "endure", "tap_or_untap", "friend_foe", "venture", "gift", "assist",
})


def public_choice(d: Any) -> bool:
    """May the chooser's client offer this decision on its quick wheel? One answer among the public options of a known public step (above), or
    which of two public coin flips to keep (coin_group "ignore": heads or tails). Options naming a card (a target, a card looked at) or typed
    (a card name, a secret number: ``group``) never are. Read from the server-only ``resume``; sent to the chooser alone, as a flag."""
    if d.kind != "choose_one" or d.max_choices != 1 or d.display is not None:
        return False
    resume = d.resume or {}
    step = resume.get("step")
    known = step in PUBLIC_CHOICE_STEPS or (step == "coin_group" and resume.get("phase") == "ignore")
    return known and all(o.card_id is None and o.group is None for o in d.options)


def decision_view(state: GameState, d: Any, viewer: str) -> dict[str, Any]:
    """The pending decision as ``viewer`` may see it. The chooser (and the omniscient host view)
    gets all of it. Anyone else gets only public facts — who is choosing, and for combat
    declarations what they're declaring — built from structured fields, never from the chooser's
    prompt, options, labels, source card or presentation hints: a decision made while a spell is
    still in its caster's hand (601.2a: its targets, modes, division, costs) or about hidden cards
    (a search, a look, a private cost) must not reveal them (hidden information, 400.2)."""
    decider = decider_of(state, d)  # -- controlling another player (wave 18H) -- 723.5
    if viewer in (decider, OMNISCIENT):
        # -- keyword actions & face-down (wave 3F) -- 708.5: a face-down card the chooser may not look
        # at is never named in the prompt or an option's label
        options = [o.model_dump() for o in d.options]
        for o in options:
            o["label"] = mask_face_down(state, o["label"], viewer, refs=[o.get("card_id")])
        full: dict[str, Any] = {"id": d.id, "player": d.player if viewer == OMNISCIENT else decider, "kind": d.kind, "prompt": mask_face_down(state, d.prompt, viewer, refs=[d.source_id, *(o.card_id for o in d.options)]),
                                "source_id": d.source_id, "options": options,
                                "min_choices": d.min_choices, "max_choices": d.max_choices,
                                "rememberable": d.memory_key is not None,
                                "cancelable": cancelable(d)}  # (wave 24D)
        if d.display is not None:
            full["display"] = d.display
        if public_choice(d):
            full["public_choice"] = True  # (public choice wheel) the chooser's client may answer it on its radial picker
        if decider != d.player:
            full["for_player"] = d.player  # the player this choice is made for
        return full
    chooser = state.players[d.player].name if d.player in state.players else "A player"
    if decider != d.player and decider in state.players:  # (wave 18H) 723.5: who makes it is public, as who controls whom
        chooser = f"{state.players[decider].name} (for {chooser})"
    doing = _PUBLIC_KINDS.get(d.kind)
    return {"id": d.id, "player": d.player, "kind": d.kind if doing else "waiting",
            "prompt": f"{chooser} {doing or 'is making a choice'}", "source_id": None,
            "public": {"type": "PLAYER_MAKING_CHOICE", "chooser": chooser}}


def stats(state: GameState, viewer: str, info: CardInfo) -> dict[str, dict[str, Any]]:
    """Current battlefield characteristics and granted abilities of visible cards in hands/exile.

    The visibility check precedes derivation/publication, so a hand grant reveals no hidden card.
    """
    from app.rules import licids
    from app.rules.layers import derive

    out: dict[str, dict[str, Any]] = {}
    for cid in (c for z, ids in state.zones.items() if z.endswith((":battlefield", ":hand", ":exile")) for c in ids):
        card = state.cards[cid]
        if not (viewer == OMNISCIENT or can_see(state, card, viewer)):
            continue
        if card.face_down:
            if card.zone.endswith(":battlefield") and (viewer == OMNISCIENT or acting_as(state, viewer) == card.controller):
                from app.rules.casting import face_up_ways

                printed_face = chars.of(card.model_copy(update={"face_down": False}), info)
                ways = face_up_ways(card, printed_face, state=state, info=info)
                if ways:
                    from app.rules import morph_costs78

                    tax78 = morph_costs78.tax(state, info)
                    out[cid] = {"turn_up": [{"method": method, "cost": ('{' + str(tax78) + '}, ' + cost
                        if method == 'morph' and tax78 and not cost.startswith('{') else cost)} for method, (cost, _) in ways.items()]}
            continue
        printed = chars.of(card, info)
        now = derive(state, card, printed, info)
        entry: dict[str, Any] = {}
        granted = [{"index": a.index, "text": ops.shown(state, a.text), "kind": a.kind} for a in now.abilities if a.index >= 100]
        if granted:
            entry["abilities"] = granted  # Visibility was checked before reading any outside-zone grant.
        if not card.zone.endswith(":battlefield"):
            if entry:
                out[cid] = entry
            continue
        if now.doors is not None:
            entry["doors"] = sorted(now.doors)  # -- Rooms (wave 18G) -- 709.5c: public (the designations are on the table)
            from app.rules.copying import (
                room_printing,  # (review 18G: a copy of a Room has the copied card's halves, 709.5b)
            )

            data = info.get(room_printing(state.rules, card, state.rules.object_id(card.id))) if state.rules else None
            if data is not None and chars.room(data):
                entry["halves"] = [{"name": h.name, "mana_cost": h.mana_cost} for h in (chars.half_from_data(data, i) for i in (0, 1))]
        if end := licids.ending(state, card, viewer):  # -- licids (wave 50A) -- 116.2c: the cost of the special action that ends the viewer's effect on it
            entry["end_cost"] = end[0].end_cost
        from app.rules import (
            wave110a_arbiter,  # -- wave 110A -- Leonin Arbiter: any player may pay {2} (shown until they have)
        )

        if card.zone.endswith(":battlefield") and wave110a_arbiter.has(now) and "end_cost" not in entry:
            entry["end_cost"] = wave110a_arbiter.COST
            entry["end_label"] = f"Ignore {card.name or 'this effect'} until end of turn"  # (not "end the effect": 116.2c's special action only lets the payer ignore it)
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
    with read_pass.scope(state, info):  # (wave 29A) nothing here changes the table: the statics are read once, not once per card and kind
        return _hints(state, viewer, info)


def _hints(state: GameState, viewer: str, info: CardInfo) -> dict[str, Any]:
    out: dict[str, Any] = {"has_priority": state.rules is not None and state.rules.priority == viewer}
    if state.rules is not None and state.rules.miracle:  # -- casting extras (wave 18E) -- only the owner's own windows (app/rules/miracle.py)
        mine = [c for c in state.rules.miracle if c in state.cards and state.cards[c].owner == viewer]
        if mine:
            out["miracle"] = mine
    from app.rules import deferred_payment82

    windows = deferred_payment82.active(state, viewer)
    if windows:
        out["deferred_payments"] = [{"id": w.id, "cost": w.cost, "name": w.name} for w in windows]
    if not out["has_priority"]:
        return out
    from app.rules import wave110i_cards

    if wave110i_cards.channel_active(state, viewer):
        out["channel"] = wave110i_cards.CHANNEL_ID  # -- cards (wave 110I) -- Channel: the viewer's own player-level mana ability (605.3a), the ActivateAbility.card_id to send
    # Your hand, your commander, your graveyard and exile (flashback, "you may play that card this
    # turn" …) and the top card of your library — that one only when you can see it (601.3f in
    # spirit: a card you can't look at isn't offered, so the hint reveals nothing about it).
    candidates = [cid for key in (zone_key(viewer, "hand"), zone_key(viewer, "command"), zone_key(viewer, "graveyard"),
                                  zone_key(viewer, "exile"), zone_key(viewer, "foretell")) for cid in state.zones.get(key, [])
                  if can_see(state, state.cards[cid], viewer)]  # (-- review (sys 18A) -- not a face-down exiled card nobody looked at, 406.3)
    # -- review 30 -- a card in another player's exile this viewer may cast or play (Hostage Taker, Valgavoth, Jeleva, Opposition Agent: the
    # card stays in its owner's exile, 400.3): the hints are this viewer's own, so listing it tells no one else anything
    # Only cards a grant could name are checked (a permission for that object, a linked "exiled with" set: permissions.grants reads nothing
    # else for another player's card), so a big exile costs nothing (wave 29A's hint speed)
    r = state.rules
    named = {o for objs in r.exiled_with.values() for o in objs} | {o for p in r.permissions if p.player == viewer for o in (p.object_id, r.object_id(p.card) if p.card else None) if o} \
        if r is not None else set()
    candidates += [cid for pid in state.players if pid != viewer for cid in state.zones.get(zone_key(pid, "exile"), [])
                   if r is not None and (r.object_id(cid) in named or cid in r.free_casts) and can_see(state, state.cards[cid], viewer)]
    library = state.zones.get(zone_key(viewer, "library"), [])
    if library and can_see(state, state.cards[library[0]], viewer):
        candidates.append(library[0])
    # -- Xanathar (wave 110C) -- the top card of another player's library a permission of this viewer's names (601.3), only when the viewer sees it (401.5)
    for owner in {p.library_of for p in r.permissions if p.player == viewer and p.library_of and p.zone == "library_top"} if r is not None else ():
        theirs = state.zones.get(zone_key(owner, "library"), [])
        if theirs and can_see(state, state.cards[theirs[0]], viewer):
            candidates.append(theirs[0])
    from app.rules.pooled_casting_authorities71 import external_candidates

    candidates = list(dict.fromkeys([*candidates, *external_candidates(state, viewer, info)]))
    playable = []
    for cid in candidates:
        card = state.cards[cid]
        if land_play_problem(state, viewer, card, chars.of(card, info), info=info) is None:
            playable.append(cid)
    out["playable_lands"] = playable
    out["activatable"] = activatable(state, viewer, info, announce=True)  # (soak: targets too)
    out["castable"] = [cid for cid in candidates if castable(state, viewer, state.cards[cid], info, announce=True)]  # (soak: modes and targets too)
    # (wave 24D) 107.3a: castable cards that ask for X when cast (the server validates the range; min 0)
    if x_cast := [cid for cid in out["castable"] if announces_x(state.cards[cid], info)]:
        out["x_cast"] = x_cast
    if x_kicker := [cid for cid in out["castable"] if announces_kicker_x(state.cards[cid], info)]:  # (wave 43D: "Kicker {X}", asked only when kicked)
        out["x_kicker"] = x_kicker
    if chorus := [cid for cid in out["castable"] if wave110c_chorus.offered(state, viewer, state.cards[cid], chars.of(state.cards[cid], info), info)]:
        out["chorus"] = chorus  # -- Chorus of the Conclave (wave 110C) -- castable cards whose cast may carry CastSpell.chorus (601.2b, 0-1000)
    from app.rules import (
        wave111r3_replicate,  # -- granted replicate (wave 111R3) -- card id → the labels of CastSpell.replicate's counts (702.56b)
    )

    if replicated := {cid: labels for cid in out["castable"] if (labels := wave111r3_replicate.hint(state, viewer, state.cards[cid], info))}:
        out["replicate111r3"] = replicated
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
