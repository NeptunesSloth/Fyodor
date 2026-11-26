"""Zone, library and hidden-information actions."""

from __future__ import annotations

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.handlers import objects, response
from app.game.ops import group, log, pname, text, zone_label
from app.game.rules_state import emit
from app.game.state import (
    ALL,
    STACK,
    CardInstance,
    DigLog,
    GameState,
    RevealLog,
    ViewContext,
    split_zone,
    zone_key,
)
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
    if a.routes:
        dests = [destination(state, a.routes.get(c.id, a.to), c, a.actor) for c in moving]
    tapped = set(a.tapped_ids or ())
    positions = a.r.positions if a.r else {}
    who_saw = {c.id: seers(state, c) for c in moving}
    sources = {c.id: c.zone for c in moving}
    library_parts = {p.id for c in moving for p in c.merged} | {c.id for c in moving}
    for c, dest in zip(moving, dests, strict=True):  # -- keyword actions & face-down (wave 3F) --
        # 708.9: a face-down permanent leaving the battlefield, or a face-down spell leaving the stack
        # other than for the battlefield, is revealed to all players as it moves (the log names it to all)
        # (-- review (sys 18A) -- even when it goes on face down, e.g. into a face-down pile: 708.9 has no exception)
        if c.face_down and (c.zone.endswith(":battlefield") and not dest.endswith(":battlefield")
                                                or c.zone == STACK and not dest.endswith(":battlefield")):
            who_saw[c.id] = {ALL}
    commander_casts: list[CardInstance] = []
    was_down = {c.id: c.face_down for c in moving}

    for i, (c, dest) in enumerate(zip(moving, dests, strict=True)):
        position = (a.library_positions or {}).get(c.id, a.position)
        lib_top = ops.zone_name(dest) == "library" and position != "bottom"
        index = a.index + i if a.index is not None else (i if lib_top else None)
        x = y = None
        if ops.zone_name(dest) == "battlefield":
            if c.id in positions:
                x, y = positions[c.id]
            elif a.x is not None and a.y is not None:
                x, y = a.x + i * 18, a.y + i * 18
        if c.zone.endswith(":command") and dest == STACK and c.commander_key:
            commander_casts.append(c)
        ops.move_card(state, c, dest, index=index, position=position, x=x, y=y, face_down=a.face_down, rest=a.rest_zone,
                      sticker_recipient101=(a.sticker_recipients101 or {}).get(c.id),
                      keep_counters=c.id in (a.keep_counters or ()))
        if (a.entry_characteristics and c.id in a.entry_characteristics and c.id in state.cards
                and c.zone.endswith(":battlefield") and not sources[c.id].endswith(":battlefield") and not c.is_token):
            c.entry_characteristics = a.entry_characteristics[c.id].model_copy(deep=True)
        if dest == STACK and sources[c.id] != STACK and a.actor in state.players:
            c.controller = a.actor  # -- refused look/cast-free (wave 3R5) -- 601.2a: the player who casts a spell controls it
        if (a.tapped or c.id in tapped) and ops.zone_name(dest) == "battlefield" and c.id in state.cards:
            c.tapped = True
        if a.back_ids and c.id in a.back_ids and ops.zone_name(dest) == "battlefield" and c.id in state.cards:
            c.face = 1  # -- transform (wave 11A) -- 712.14a
        if a.flipped_ids and c.id in a.flipped_ids and ops.zone_name(dest) == "battlefield" and c.id in state.cards:
            c.flipped = True  # -- flip (wave 110I) -- 710.2: the alternative characteristics apply once it is on the battlefield
        if c.face_down and a.face_down:
            c.face_down_kind = a.face_down_kind or ("exile" if ops.zone_name(dest) == "exile" else "generic")
            c.face_down_as = a.face_down_as  # (-- hidden exile (wave 18A) -- 708.2a)
            if ops.zone_name(dest) == 'exile' and a.blind:
                c.unseen = True
            if ops.zone_name(dest) == "exile" and a.actor in state.players and a.actor != c.owner:
                # -- as long as (wave 9B) -- 406.3: a card another player exiles face down is looked at by the one who exiled
                # it (Gonti, Thief of Sanity), not by its owner: the face-down rule shows an exiled card to its "controller"
                c.controller = a.actor

    if a.library_order is not None:
        # Arrange only this event's entering physical cards before tracking observes the event.
        ordered = list(dict.fromkeys(cid for cid in a.library_order if cid in library_parts))
        for key, ids in state.zones.items():
            if not key.endswith(":library"):
                continue
            entered = [cid for cid in ordered if cid in ids and cid in state.cards]
            top = [cid for cid in entered if (a.library_positions or {}).get(cid) == "top"]
            bottom = [cid for cid in entered if (a.library_positions or {}).get(cid) == "bottom"]
            selected = set(top + bottom)
            ids[:] = top + [cid for cid in ids if cid not in selected] + bottom

    if not a.keep_ids:  # -- review (face-down ids) -- 406.3: a card that went face down where others see it is a new object
        fresh = renumber_down(state, [(c, sources[c.id], was_down[c.id]) for c in moving])
        who_saw = {fresh.get(k, k): v for k, v in who_saw.items()}
        sources = {fresh.get(k, k): v for k, v in sources.items()}

    for c in commander_casts:
        caster = state.players[c.owner]
        caster.commander_casts[c.commander_key or ""] = caster.commander_casts.get(c.commander_key or "", 0) + 1
        if state.settings.auto_commander_tax:
            owner = state.players[c.owner]
            owner.commander_tax[c.commander_key or ""] = owner.commander_tax.get(c.commander_key or "", 0) + 2

    # One log line per (source zone, destination) pair keeps multi-card moves readable.
    by_route: dict[tuple[str, str, str | None], list[CardInstance]] = {}
    for c, dest in zip(moving, dests, strict=True):
        by_route.setdefault((sources[c.id], dest, (a.library_positions or {}).get(c.id, a.position)), []).append(c)
    for (src, dest, log_position), group_cards in by_route.items():
        if src == dest and ops.zone_name(dest) != "library":
            continue  # reordering within hand / battlefield is not worth a log line
        if ops.zone_name(dest) == "library" and len(group_cards) > 1:
            # -- review (wave 29B) -- 401.4: the order of cards put into a library together isn't revealed ("in a random order", "in any
            # order"): the cards are listed by name, not in the order they went in (-- review 30 -- to the players who looked at them too:
            # a random order is no one's; a hidden card is only counted, so its place in the list says nothing)
            group_cards = sorted(group_cards, key=lambda c: (c.name or "", c.id))
        verb = _verb(src, dest, log_position)
        # -- playtest M6 -- 701.9a: a player discards from their own hand: an effect that makes each player discard ("Each player discards
        # their hand", Wheel of Fortune) reads "Bob discarded …", not "Alice discarded … from Bob's hand" (the rules engine's moves keep ids)
        who = split_zone(src)[0] if verb == "discarded" and a.keep_ids and split_zone(src)[0] in state.players else a.actor
        parts = [pname(state, who), text(f" {verb} "), group(state, group_cards, who_saw)]
        if a.keep_ids and ops.zone_name(src) == "battlefield" and ops.zone_name(dest) == "graveyard":
            # the rules engine's own move: "Grizzly Bears dies", "Sol Ring is put into Alice's graveyard" (not "Alice moved … from
            # their battlefield to their graveyard": nobody moved it, and whose graveyard it is reads by name)
            many = len(group_cards) > 1
            if all(c.id in (a.died or ()) for c in group_cards):
                parts = [group(state, group_cards, who_saw), text(" die" if many else " dies")]
            else:
                parts = [group(state, group_cards, who_saw), text(f" {'are' if many else 'is'} put into {zone_label(state, dest)}")]
        elif verb in ("played", "cast", "discarded"):
            if split_zone(src)[0] != who:
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


def renumber_down(state: GameState, moved: list[tuple[CardInstance, str, bool]]) -> dict[str, str]:
    """(card, the zone it came from, was it face down) -> the new ids of those that need one (ops.needs_fresh_id)."""
    return ops.renumber(state, [c.id for c, source, was in moved if c.id in state.cards and ops.needs_fresh_id(source, c.zone, was, c)])


def renumber(state: GameState, a: A.Renumber) -> None:
    ops.renumber(state, a.card_ids)


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
    if a.learned_rows and a.actor in state.players:  # -- saved rows -- (decided by resolve: app/game/resolve.py _learned_rows)
        rows = state.players[a.actor].row_overrides
        for name, row in a.learned_rows.items():
            if row is None:
                rows.pop(name, None)
            else:
                rows[name] = row


def draw_cards(state: GameState, pid: str, count: int, from_bottom: bool = False) -> list[CardInstance]:
    lib = state.zone(zone_key(pid, "library"))
    if not lib:
        raise ActionError(f"{state.players[pid].name}'s library is empty")
    drawn = [state.cards[cid] for cid in (reversed(lib[-count:]) if from_bottom else lib[:count])]
    for c in drawn:
        ops.move_card(state, c, zone_key(pid, "hand"))
        emit(state, "drew", player=pid, card=c.id)  # 121.2: each card is its own draw
    return drawn


def draw(state: GameState, a: A.Draw) -> None:
    pid = ops.player(state, a.player, a.actor)
    drawn = draw_cards(state, pid, a.count, a.from_bottom)
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
    state.shuffles[key] = state.shuffles.get(key, 0) + 1  # (table motion: the shuffle is public)
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
    selected = a.card_ids
    if a.r.retained_indices:
        pile = state.zone(key)
        indices = set(a.r.retained_indices)
        if (a.zone != 'library' or a.card_ids is not None or len(indices) != len(a.r.retained_indices)
                or any(index < 0 or index >= len(pile) for index in indices)):
            raise ActionError('The retained library placement does not match this shuffle')
        selected = [cid for index, cid in enumerate(pile) if index not in indices]
    rekey_zone(state, key, a.r.perm, a.r.new_ids, selected)
    if a.zone == "library":
        emit(state, "library_shuffled", player=pid, actor=a.actor)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" shuffled {zone_label(state, key, a.actor)}")])


def mill(state: GameState, a: A.Mill) -> None:
    pid = ops.player(state, a.player, a.actor)
    lib = state.zone(zone_key(pid, "library"))
    if not lib:
        raise ActionError(f"{state.players[pid].name}'s library is empty")
    milled = [state.cards[cid] for cid in lib[: a.count]]
    dest = zone_key(pid, a.to)
    moved = [(c, c.zone, c.face_down) for c in milled]
    for c in milled:
        ops.move_card(state, c, dest, face_down=a.face_down if a.to == "exile" else None)
        if c.face_down:
            c.face_down_kind = "exile"
            c.unseen = a.blind  # (-- hidden exile (wave 18A) --)
        if a.to == "graveyard" and c.zone == dest:  # -- triggers (wave 17D) -- 701.17a (not a card a replacement sent elsewhere)
            emit(state, "milled", card=c.id, player=pid)
    if not a.keep_ids:
        renumber_down(state, moved)
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
    if not a.keep_ids:
        renumber_down(state, [(c, zone_key(pid, "library"), False) for c in cards_])
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
    owners = {c.owner for c in targets}
    # -- public reveals -- the table shows each viewer the cards this line names to them (a reveal to some players: those players only)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" revealed "), group(state, targets, extra), text(f" to {audience}")],
        reveal=RevealLog(player=owners.pop() if len(owners) == 1 else a.actor or ""))


def hide(state: GameState, a: A.Hide) -> None:
    """End a reveal: the cards become anonymous again for everyone who can't normally see them."""
    targets = ops.cards(state, a.card_ids)
    if a.viewers is not None:
        for viewer in a.viewers:
            ops.player(state, viewer, a.actor)
    for c in targets:
        c.revealed_to = [] if a.viewers is None else [viewer for viewer in c.revealed_to if viewer not in a.viewers]
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
    # -- public reveals -- 701.20a: everyone sees them; the engine names the spell or ability and, for "reveal … until", the card found
    # ("Alice revealed cards from the top of her library (Nissa, Resurgent Animist): Forest, Forest and Llanowar Elves — found Llanowar Elves")
    what = f"cards from the top of {zone_label(state, key, a.actor)}" if a.until else f"the top of {zone_label(state, key, a.actor)}"
    tail = ([text(" — found "), ops.card_part(state, top[-1])] if a.found and top else [text(" — none found")] if a.until else [])
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" revealed {what}" + (f" ({a.source})" if a.source else "") + ": "), group(state, top), *tail],
        reveal=RevealLog(player=pid, source=a.source, until=a.until, found=a.found and bool(top)))


def reveal_until(state: GameState, a: A.RevealUntil) -> None:
    pid = ops.player(state, a.player, a.actor)
    if a.r is None:
        raise ActionError("unresolved reveal")
    key = zone_key(pid, "library")
    top = [state.cards[cid] for cid in state.zone(key)[: a.r.count]]
    for c in top:
        c.revealed_to = [ALL]
    hit = top[-1] if a.r.hit and top else None
    tail = [text(" (found "), ops.card_part(state, hit), text(")")] if hit else [text(f" (no {a.card_type} in it)")]
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" revealed from the top of {zone_label(state, key, a.actor)} until a {a.card_type}: "),
                               group(state, top), *tail],
        dig=DigLog(mode="reveal_until", player=pid, cards=[c.id for c in top], hit=hit.id if hit else None))


def cascade(state: GameState, a: A.Cascade) -> None:
    pid = ops.player(state, a.player, a.actor)
    if a.r is None or a.r.move is None:
        raise ActionError("unresolved cascade")
    exile = zone_key(pid, "exile")
    before = len(state.zone(exile))
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" cascades (mana value less than {a.below})")])
    move(state, a.r.move)
    landed = state.zone(exile)[before:]
    hit = landed[-1] if a.r.hit and landed else None
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" exiled "), group(state, [state.cards[c] for c in landed]),
                               *([text(", hitting "), ops.card_part(state, state.cards[hit])] if hit else [text(" and missed")])],
        dig=DigLog(mode="cascade", player=pid, cards=list(landed), hit=hit))


def fetch_card(state: GameState, a: A.FetchCard) -> None:
    pid = ops.player(state, a.player, a.actor)
    if a.r is None:
        raise ActionError("unresolved search")
    move(state, a.r.move)
    key = zone_key(pid, "library")
    if len(a.r.shuffle.perm) != len(state.zone(key)):
        raise ActionError("The library changed; try again")
    rekey_zone(state, key, a.r.shuffle.perm, a.r.shuffle.new_ids)
    emit(state, "library_shuffled", player=pid, actor=a.actor)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" searched for a {a.name} and shuffled {zone_label(state, key, a.actor)}")])


def discard_random(state: GameState, a: A.DiscardRandom) -> None:
    if a.r is None:
        raise ActionError("unresolved discard")
    n = len(a.r.card_ids)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" discards {n} card{'s' if n != 1 else ''} at random")])
    move(state, a.r)


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
