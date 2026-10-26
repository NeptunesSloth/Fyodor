"""Per-card state: tapping, counters, tokens, copies, faces, notes, control."""

from __future__ import annotations

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.ops import group, log, pname, text
from app.game.state import (
    STACK,
    CardInstance,
    CopyInfo,
    GameState,
    TokenDef,
    TokenSource,
    split_zone,
    zone_key,
)
from app.game.visibility import publicly_visible, seers


def _on_battlefield(c: CardInstance) -> bool:
    return ops.zone_name(c.zone) == "battlefield"


def tap(state: GameState, a: A.Tap) -> None:
    targets = ops.cards(state, a.card_ids)
    changed_on: list[CardInstance] = []
    changed_off: list[CardInstance] = []
    for c in targets:
        if not _on_battlefield(c):
            continue
        new = (not c.tapped) if a.tapped is None else a.tapped
        if new != c.tapped:
            c.tapped = new
            (changed_on if new else changed_off).append(c)
    if not changed_on and not changed_off:
        raise ActionError("Nothing to tap or untap")
    if changed_on:
        log(state, a.actor, a.ts, [pname(state, a.actor), text(" tapped "), group(state, changed_on)])
    if changed_off:
        log(state, a.actor, a.ts, [pname(state, a.actor), text(" untapped "), group(state, changed_off)])


def phase_shift(state: GameState, a: A.PhaseShift) -> None:
    """-- phasing (wave 13D) -- 702.26b-g: a permanent phases out into its controller's "phased" zone (not a zone change,
    702.26d: counters, damage, tapped state and tokens stay) and leaves combat (506.4); Auras, Equipment and Fortifications
    attached to it phase out with it (702.26g; 702.26h: indirectly if also named). Phasing in puts each back on its
    controller's battlefield, indirect ones along with their host; a directly phased attachment whose host isn't on the
    battlefield any more phases in unattached (702.26i)."""
    here, there = ("battlefield", "phased") if a.out else ("phased", "battlefield")
    moving = {c.id: c for c in ops.cards(state, a.card_ids) if c.zone == zone_key(c.controller, here) and (a.out or not c.phased_indirect)}
    indirect: set[str] = set()
    grew = True
    while grew:  # (attachments of attachments: an Aura on an Equipment)
        grew = False
        for c in state.cards.values():
            if c.id not in indirect and c.attached_to in moving and c.zone == zone_key(c.controller, here) and (a.out or c.phased_indirect):
                moving[c.id] = c
                indirect.add(c.id)
                grew = True
    for c in moving.values():
        ops.remove_from_zone(state, c)
        ops.insert(state, c, zone_key(c.controller, there))
        c.phased_indirect = a.out and c.id in indirect
        if a.out:
            ops.lose_attack_target(state, c)
        if a.out:  # 506.4 (-- review (wave 14R) -- every block of a blocker of several, 509.1a)
            c.attacking = None
            c.attacking_without_target = None
            c.unblock()
            for other in state.cards.values():
                if other.blocks(c.id):
                    other.unblock(c.id)
                if other.attacking and other.attacking.kind == "card" and other.attacking.id == c.id:
                    other.attacking = None
    for c in moving.values():
        if not a.out and c.attached_to and ((host := state.cards.get(c.attached_to)) is None or not host.zone.endswith(":battlefield")):
            c.attached_to = None  # 702.26i (state-based actions apply as appropriate)
            c.attach_offset = None
    if moving:
        log(state, a.actor, a.ts, [group(state, list(moving.values())), text(f" phase{'' if len(moving) > 1 else 's'} {'out' if a.out else 'in'}")])


def untap_all(state: GameState, a: A.UntapAll) -> None:
    pid = ops.player(state, a.player, a.actor)
    count = untap_permanents(state, pid, set(a.keep_tapped))
    log(state, a.actor, a.ts, [pname(state, pid), text(f" untapped {count} permanent{'s' if count != 1 else ''}")])


def untap_permanents(state: GameState, pid: str, keep: set[str] | frozenset[str] = frozenset()) -> int:
    count = 0
    for cid in state.zone(zone_key(pid, "battlefield")):
        c = state.cards[cid]
        if c.tapped and cid not in keep:
            c.tapped = False
            count += 1
    return count


def counter(state: GameState, a: A.Counter) -> None:
    targets = ops.cards(state, a.card_ids)
    for c in targets:
        value = max(0, c.counters.get(a.kind, 0) + a.delta)
        if value:
            c.counters[a.kind] = value
        else:
            c.counters.pop(a.kind, None)
    verb = f"put {a.delta} {a.kind} counter{'s' if a.delta != 1 else ''} on" if a.delta > 0 else (
        f"removed {-a.delta} {a.kind} counter{'s' if a.delta != -1 else ''} from"
    )
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" {verb} "), group(state, targets)])


def set_counter(state: GameState, a: A.SetCounter) -> None:
    c = ops.card(state, a.card_id)
    if a.rename_from and a.rename_from != a.kind:
        old = c.counters.pop(a.rename_from, 0)
        value = a.value if a.value else old
    else:
        value = a.value
    if value:
        c.counters[a.kind] = value
    else:
        c.counters.pop(a.kind, None)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" set {a.kind} counters on "), ops.card_part(state, c), text(f" to {value}")])


def create_token(state: GameState, a: A.CreateToken) -> None:
    pid = ops.player(state, a.player, a.actor)
    stacked = bool(a.stacked)
    if a.r is None or len(a.r.ids) != (1 if stacked else a.count):
        raise ActionError("unresolved token creation")
    spec = a.resolved_token or TokenDef(
        name=a.token.name,
        card_id=a.token.card_id,
        power=a.token.power,
        toughness=a.token.toughness,
        colors=list(a.token.colors),
        type_line=a.token.type_line,
        text=a.token.text,
        back=_token_back(a.token.back),  # -- keyword actions & face-down (wave 3F) -- 111.10i
    )
    emblem = spec.type_line == "Emblem"  # -- emblems (wave 13A) -- 114.1: an object in the command zone, not a token (111.7 doesn't apply)
    key = zone_key(pid, "command" if emblem else a.zone or "battlefield")
    source = None
    if a.source_id:
        src = ops.card(state, a.source_id)
        if ops.visible_to_all_players(state, src):
            source = TokenSource(source_id=src.id, name=src.name, object_id=a.source_object)
    base_x = a.x if a.x is not None else 20.0
    base_y = a.y if a.y is not None else 220.0
    for i, new_id in enumerate(a.r.ids):
        if new_id in state.cards:
            raise ActionError("id collision")
        c = CardInstance(
            id=new_id,
            card_id=spec.card_id,
            name=spec.name,
            owner=pid,
            controller=pid,
            zone=key,
            x=base_x + (i % 10) * 16,
            y=base_y + (i // 10) * 16 + (i % 10) * 4,
            tapped=a.tapped,
            is_token=not emblem,
            token=spec.model_copy(),
            quantity=a.count if stacked else 1,
            token_source=source,
            embalmed=a.embalmed,
        )
        state.cards[new_id] = c
        state.zone(key).append(new_id)
    what = f"{a.count} {spec.name} token{'s' if a.count != 1 else ''}" if a.count != 1 else f"a {spec.name} token"
    if emblem:
        what = f"the {spec.name}"
    if stacked and a.count > 1:
        what += f" (stack ×{a.count})"
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" created {what}" + (f" (from {source.name})" if source else ""))])


def copy_card(state: GameState, a: A.CopyCard) -> None:
    src = state.cards.get(a.card_id) if a.saved_stack is not None else ops.card(state, a.card_id)
    if a.r is None or len(a.r.ids) != a.count:
        raise ActionError("unresolved copy")
    snap = a.saved_stack
    if snap is not None:
        if snap.card != a.card_id or snap.zone != STACK or snap.face_down or a.zone is not None:
            raise ActionError("That preserved object is not a public spell")
    elif a.last_known:
        snap = state.rules.lki.get(a.last_known) if state.rules is not None else None
        if snap is None or snap.card != a.card_id or snap.zone != STACK or snap.is_token:
            raise ActionError("That spell has no last known information")
    elif src is not None and ops.zone_name(src.zone) not in ("battlefield", STACK) and not publicly_visible(state, src):
        raise ActionError("Only public objects can be copied")
    pid = ops.player(state, a.player, a.actor)
    on_stack = snap is not None or (src is not None and src.zone == STACK)
    key = STACK if on_stack else zone_key(pid, "battlefield")
    if a.zone:
        key = zone_key(pid, a.zone)
    for i, new_id in enumerate(a.r.ids):
        if new_id in state.cards:
            raise ActionError("id collision")
        c = CardInstance(
            id=new_id,
            card_id=a.printing or (snap.printing if snap is not None else src.card_id if src else None),
            name=a.name or (snap.name if snap is not None else src.name if src else ""),
            owner=pid, controller=pid, zone=key,
            x=(a.x if a.x is not None else (src.x if src else 0) + 24) + i * 18,
            y=(a.y if a.y is not None else (src.y if src else 0) + 24) + i * 18,
            face=(snap.face if snap is not None else src.face if src else 0) if a.face is None else a.face,
            is_token=True,
            token=src.token.model_copy() if src and src.token and a.saved_stack is None else None,
            ability=src.ability.model_copy() if src and src.ability and a.saved_stack is None else None,
            copy_of=CopyInfo(source_id=a.card_id, source_name=snap.name if snap is not None else src.name if src else "",
                             modifications=a.modifications),
            quantity=1,
        )
        state.cards[new_id] = c
        state.zone(key).append(new_id)
    n = f"{a.count} copies" if a.count != 1 else "a copy"
    if snap is not None:
        source_part = text(snap.name)
    else:
        assert src is not None
        source_part = ops.card_part(state, src)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" created {n} of "), source_part])


def delete_card(state: GameState, a: A.DeleteCard) -> None:
    targets = ops.cards(state, a.card_ids)
    for c in targets:
        if not ops.is_ephemeral(c):
            raise ActionError(f"{c.name} is a real card; move it to a zone instead")
        if c.protected and not a.force:
            raise ActionError(f"{c.name} is protected — confirm to delete it")
    names = group(state, targets)
    for c in targets:
        if c.merged:  # -- merged permanents (wave 18D) -- 730.3: removing the token on top doesn't remove the cards under it
            ops.move_card(state, c, zone_key(c.owner, "graveyard"))
            continue
        ops.delete(state, c)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" removed "), names])


def _token_back(spec: A.TokenSpec | None) -> TokenDef | None:
    """-- keyword actions & face-down (wave 3F) -- a double-faced token's back face (111.10i)."""
    if spec is None:
        return None
    return TokenDef(name=spec.name, card_id=spec.card_id, power=spec.power, toughness=spec.toughness, colors=list(spec.colors),
                    type_line=spec.type_line, text=spec.text)


def merge(state: GameState, a: A.Merge) -> None:
    """-- merged permanents (wave 18D) -- 702.140c, 730.2: the mutating creature spell on the stack becomes part of the permanent."""
    from app.game import merging

    host, spell = ops.card(state, a.card_id), ops.card(state, a.spell_id)
    if a.r is None or not a.r.ids or not _on_battlefield(host) or spell.zone != STACK or host.melded or spell.merged or spell.id == host.id:
        raise ActionError("Only a spell on the stack can merge with a permanent on the battlefield")
    keys = {p.commander_key for p in host.merged if p.commander_key} | {k for k in (host.commander_key, spell.commander_key) if k}
    if len(keys) > 1:
        raise ActionError("Two commanders can't be merged")
    merging.merge(state, host, spell, a.over, a.r.ids[0])
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" merged {spell.name} {'over' if a.over else 'under'} "), ops.card_part(state, host)])


def meld(state: GameState, a: A.Meld) -> None:
    """-- merged permanents (wave 18D) -- 701.42a: the two exiled cards of a meld pair enter the battlefield as one permanent."""
    from app.game import merging, placement

    first, second = ops.card(state, a.card_id), ops.card(state, a.other_id)
    if a.r is None or not a.r.ids or ops.zone_name(first.zone) != "exile" or ops.zone_name(second.zone) != "exile" \
            or first.is_token or second.is_token or first.owner != second.owner:
        raise ActionError("Only two cards of a meld pair in exile can be melded")
    if first.commander_key and second.commander_key:
        raise ActionError("Two commanders can't be melded")
    owner = first.owner
    x, y = placement.free_spot(state, zone_key(owner, "battlefield"), a.row)
    ops.move_card(state, first, zone_key(owner, "battlefield"), x=x, y=y)
    merging.meld(state, first, second, a.result_id, a.result_name, a.r.ids[0])
    first.tapped = a.tapped
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" melded into {a.result_name}")])


def set_face(state: GameState, a: A.SetFace) -> None:
    c = ops.card(state, a.card_id)
    before = ops.card_part(state, c)
    c.face = a.face if a.face is not None else (c.face + 1) % max(1, a.faces)
    if c.token is not None and c.token.back is not None:  # -- wave 3F -- a double-faced token shows the face that's up
        c.face = min(c.face, 1)
        c.name = c.token.back.name if c.face == 1 else c.token.name
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" turned over "), before])


def flip(state: GameState, a: A.Flip) -> None:
    c = ops.card(state, a.card_id)
    c.flipped = not c.flipped
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" flipped "), ops.card_part(state, c)])


def zone_of(c: CardInstance) -> str:
    return ops.zone_name(c.zone)


def face_down(state: GameState, a: A.FaceDown) -> None:
    targets = ops.cards(state, a.card_ids)
    for c in targets:
        zone = ops.zone_name(c.zone)
        if zone not in ("battlefield", "exile", "foretell", STACK):
            raise ActionError("Only cards on the battlefield, in exile or on the stack can be face down")
        if c.melded and a.face_down is not False:
            raise ActionError("A melded permanent can't be turned face down (712.16)")  # -- merged permanents (wave 18D) --
    before = {c.id: seers(state, c) for c in targets}
    turned_up: list[CardInstance] = []
    turned_down: list[CardInstance] = []
    for c in targets:
        new = (not c.face_down) if a.face_down is None else a.face_down
        if new == c.face_down:
            continue
        c.face_down = new
        c.face_down_kind = (a.kind or ("exile" if zone_of(c) == "exile" else "generic")) if new else None
        c.face_down_as = a.face_down_as if new else None  # (-- hidden exile (wave 18A) -- 708.2a)
        # A face-down card is anonymous to everyone but its controller from now on.
        c.revealed_to = []
        (turned_down if new else turned_up).append(c)
    if turned_down and state.rules is not None:
        down = {c.id for c in turned_down}  # -- Vesuvan Shapeshifter (wave 110C) -- 708.2: its copy lasts "until this creature is turned face down"
        state.rules.effects = [e for e in state.rules.effects if not (e.label == "Copy until turned face down" and any(x.split(".")[0] in down for x in e.affected))]
    if turned_down:
        log(state, a.actor, a.ts, [pname(state, a.actor), text(" turned "), group(state, turned_down, before), text(" face down")])
    if turned_up:
        log(state, a.actor, a.ts, [pname(state, a.actor), text(" turned "), group(state, turned_up), text(" face up")])


def note(state: GameState, a: A.Note) -> None:
    c = ops.card(state, a.card_id)
    c.note = a.text
    verb = " added a note to " if a.text else " cleared the note on "
    log(state, a.actor, a.ts, [pname(state, a.actor), text(verb), ops.card_part(state, c)])


def set_controller(state: GameState, a: A.SetController) -> None:
    pid = ops.player(state, a.player, a.actor)
    targets = ops.cards(state, a.card_ids)
    for c in targets:
        if not _on_battlefield(c) and not (c.zone == STACK and c.ability is None):
            raise ActionError(f"{c.name} is not on the battlefield or a spell on the stack")
    dest = zone_key(pid, "battlefield")
    for c in targets:
        if c.zone == STACK:
            c.controller = pid
            entry = state.rules.stack.get(c.id) if state.rules is not None else None
            if entry is not None and entry.kind == "spell":
                entry.controller = pid
            continue
        if c.zone == dest:
            continue
        ops.lose_attack_target(state, c)
        ops.remove_from_zone(state, c)
        ops.insert(state, c, dest)
        c.controller = pid
        c.attacking = None
        c.attacking_without_target = None
        c.unblock()
    log(state, a.actor, a.ts, [pname(state, pid), text(" gained control of "), group(state, targets)])


def return_to_owner(state: GameState, a: A.ReturnToOwner) -> None:
    targets = ops.cards(state, a.card_ids)
    moved = []
    for c in targets:
        if c.zone == STACK or c.ability is not None:
            continue
        holder, zone = split_zone(c.zone)
        if holder == c.owner and c.controller == c.owner:
            continue
        dest = zone_key(c.owner, zone)
        if zone == "battlefield":
            ops.lose_attack_target(state, c)
            ops.remove_from_zone(state, c)
            ops.insert(state, c, dest)
            c.controller = c.owner
            c.attacking = None
            c.attacking_without_target = None
            c.unblock()
        else:
            ops.move_card(state, c, dest)
        moved.append(c)
    if not moved:
        raise ActionError("Those cards are already with their owners")
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" returned "), group(state, moved), text(" to their owners")])


def set_commander(state: GameState, a: A.SetCommander) -> None:
    c = ops.card(state, a.card_id)
    if c.is_token or c.ability:
        raise ActionError("Tokens cannot be commanders")
    if a.value:
        if not c.commander_key:
            c.commander_key = f"cmd-{c.owner}-{len([x for x in state.cards.values() if x.commander_key]) + 1}"
            state.players[c.owner].commander_tax.setdefault(c.commander_key, 0)
        log(state, a.actor, a.ts, [pname(state, c.owner), text(" designated "), ops.card_part(state, c), text(" as a commander")])
    else:
        if c.commander_key:
            state.players[c.owner].commander_tax.pop(c.commander_key, None)
        c.commander_key = None
        log(state, a.actor, a.ts, [ops.card_part(state, c), text(" is no longer a commander")])
