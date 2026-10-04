"""Zone, library and hidden-information actions."""

from __future__ import annotations

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.handlers import objects, response
from app.game.ops import group, log, pname, text, zone_label
from app.game.rules_state import emit
from app.game.state import ALL, STACK, CardInstance, GameState, ViewContext, split_zone, zone_key
from app.game.visibility import seers

OWNER_DEFAULT_ZONES = {"library", "hand", "graveyard", "exile", "command", "sideboard", "companion", "foretell", "setaside"}


def destination(state: GameState, ref: A.ZoneRef, card: CardInstance, actor: str) -> str:
    if ref.zone == STACK:
        return STACK
    if ref.player is not None:
        ops.player(state, ref.player, actor)
        return zone_key(ref.player, ref.zone)
    default = card.owner if ref.zone in OWNER_DEFAULT_ZONES else actor
    return zone_key(default, ref.zone)


def _verb(src: str, dst: str, position: str | None) -> str:
    s, d = ops.zone_name(src), ops.zone_name(dst)
    if s == "hand" and d == "battlefield":
        return "played"
    if s == "hand" and d == STACK:
        return "cast"
    if s == "command" and d == STACK:
        return "cast"
    if s == "hand" and d == "graveyard":
        return "discarded"
    if d == "library":
        return f"put on the {position or 'top'} of"
    return "moved"


def move(state: GameState, a: A.Move) -> None:
    moving = ops.cards(state, a.card_ids)
    for c in moving:
        if c.locked:
            raise ActionError(f"{c.name or 'That card'} is locked — unlock it first")
    dests = [destination(state, a.to.model_copy(update={"player": a.controllers[c.id]})
                         if a.controllers and c.id in a.controllers and a.to.zone == "battlefield" else a.to, c, a.actor)
             for c in moving]
    tapped = set(a.tapped_ids or ())
    positions = a.r.positions if a.r else {}
    who_saw = {c.id: seers(state, c) for c in moving}
    sources = {c.id: c.zone for c in moving}
    for c, dest in zip(moving, dests, strict=True):  # -- keyword actions & face-down (wave 3F) --
        # 708.9: a face-down permanent leaving the battlefield, or a face-down spell leaving the stack
        # other than for the battlefield, is revealed to all players as it moves (the log names it to all)
        # (-- review (sys 18A) -- even when it goes on face down, e.g. into a face-down pile: 708.9 has no exception)
        if c.face_down and (c.zone.endswith(":battlefield") and not dest.endswith(":battlefield")
                                                or c.zone == STACK and not dest.endswith(":battlefield")):
            who_saw[c.id] = {ALL}
    commander_casts: list[CardInstance] = []

    for i, (c, dest) in enumerate(zip(moving, dests, strict=True)):
        lib_top = ops.zone_name(dest) == "library" and a.position != "bottom"
        index = a.index + i if a.index is not None else (i if lib_top else None)
        x = y = None
        if ops.zone_name(dest) == "battlefield":
            if c.id in positions:
                x, y = positions[c.id]
            elif a.x is not None and a.y is not None:
                x, y = a.x + i * 18, a.y + i * 18
        if c.zone.endswith(":command") and dest == STACK and c.commander_key:
            commander_casts.append(c)
        ops.move_card(state, c, dest, index=index, position=a.position, x=x, y=y, face_down=a.face_down)
        if dest == STACK and sources[c.id] != STACK and a.actor in state.players:
            c.controller = a.actor  # -- refused look/cast-free (wave 3R5) -- 601.2a: the player who casts a spell controls it
        if (a.tapped or c.id in tapped) and ops.zone_name(dest) == "battlefield" and c.id in state.cards:
            c.tapped = True
        if a.back_ids and c.id in a.back_ids and ops.zone_name(dest) == "battlefield" and c.id in state.cards:
            c.face = 1  # -- transform (wave 11A) -- 712.14a
        if c.face_down and a.face_down:
            c.face_down_kind = a.face_down_kind or ("exile" if ops.zone_name(dest) == "exile" else "generic")
            c.face_down_as = a.face_down_as  # (-- hidden exile (wave 18A) -- 708.2a)
            if ops.zone_name(dest) == "exile" and a.actor in state.players and a.actor != c.owner:
                # -- as long as (wave 9B) -- 406.3: a card another player exiles face down is looked at by the one who exiled
                # it (Gonti, Thief of Sanity), not by its owner: the face-down rule shows an exiled card to its "controller"
                c.controller = a.actor

    for c in commander_casts:
        caster = state.players[c.owner]
        caster.commander_casts[c.commander_key or ""] = caster.commander_casts.get(c.commander_key or "", 0) + 1
        if state.settings.auto_commander_tax:
            owner = state.players[c.owner]
            owner.commander_tax[c.commander_key or ""] = owner.commander_tax.get(c.commander_key or "", 0) + 2

    # One log line per (source zone, destination) pair keeps multi-card moves readable.
    by_route: dict[tuple[str, str], list[CardInstance]] = {}
    for c, dest in zip(moving, dests, strict=True):
        by_route.setdefault((sources[c.id], dest), []).append(c)
    for (src, dest), group_cards in by_route.items():
        if src == dest and ops.zone_name(dest) != "library":
            continue  # reordering within hand / battlefield is not worth a log line
        verb = _verb(src, dest, a.position)
        parts = [pname(state, a.actor), text(f" {verb} "), group(state, group_cards, who_saw)]
        if verb in ("played", "cast", "discarded"):
            if split_zone(src)[0] != a.actor:
                parts.append(text(f" from {zone_label(state, src, a.actor)}"))
        elif verb.startswith("put on"):
            parts.append(text(f" {zone_label(state, dest, a.actor)}"))
        else:
            parts += [text(f" from {zone_label(state, src, a.actor)} to {zone_label(state, dest, a.actor)}")]
        if a.face_down:
            parts.append(text(" face down"))
        log(state, a.actor, a.ts, parts)
    for c in commander_casts:
        tax = state.players[c.owner].commander_tax.get(c.commander_key or "", 0)
        log(state, a.actor, a.ts, [text(f"Commander tax for {c.name} is now {tax}.")], kind="info")
    cast = [c for c, dest in zip(moving, dests, strict=True) if dest == STACK and sources[c.id] != STACK]
    if cast:
        names = ", ".join("a face-down spell" if c.face_down else c.name for c in cast)
        response.on_stack_add(state, a.actor, f"cast {names}")


def set_position(state: GameState, a: A.SetPosition) -> None:
    targets = [(ops.card(state, cid), x, y) for cid, x, y in a.moves]
    for c, _x, _y in targets:
        if ops.zone_name(c.zone) != "battlefield":
            raise ActionError(f"{c.id} is not on the battlefield")
        if c.locked:
            raise ActionError(f"{c.name or 'That card'} is locked — unlock it first")
    explicit = {c.id for c, _x, _y in targets}
    for c, x, y in targets:
        dx, dy = x - c.x, y - c.y
        c.x, c.y = x, y
        if c.attached_to and c.attached_to not in explicit:
            host = state.cards.get(c.attached_to)
            if host is not None:  # dragging an attachment re-seats it relative to its host
                c.attach_offset = (c.x - host.x, c.y - host.y)
        ids = state.zone(c.zone)
        ids.remove(c.id)
        ids.append(c.id)  # bring to front
        if a.with_attachments:
            for child in objects.children_of(state, c.id):
                if child.id in explicit or child.zone != c.zone:
                    continue
                child.x += dx
                child.y += dy
        # attachments are drawn tucked underneath their host
        for child in objects.children_of(state, c.id):
            if child.zone == c.zone and child.id in ids:
                ids.remove(child.id)
                ids.insert(ids.index(c.id), child.id)


def draw_cards(state: GameState, pid: str, count: int) -> list[CardInstance]:
    lib = state.zone(zone_key(pid, "library"))
    if not lib:
        raise ActionError(f"{state.players[pid].name}'s library is empty")
    drawn = [state.cards[cid] for cid in lib[:count]]
    for c in drawn:
        ops.move_card(state, c, zone_key(pid, "hand"))
        emit(state, "drew", player=pid, card=c.id)  # 121.2: each card is its own draw
    return drawn


def draw(state: GameState, a: A.Draw) -> None:
    pid = ops.player(state, a.player, a.actor)
    drawn = draw_cards(state, pid, a.count)
    n = len(drawn)
    parts = [pname(state, pid), text(" drew " + ("a card" if n == 1 else f"{n} cards"))]
    if n < a.count:
        parts.append(text(f" (library ran out after {n})"))
    log(state, a.actor, a.ts, parts)


def rekey_zone(state: GameState, key: str, perm: list[int], new_ids: list[str], only: list[str] | None = None) -> None:
    """Reorder a zone and give its cards fresh ids so their identities cannot be tracked. ``only``: just these cards of the zone,
    among their own places, and they stay face down (-- review (sys 18A) -- a face-down pile that is shuffled, 406.3)."""
    zone = state.zone(key)
    slots = [i for i, cid in enumerate(zone) if only is None or cid in only]
    if only is not None and len(slots) != len(set(only)):
        raise ActionError("Shuffle data does not match the zone (state changed?)")
    old = [zone[i] for i in slots]
    if sorted(perm) != list(range(len(old))) or len(new_ids) != len(old):
        raise ActionError("Shuffle data does not match the zone (state changed?)")
    reordered = [state.cards[old[i]] for i in perm]
    renamed: dict[str, str] = {}
    for c, new_id in zip(reordered, new_ids, strict=True):
        if new_id in state.cards and new_id not in old:
            raise ActionError("id collision while shuffling")
        renamed[c.id] = new_id
    for c in reordered:
        del state.cards[c.id]
    for c, new_id in zip(reordered, new_ids, strict=True):
        c.id = new_id
        c.revealed_to = []
        if only is None:
            c.face_down = False
            c.face_down_kind = None
        else:
            c.unseen = c.face_down  # 406.3: nobody may look at a shuffled face-down pile any more
        state.cards[new_id] = c
    for i, new_id in zip(slots, new_ids, strict=True):
        zone[i] = new_id
    # Shuffling invalidates every positional view of the zone.
    state.views = [v for v in state.views if v.zone != key]
    for other in state.cards.values():
        if other.copy_of and other.copy_of.source_id in renamed:
            other.copy_of.source_id = renamed[other.copy_of.source_id]


def shuffle(state: GameState, a: A.Shuffle) -> None:
    pid = ops.player(state, a.player, a.actor)
    if a.r is None:
        raise ActionError("unresolved shuffle")
    key = zone_key(pid, a.zone)
    rekey_zone(state, key, a.r.perm, a.r.new_ids, a.card_ids)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" shuffled {zone_label(state, key, a.actor)}")])


def mill(state: GameState, a: A.Mill) -> None:
    pid = ops.player(state, a.player, a.actor)
    lib = state.zone(zone_key(pid, "library"))
    if not lib:
        raise ActionError(f"{state.players[pid].name}'s library is empty")
    milled = [state.cards[cid] for cid in lib[: a.count]]
    dest = zone_key(pid, a.to)
    for c in milled:
        ops.move_card(state, c, dest, face_down=a.face_down if a.to == "exile" else None)
        if c.face_down:
            c.face_down_kind = "exile"
            c.unseen = a.blind  # (-- hidden exile (wave 18A) --)
        if a.to == "graveyard" and c.zone == dest:  # -- triggers (wave 17D) -- 701.17a (not a card a replacement sent elsewhere)
            emit(state, "milled", card=c.id, player=pid)
    verb = "milled" if a.to == "graveyard" else ("exiled face down" if a.face_down else "exiled")
    log(state, a.actor, a.ts, [pname(state, pid), text(f" {verb} "), group(state, milled)])


def put_top_face_down(state: GameState, a: A.PutTopFaceDown) -> None:
    pid = ops.player(state, a.player, a.actor)
    lib = state.zone(zone_key(pid, "library"))
    if not lib:
        raise ActionError(f"{state.players[pid].name}'s library is empty")
    cards_ = [state.cards[cid] for cid in lib[: a.count]]
    positions = a.r.positions if a.r else {}
    dest = zone_key(a.actor, "battlefield")
    for i, c in enumerate(cards_):
        x, y = positions.get(c.id, (80 + i * 22, 80 + i * 22))
        ops.move_card(state, c, dest, x=x, y=y, face_down=True)
        c.face_down_kind = a.kind
    what = {"manifest": "manifested", "cloak": "cloaked", "generic": "put face down"}[a.kind]
    n = len(cards_)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" {what} the top {'card' if n == 1 else f'{n} cards'} of "),
                                pname(state, pid), text("'s library")])


def mulligan(state: GameState, a: A.Mulligan) -> None:
    pid = ops.player(state, a.player, a.actor)
    if a.r is None:
        raise ActionError("unresolved mulligan")
    hand = list(state.zone(zone_key(pid, "hand")))
    lib_key = zone_key(pid, "library")
    for cid in hand:
        ops.move_card(state, state.cards[cid], lib_key, position="bottom")
    rekey_zone(state, lib_key, a.r.perm, a.r.new_ids)
    state.players[pid].mulligans += 1
    n = state.players[pid].mulligans
    if a.draw:
        draw_cards(state, pid, a.draw)
    log(
        state,
        a.actor,
        a.ts,
        [pname(state, pid), text(f" took a mulligan (#{n}), shuffled and drew {a.draw}. Put {n} on the bottom (London).")],
    )


def reveal(state: GameState, a: A.Reveal) -> None:
    targets = ops.cards(state, a.card_ids)
    if a.to:
        for p in a.to:
            ops.player(state, p, a.actor)
    before = {c.id: seers(state, c) for c in targets}
    for c in targets:
        if a.to is None:
            c.revealed_to = [ALL]
        elif ALL not in c.revealed_to:
            c.revealed_to = sorted(set(c.revealed_to) | set(a.to))
    audience = "everyone" if a.to is None else ", ".join(state.players[p].name for p in a.to)
    extra = {c.id: before[c.id] | ({ALL} if a.to is None else set(a.to)) for c in targets}
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" revealed "), group(state, targets, extra), text(f" to {audience}")])


def hide(state: GameState, a: A.Hide) -> None:
    """End a reveal: the cards become anonymous again for everyone who can't normally see them."""
    targets = ops.cards(state, a.card_ids)
    for c in targets:
        c.revealed_to = []
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" stopped revealing {len(targets)} card{'s' if len(targets) != 1 else ''}")],
        kind="minor")


def _open_view(state: GameState, viewer: str, zone: str, kind: str, card_ids: list[str], view_id: str) -> None:
    state.views = [v for v in state.views if not (v.viewer == viewer and v.zone == zone)]
    state.views.append(ViewContext(id=view_id, viewer=viewer, zone=zone, kind=kind, card_ids=card_ids))  # type: ignore[arg-type]


def look_top(state: GameState, a: A.LookTop) -> None:
    """Privately look at the top N cards. Only the looker sees them, until the view is closed."""
    pid = ops.player(state, a.player, a.actor)
    key = zone_key(pid, "library")
    top = state.zone(key)[: a.count]
    _open_view(state, a.actor, key, "look", list(top), f"look-{state.seq}")
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" looked at the top {len(top)} of {zone_label(state, key, a.actor)}")])


def reveal_top(state: GameState, a: A.RevealTop) -> None:
    pid = ops.player(state, a.player, a.actor)
    key = zone_key(pid, "library")
    top = [state.cards[cid] for cid in state.zone(key)[: a.count]]
    for c in top:
        c.revealed_to = [ALL]
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" revealed the top of {zone_label(state, key, a.actor)}: "), group(state, top)])


def search_start(state: GameState, a: A.SearchStart) -> None:
    if a.zone.zone == STACK:
        raise ActionError("The stack is public")
    key = zone_key(ops.player(state, a.zone.player, a.actor), a.zone.zone)
    _open_view(state, a.actor, key, "search", [], f"search-{state.seq}")
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" is searching {zone_label(state, key, a.actor)}")])


def end_view(state: GameState, a: A.EndView) -> None:
    """Close the actor's private "look" views; the cards are hidden again."""
    closing = [v for v in state.views if v.viewer == a.actor and v.kind == "look" and (a.zone is None or v.zone.endswith(":" + a.zone))]
    if not closing:
        raise ActionError("You are not looking at anything")
    state.views = [v for v in state.views if v not in closing]


def search_end(state: GameState, a: A.SearchEnd) -> None:
    key = state.searching(a.actor)
    if key is None:
        raise ActionError("You are not searching anything")
    state.views = [v for v in state.views if not (v.viewer == a.actor and v.kind == "search")]
    parts = [pname(state, a.actor), text(f" finished searching {zone_label(state, key, a.actor)}")]
    if a.shuffle and a.r is not None:
        rekey_zone(state, key, a.r.perm, a.r.new_ids)
        parts.append(text(" and shuffled it"))
    log(state, a.actor, a.ts, parts)
