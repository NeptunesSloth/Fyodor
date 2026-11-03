"""Per-viewer sanitized game views.

The server never sends the full state to a client. ``build_view`` produces exactly what one
viewer may know: hidden cards are reduced to opaque placeholders (no printing id, name,
note or face), libraries are sent as a count plus the cards the viewer knows, and log
entries name cards only for viewers who could see them.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.game.state import (
    ALL,
    OWNER_VISIBLE_ZONES,
    PUBLIC_ZONES,
    STACK,
    CardInstance,
    GameState,
    LogEntry,
    LogPart,
    split_zone,
)
from app.game.visibility import OMNISCIENT, SPECTATOR, can_see

VIEW_VERSION = 2
PLACEHOLDER_PREFIX = "hidden:"


def placeholder_id(zone_key: str, index: int) -> str:
    return f"{PLACEHOLDER_PREFIX}{zone_key}:{index}"


def hidden_order(state: GameState, ids: list[str]) -> list[str]:
    """Order anonymous cards by a keyed hash (secret per-game salt), never by entry order."""
    salt = state.hidden_salt.encode()
    return sorted(ids, key=lambda cid: hashlib.blake2b(cid.encode(), key=salt[:64] or b"fyodor", digest_size=12).digest())


def resolve_placeholder(state: GameState, value: str, viewer: str) -> str:
    """Map an anonymous placeholder id (as ``viewer`` saw it) back to a real card id.

    Clients may act on cards they can't identify (e.g. "discard a card at random"). The
    mapping is recomputed from the current state exactly as ``build_view`` produced it.
    """
    if not value.startswith(PLACEHOLDER_PREFIX):
        return value
    key, _, index_s = value[len(PLACEHOLDER_PREFIX):].rpartition(":")
    ids = state.zones.get(key)
    _, zone = split_zone(key) if key else (None, "")
    if ids is None or not index_s.isdigit() or zone not in OWNER_VISIBLE_ZONES:
        return value
    hidden = hidden_order(state, [cid for cid in ids if not can_see(state, state.cards[cid], viewer)])
    index = int(index_s)
    return hidden[index] if index < len(hidden) else value


def _copied(state: GameState, c: CardInstance, view: dict[str, Any]) -> None:
    """-- copies (the pod's decks: Irma becoming Kiora, Spark Double, Sakashima) -- a permanent a rules copy effect applies to (613.2a,
    layer 1) is shown as what it copied: that printing's face (or the copied token's values) and its name after the copy's exceptions,
    with a COPY mark naming what it copies. Copiable values are public (707.2): the same for every viewer, and never the copied
    object's id (it may since have gone somewhere hidden)."""
    from app.game.rules_state import copy_recipe_of

    assert state.rules is not None
    recipe = copy_recipe_of(state.rules, state.rules.object_id(c.id))
    if recipe is None or not (recipe.printing or recipe.token):
        return
    named = next((e.name for e in reversed(recipe.excepts) if e.name), None)
    if recipe.printing:
        view["card_id"], view["face"] = recipe.printing, recipe.face
    else:
        view["token"] = {**(view.get("token") or {}), **(recipe.token or {})}
    view["name"] = named or recipe.source or c.name
    changes = []
    for e in recipe.excepts:
        if e.name:
            changes.append(f"named {e.name}")
        if e.power is not None and e.toughness is not None:
            changes.append(f"{e.power}/{e.toughness}")
        if "Legendary" in e.remove_supertypes:
            changes.append("not legendary")
        changes += [f"is also {t}" for t in e.add_types + e.add_subtypes]
        changes += [f"has “{t if len(t) <= 60 else t[:57].rstrip() + '…'}”" for t in e.add_text]
    view["copy_of"] = {"source_id": "", "source_name": recipe.source or "a permanent", "modifications": "; ".join(dict.fromkeys(changes))[:300]}


def card_view(state: GameState, c: CardInstance, viewer: str) -> dict[str, Any]:
    _, zone = split_zone(c.zone)
    if can_see(state, c, viewer):
        view: dict[str, Any] = {
            "id": c.id,
            "card_id": c.card_id,
            "name": c.name,
            "owner": c.owner,
            "controller": c.controller,
            "zone": c.zone,
            "face": c.face,
            "face_down": c.face_down,
            "revealed": bool(c.revealed_to),
            "note": c.note,
            "is_token": c.is_token,
        }
        if c.token:
            view["token"] = c.token.model_dump()
            if c.token.back is not None and c.face == 1:  # -- wave 3F -- a transformed double-faced token (701.27)
                view["token"] = {**c.token.back.model_dump(), "front": c.token.model_dump(exclude={"back"})}
        if c.copy_of:
            view["copy_of"] = c.copy_of.model_dump()
        elif state.rules is not None and zone in ("battlefield", "phased") and not c.face_down:
            _copied(state, c, view)
        if c.ability:
            view["ability"] = c.ability.model_dump()
        if c.commander_key:
            view["commander_key"] = c.commander_key
        if c.merged:  # -- merged permanents (wave 18D) -- the cards representing it, topmost first (visible to whoever sees the permanent)
            view["merged"] = [{"id": p.id, "card_id": p.card_id, "name": p.name, "is_token": p.is_token,
                               **({"token": p.token.model_dump()} if p.token else {})} for p in c.merged]
            if c.melded:
                view["melded"] = True
        if c.categories and viewer in (c.owner, OMNISCIENT):
            view["categories"] = list(c.categories)
    else:
        view = {"id": c.id, "hidden": True, "owner": c.owner, "controller": c.controller, "zone": c.zone,
                "face_down": c.face_down}
    if zone in PUBLIC_ZONES or c.zone == STACK:
        # physical markers on the table are public, even on a face-down card
        if c.effects:
            view["effects"] = [e.model_dump(exclude_none=True) for e in c.effects]
        if c.damage:
            view["damage"] = c.damage
        if c.stack_info is not None:
            view["stack_info"] = c.stack_info.model_dump()
        if c.exile_group and not view.get("hidden"):
            view["exile_group"] = c.exile_group
        if c.choices and not view.get("hidden"):
            view["choices"] = dict(c.choices)
    if c.test_object and not view.get("hidden"):
        view["test_object"] = True
    if c.stickers101 and c.zone.split(':')[-1] in ('battlefield', 'graveyard', 'exile', 'command', 'stack', 'phased'):
        view['stickers101'] = [s.model_dump() for s in c.stickers101]
    if c.token_source is not None and not view.get("hidden"):
        # "Created by Mischievous Mystic" is public (everyone saw it happen), but which card made it is shown only while the viewer can
        # see that card: once the source is back in its owner's hand or library, its id would pick it out among the hidden cards
        source = state.cards.get(c.token_source.source_id or "")
        if source is not None and can_see(state, source, viewer):
            view["token_source"] = c.token_source.model_dump()
        else:
            view["token_source"] = {"source_id": None, "name": c.token_source.name, "object_id": None}
    if c.face_down and c.face_down_kind:
        view["face_down_kind"] = c.face_down_kind  # public: everyone saw how it got face down
        if c.face_down_as:
            view["face_down_as"] = c.face_down_as  # -- review (sys 18A) -- 708.2a: what it is face down ("Forest land") is public
    if c.protected:
        view["protected"] = True
    if zone in PUBLIC_ZONES:
        # Position, tapped state, counters and combat roles are public even for face-down cards.
        view.update(x=c.x, y=c.y, tapped=c.tapped, flipped=c.flipped)
        if c.rotation:
            view["rotation"] = c.rotation
        if c.locked:
            view["locked"] = True
        if c.attached_to:
            view["attached_to"] = c.attached_to
        if c.attached_player:
            view["attached_player"] = c.attached_player
        if c.group:
            view["group"] = c.group
        if c.quantity != 1:
            view["quantity"] = c.quantity
        if c.counters:
            view["counters"] = dict(c.counters)
        if c.attacking_without_target is not None:
            view["attacking_without_target"] = c.attacking_without_target
        if c.attacking:
            view["attacking"] = c.attacking.model_dump()
        if c.blocking_without_attacker:
            view["blocking_without_attacker"] = True
        if c.blocking:
            view["blocking"] = c.blocking
            if c.blocking_more:
                view["blocking_more"] = list(c.blocking_more)
    return view


def _render_part(part: LogPart, viewer: str) -> dict[str, Any] | list[dict[str, Any]]:
    if part.group is not None:
        names = []
        hidden = 0
        for p in part.group:
            if _sees(p, viewer):
                names.append({"card": {"name": p.name, "card_id": p.card_id}})
            else:
                hidden += 1
        return {"group": names, "hidden": hidden}
    if part.t is not None:
        return {"t": part.t}
    if _sees(part, viewer):
        return {"card": {"name": part.name, "card_id": part.card_id}}
    return {"group": [], "hidden": 1}


def _sees(part: LogPart, viewer: str) -> bool:
    return viewer == OMNISCIENT or ALL in part.visible_to or viewer in part.visible_to


DRAWN_SHOWN = 20  # -- table toys -- the latest chits drawn from the draw bag a view lists


def bag_view(state: GameState, viewer: str) -> dict[str, Any]:
    """-- table toys -- what ``viewer`` sees of the draw bag (app/game/handlers/toys.py): how many chits are inside, never which
    nor their order, and the latest drawn ones, a hidden one only to its drawer (and the hot-seat table's open view)."""
    bag = state.bag
    return {
        "count": len(bag.chits),
        "drawn": [{"player": d.player, "chit": d.chit if d.shown or viewer in (d.player, OMNISCIENT) else None, "shown": d.shown}
                  for d in bag.drawn[-DRAWN_SHOWN:]],
        "drawn_count": len(bag.drawn),
    }


def render_log(entries: list[LogEntry], viewer: str) -> list[dict[str, Any]]:
    return [
        {
            "seq": e.seq,
            "ts": e.ts,
            "turn": e.turn,
            "phase": e.phase,
            "actor": e.actor,
            "kind": e.kind,
            "parts": [_render_part(p, viewer) for p in e.parts],
            **({"manual": True} if e.manual else {}),
            **({"folded": True} if e.folded else {}),
            **({"roll": e.roll.model_dump(exclude={"cannon"} if e.roll.cannon is None else None)} if e.roll else {}),  # (a plain roll: as before)
            **({"dig": e.dig.model_dump()} if e.dig else {}),
            # -- table toys -- a draw from the draw bag: a hidden chit only for its drawer (and the hot-seat open view)
            **({"bag": {"player": e.bag.player, "hidden": e.bag.hidden, "left": e.bag.left,
                        "chit": e.bag.chit if not e.bag.hidden or viewer in (e.bag.player, OMNISCIENT) else None}} if e.bag else {}),
        }
        for e in entries
    ]


def build_view(
    state: GameState,
    viewer: str,
    *,
    log_limit: int = 250,
    extra_log: list[LogEntry] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if viewer not in state.players and viewer not in (SPECTATOR, OMNISCIENT):
        raise ValueError(f"unknown viewer {viewer}")
    cards: dict[str, dict[str, Any]] = {}
    zones: dict[str, Any] = {}
    for key, ids in state.zones.items():
        owner, zone = split_zone(key)
        if zone in ("library", "attractions"):  # (wave 100L: an Attraction deck is face down too, 717.2)
            # Libraries: a count plus only the cards this viewer can see right now (with positions).
            known = []
            for index, cid in enumerate(ids):
                c = state.cards[cid]
                if can_see(state, c, viewer):
                    known.append([index, cid])
                    cards[cid] = card_view(state, c, viewer)
            zones[key] = {"count": len(ids), "known": known, **({"shuffles": state.shuffles[key]} if state.shuffles.get(key) else {})}
        elif zone in OWNER_VISIBLE_ZONES:
            # Hands etc.: visible cards keep their ids; every hidden card becomes an anonymous
            # placeholder in a keyed-hash order, so nothing links it to a card seen earlier.
            visible = [cid for cid in ids if can_see(state, state.cards[cid], viewer)]
            hidden = hidden_order(state, [cid for cid in ids if cid not in set(visible)])
            listed = list(visible)
            for cid in visible:
                cards[cid] = card_view(state, state.cards[cid], viewer)
            for index, _cid in enumerate(hidden):
                pid = placeholder_id(key, index)
                listed.append(pid)
                cards[pid] = {"id": pid, "hidden": True, "owner": owner, "controller": owner, "zone": key, "face_down": False}
            zones[key] = listed
        else:
            zones[key] = list(ids)
            for cid in ids:
                cards[cid] = card_view(state, state.cards[cid], viewer)

    commanders: dict[str, list[dict[str, Any]]] = {pid: [] for pid in state.seat_order}
    for c in state.cards.values():
        if c.commander_key:
            commanders[c.owner].append(
                {"key": c.commander_key, "name": c.name, "card_id": c.card_id, "instance_id": c.id if can_see(state, c, viewer) else None,
                 # -- review (sys 18A) -- 708.5: a face-down commander the viewer can't look at (manifested from a library, cast
                 # face down from a hand) isn't located for them: its zone would say which face-down permanent it is
                 # (soak: nor one in a hand or library they can't see: its zone would say when it is drawn, searched for or put back, 400.2)
                 "zone": c.zone if can_see(state, c, viewer) else None,
                 "tax": state.players[c.owner].commander_tax.get(c.commander_key, 0),
                 "casts": state.players[c.owner].commander_casts.get(c.commander_key, 0)}
            )

    players = []
    for pid in state.seat_order:
        p = state.players[pid]
        own = viewer in (pid, OMNISCIENT)
        exclude = set() if own else {"token_shortcuts", "deck_id"}
        if not own and state.settings.deck_privacy == "private":
            exclude.add("deck_name")
        data = p.model_dump(exclude=exclude)
        if viewer != OMNISCIENT:
            for unit in data['mana_units']:  # (where a source was when it made mana can name a hidden zone)
                unit.pop('production_zone', None)  # -- review 18B -- whether a source's mana is remembered depends on every card of the game, hidden
            # ones too (mana_units.tracking): mana with no restriction and no rider shows as plain mana, units renumbered, no counter
            data.pop("mana_seq", None)
            visible_units: list[dict[str, Any]] = []
            for u in data["mana_units"]:
                if not u["only"] and not u["riders"] and u.get('generic_allowed', True):
                    data["mana"][u["sym"]] = data["mana"].get(u["sym"], 0) + 1
                else:
                    visible_units.append({**u, "id": len(visible_units)})
            data["mana_units"] = visible_units
        data["commanders"] = sorted(commanders[pid], key=lambda x: x["key"])
        data["hand_count"] = len(state.zones.get(f"{pid}:hand", []))
        data["library_count"] = len(state.zones.get(f"{pid}:library", []))
        players.append(data)

    log = list(state.log)
    if extra_log:
        log = sorted(log + extra_log, key=lambda e: (e.ts, e.seq))
    return {
        "view_version": VIEW_VERSION,
        "game": {
            "id": state.id,
            "name": state.name,
            "format": state.format,
            "seq": state.seq,
            "settings": state.settings.model_dump(),
            **(meta or {}),
        },
        "viewer": viewer,
        "players": players,
        "seat_order": list(state.seat_order),
        "turn": state.turn.model_dump(exclude={'starting_life'}),
        "table": state.table.model_dump(),
        # Who is searching what is public ("X is searching their library"); contents are not.
        "searches": {v.viewer: v.zone for v in state.views if v.kind == "search"},
        "my_views": [v.model_dump() for v in state.views if v.viewer == viewer],
        # Public: who is still deciding, mulligan counts, how many cards someone must bottom.
        "arrows": [ar.model_dump() for ar in state.arrows],
        "pregame": state.pregame.model_dump() if state.pregame and not state.pregame.finished else None,
        # Public: the open "anything in response?" check (its pending intent is only described).
        "response": state.response.model_dump(exclude={"intent"}) | {"has_intent": state.response.intent is not None}
        if state.response else None,
        "auto_pass": sorted(p for p, t in state.auto_pass.items() if t == state.turn.number),
        "cards": cards,
        "zones": zones,
        "stack": list(state.zones.get(STACK, [])),
        "log": render_log(log[-log_limit:], viewer),
        "bag": bag_view(state, viewer),  # -- table toys -- how many chits, and the drawn ones this viewer may see
    }
