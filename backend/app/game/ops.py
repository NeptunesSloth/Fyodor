"""Primitive state operations shared by the action handlers."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from app.game.errors import ActionError
from app.game.state import (
    ALL,
    HIDDEN_ZONES,
    STACK,
    Arrow,
    CardInstance,
    GameState,
    LogEntry,
    LogPart,
    MergedPart,
    PlayerState,
    split_zone,
    zone_key,
)
from app.game.visibility import publicly_visible, seers

LOG_LIMIT = 2000


def shown(state: GameState, text: str) -> str:
    """-- granted from object (wave 18F) -- an ability's text as people read it: the ‹granter#object› a static grant bound
    (rules/granted.py) is the granting object's name (a face-down one: "it", nothing about it leaks)."""
    def name(m: re.Match[str]) -> str:
        c = state.cards.get((m["oid"] or "").rsplit(".", 1)[0])
        return c.name if c is not None and not c.face_down and c.name else "it"

    return re.sub(r"‹granter(?:#(?P<oid>[^›]+))?›", name, text) if "‹" in text else text


def card(state: GameState, card_id: str) -> CardInstance:
    found = state.cards.get(card_id)
    if found is None:
        raise ActionError(f"Card {card_id} is not in this game")
    return found


def cards(state: GameState, card_ids: Iterable[str]) -> list[CardInstance]:
    seen: set[str] = set()
    out = []
    for cid in card_ids:
        if cid in seen:
            continue
        seen.add(cid)
        out.append(card(state, cid))
    return out


def player(state: GameState, player_id: str | None, default: str) -> str:
    pid = player_id or default
    if pid not in state.players or state.players[pid].left:
        raise ActionError(f"Unknown player {pid}")
    return pid


def zone_name(key: str) -> str:
    return split_zone(key)[1]


def remove_from_zone(state: GameState, c: CardInstance) -> int:
    ids = state.zone(c.zone)
    try:
        index = ids.index(c.id)
    except ValueError:
        raise ActionError(f"Card {c.id} is missing from zone {c.zone}") from None
    ids.pop(index)
    return index


def insert(state: GameState, c: CardInstance, key: str, *, index: int | None = None, position: str | None = None) -> None:
    ids = state.zone(key)
    library = zone_name(key) == "library"
    if index is not None:
        ids.insert(max(0, min(index, len(ids))), c.id)
    elif position == "bottom":
        ids.append(c.id) if library else ids.insert(0, c.id)
    else:  # top (default)
        ids.insert(0, c.id) if library else ids.append(c.id)
    c.zone = key


def is_ephemeral(c: CardInstance) -> bool:
    """Tokens, copies and ability objects only exist on the battlefield / stack."""
    return c.is_token or c.ability is not None


def delete(state: GameState, c: CardInstance) -> None:
    remove_from_zone(state, c)
    del state.cards[c.id]
    for other in state.cards.values():
        if other.attached_to == c.id:
            other.attached_to = None
            other.attach_offset = None
        if other.blocks(c.id):
            other.unblock(c.id)
        if other.attacking and other.attacking.kind == "card" and other.attacking.id == c.id:
            other.attacking = None


def move_card(
    state: GameState,
    c: CardInstance,
    dest: str,
    *,
    index: int | None = None,
    position: str | None = None,
    x: float | None = None,
    y: float | None = None,
    face_down: bool | None = None,
    rest: str | None = None,
) -> bool:
    """Move a card between zones, carrying knowledge along. Returns False if it ceased to exist."""
    source = c.zone
    src_zone, dst_zone = zone_name(source), zone_name(dest)
    if c.merged and src_zone in ("battlefield", "phased") and dst_zone not in ("battlefield", "phased", STACK) and source != dest:
        # -- merged permanents (wave 18D) -- 730.3, 712.21: one permanent leaves, each of its cards goes to the zone
        from app.game import merging

        parts, pick = merging.break_up(state, c, dest)
        moved = move_card(state, c, dest, index=index, position=position, x=x, y=y, face_down=face_down)
        merging.place(state, parts, pick, dest, rest, index, position)
        return moved
    if dest != STACK:
        owner, _ = split_zone(dest)
        if owner not in state.players:
            raise ActionError(f"Unknown zone {dest}")

    if source == dest:
        # reorder within a zone / reposition
        remove_from_zone(state, c)
        insert(state, c, dest, index=index, position=position)
        if dst_zone == "battlefield" and x is not None and y is not None:
            c.x, c.y = x, y
        if face_down is not None:
            c.face_down = face_down
            if not face_down:
                c.face_down_kind = c.face_down_as = None
        return True

    # (-- review (wave 14R) -- a phased-out permanent changing controller, 702.26d: the same object, as on the battlefield)
    same_object = src_zone == dst_zone and src_zone in ("battlefield", "phased")
    if is_ephemeral(c) and dst_zone not in ("battlefield", "phased", STACK):
        state.departures()[c.id] = dest  # it went there, then ceased to exist (rules tracking)
        delete(state, c)
        return False

    remove_from_zone(state, c)
    insert(state, c, dest, index=index, position=position)
    if src_zone == "battlefield" and dst_zone != "battlefield":
        c.attached_to = None
        c.attached_player = None
        c.attach_offset = None
        c.group = None
        c.locked = False
        c.rotation = 0.0
        for other in state.cards.values():
            if other.attached_to == c.id:  # equipment/auras stay where they are, unattached
                other.attached_to = None
                other.attach_offset = None
    elif src_zone == "battlefield" and dst_zone == "battlefield" and c.attached_to:
        host = state.cards.get(c.attached_to)
        if host is None or host.zone != dest:
            c.attached_to = None
            c.attach_offset = None

    if same_object:
        # A control change (another player's battlefield) is not a zone change: the permanent
        # stays the same object with its damage, counters and tapped state. It leaves combat.
        c.attacking = None
        c.unblock()
        for other in state.cards.values():
            if other.blocks(c.id):
                other.unblock(c.id)
            if other.attacking and other.attacking.kind == "card" and other.attacking.id == c.id:
                other.attacking = None
    else:
        # A card that changes zones becomes a new object: manual markers don't follow it.
        c.effects = []
        c.damage = 0
        c.choices = {}
        if src_zone == STACK or dst_zone == STACK:
            c.stack_info = None
        if dst_zone not in ("exile", "foretell"):
            c.exile_group = None
        if src_zone == "battlefield" or dst_zone == "battlefield":
            c.tapped = False
            c.attacking = None
            c.unblock()
            c.flipped = False
            if src_zone == "battlefield":
                c.counters = {}
                for other in state.cards.values():
                    if other.blocks(c.id):
                        other.unblock(c.id)
                    if other.attacking and other.attacking.kind == "card" and other.attacking.id == c.id:
                        other.attacking = None
        if src_zone not in ("battlefield", "phased"):  # (review 24C) 122.2: counters never follow a card to another zone either
            c.counters = {}  # (time counters on a commander that went from exile to the command zone, 903.9a; a suspended card returned to the hand)
    if dst_zone in HIDDEN_ZONES or src_zone in HIDDEN_ZONES or (src_zone == "battlefield" and dst_zone != "battlefield"):
        c.face = 0  # (-- transform, wave 11A -- 712.8a: off the battlefield and the stack a double-faced card shows its front face)
    c.revealed_to = []  # a reveal ends when the card changes zones
    c.unseen = False
    if face_down is not None:
        c.face_down = bool(face_down)
    elif not same_object:
        c.face_down = False  # (a control change keeps a face-down permanent face down)
    if not c.face_down:
        c.face_down_kind = c.face_down_as = None
    if dst_zone == "battlefield":
        c.controller = split_zone(dest)[0] or c.controller
        if x is not None and y is not None:
            c.x, c.y = x, y
    elif dst_zone != STACK:
        c.controller = c.owner if dst_zone != "battlefield" else c.controller

    return True


def card_part(state: GameState, c: CardInstance, extra: set[str] | None = None) -> LogPart:
    who = seers(state, c) | (extra or set())
    return LogPart(name=c.name, card_id=c.card_id, visible_to=[ALL] if ALL in who else sorted(who))


def text(t: str) -> LogPart:
    return LogPart(t=t)


def pname(state: GameState, player_id: str | None) -> LogPart:
    if player_id is None:
        return LogPart(t="nobody")
    return LogPart(t=state.players[player_id].name if player_id in state.players else player_id)


def log(state: GameState, actor: str | None, ts: float, parts: list[LogPart], kind: str = "action") -> None:
    state.log.append(
        LogEntry(seq=state.seq, ts=ts, turn=state.turn.number, phase=state.turn.phase, actor=actor, parts=parts, kind=kind)
    )
    if len(state.log) > LOG_LIMIT:
        del state.log[: len(state.log) - LOG_LIMIT]


def zone_label(state: GameState, key: str, actor: str | None = None) -> str:
    owner, zone = split_zone(key)
    if key == STACK:
        return "the stack"
    nice = {"command": "command zone", "foretell": "foretell exile"}.get(zone, zone)
    if owner == actor:
        return f"their {nice}"
    return f"{state.players[owner].name}'s {nice}" if owner in state.players else nice


def group(state: GameState, moved: list[CardInstance], extra: dict[str, set[str]] | None = None) -> LogPart:
    """A per-viewer card list: names the viewer may know, a count for the rest."""
    extra = extra or {}
    return LogPart(group=[card_part(state, c, extra.get(c.id)) for c in moved])


def visible_to_all_players(state: GameState, c: CardInstance) -> bool:
    return publicly_visible(state, c)


def library_key(state: GameState, player_id: str) -> str:
    return zone_key(player_id, "library")


# -- review (face-down ids) -- 406.3, 708.5: a card that becomes face down in a zone others can see is a new, unlinkable object
def down_public(c: CardInstance) -> bool:
    """A face-down card in a zone other players see (battlefield, exile, stack): they must not know which card it is."""
    return c.face_down and c.ability is None and zone_name(c.zone) in ("battlefield", "exile", STACK)


def needs_fresh_id(source: str, first: str, was_down: bool, c: CardInstance) -> bool:
    """Did ``c`` come to be face down somewhere others see it, having gone from ``source`` to ``first`` (the zones of its first move)?
    Not a control change, nor a face-down object that goes on (its spell resolving): they already know it as the same object. But
    708.9: a face-down permanent or spell that leaves the battlefield or stack is revealed, so going face down again is a card they
    have seen."""
    return down_public(c) and seen_move(source, first, was_down)


def seen_move(source: str, dest: str, was_down: bool) -> bool:
    """A move after which the card is no longer the face-down object others knew (``was_down``: it was one, see needs_fresh_id)."""
    src, dst = zone_name(source), zone_name(dest)
    return src != dst and (not was_down or (src in ("battlefield", STACK) and dst != "battlefield"))


# Never rewritten: what players type (a note, a counter's or an effect's name, a token's text, an arrow's label, a player's name: a
# player could write the old id there and read the new one back), and what speaks of the card as it was (400.7: the source of a copy,
# of a token, of an ability on the stack or of mana in a pool is that old object; following it to the face-down card would name it)
_KEEP: dict[type, frozenset[str]] = {
    CardInstance: frozenset({"name", "note", "counters", "effects", "choices", "stack_info", "exile_group", "face_down_as", "token",
                             "token_source", "copy_of", "ability"}),
    MergedPart: frozenset({"name", "token", "copy_of"}),
    Arrow: frozenset({"label"}),
    PlayerState: frozenset({"name", "deck_name", "resources", "mana_units"}),
}


def renumber(state: GameState, ids: Iterable[str]) -> dict[str, str]:
    """Give each of these cards a new instance id and rewrite every reference to the old one (attachments, combat, views, arrows,
    and everything the rules state remembers: exiled-with links, delayed triggers, decisions in flight, permissions, object ids).
    The new ids come from the game's secret salt and the old id: unpredictable to players, the same on replay (the compile and the
    apply). A renamed card goes to the end of the table's card order, like any new object (no position to match it by)."""
    mapping: dict[str, str] = {}
    key = state.hidden_salt.encode()[:64] or b"fyodor"
    for old in dict.fromkeys(ids):
        if old not in state.cards:
            continue
        n = 0
        while True:
            new = hashlib.blake2b(f"{old}:{n}".encode(), key=key, digest_size=6).hexdigest()
            if new not in state.cards and new not in mapping.values():
                break
            n += 1
        mapping[old] = new
    if not mapping:
        return mapping
    for field in ("cards", "zones", "views", "arrows", "response", "table", "players", "rules", "auto_pass", "pregame", "turn"):
        rewrite(getattr(state, field), mapping)
    for new in mapping.values():
        state.cards[new] = state.cards.pop(new)
    state.renames().update(mapping)
    return mapping


def rewrite(v: Any, mapping: dict[str, str]) -> Any:
    """``v`` with each card id of ``mapping`` replaced (in place where it can be), also inside an object id ("<card>.<n>") or a
    ‹granter#<card>.<n>› token; never inside a longer word."""
    pattern = re.compile(r"(?<![0-9A-Za-z_])(" + "|".join(re.escape(o) for o in mapping) + r")(?![0-9A-Za-z_])")

    def sub(v: Any) -> Any:
        if isinstance(v, str):
            return pattern.sub(lambda m: mapping[m.group(1)], v) if pattern.search(v) else v
        if isinstance(v, dict):
            items = [(sub(k), sub(x)) for k, x in v.items()]
            v.clear()
            v.update(items)
        elif isinstance(v, list):
            v[:] = [sub(x) for x in v]
        elif isinstance(v, tuple):
            return tuple(sub(x) for x in v)
        elif isinstance(v, set):
            return {sub(x) for x in v}
        elif isinstance(v, BaseModel):
            keep = _KEEP.get(type(v), frozenset())
            for field, x in v.__dict__.items():
                if field not in keep:
                    v.__dict__[field] = sub(x)
        return v

    return sub(v)
