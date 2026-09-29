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


def untap_all(state: GameState, a: A.UntapAll) -> None:
    pid = ops.player(state, a.player, a.actor)
    count = untap_permanents(state, pid)
    log(state, a.actor, a.ts, [pname(state, pid), text(f" untapped {count} permanent{'s' if count != 1 else ''}")])


def untap_permanents(state: GameState, pid: str) -> int:
    count = 0
    for cid in state.zone(zone_key(pid, "battlefield")):
        c = state.cards[cid]
        if c.tapped:
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
    )
    key = zone_key(pid, "battlefield")
    source = None
    if a.source_id:
        src = ops.card(state, a.source_id)
        if ops.visible_to_all_players(state, src):
            source = TokenSource(source_id=src.id, name=src.name)
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
            is_token=True,
            token=spec.model_copy(),
            quantity=a.count if stacked else 1,
            token_source=source,
        )
        state.cards[new_id] = c
        state.zone(key).append(new_id)
    what = f"{a.count} {spec.name} token{'s' if a.count != 1 else ''}" if a.count != 1 else f"a {spec.name} token"
    if stacked and a.count > 1:
        what += f" (stack ×{a.count})"
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" created {what}" + (f" (from {source.name})" if source else ""))])


def copy_card(state: GameState, a: A.CopyCard) -> None:
    src = ops.card(state, a.card_id)
    if a.r is None or len(a.r.ids) != a.count:
        raise ActionError("unresolved copy")
    if ops.zone_name(src.zone) not in ("battlefield", STACK) and not publicly_visible(state, src):
        raise ActionError("Only public objects can be copied")
    pid = ops.player(state, a.player, a.actor)
    on_stack = src.zone == STACK
    key = STACK if on_stack else zone_key(pid, "battlefield")
    for i, new_id in enumerate(a.r.ids):
        if new_id in state.cards:
            raise ActionError("id collision")
        c = CardInstance(
            id=new_id,
            card_id=src.card_id,
            name=src.name,
            owner=pid,
            controller=pid,
            zone=key,
            x=(a.x if a.x is not None else src.x + 24) + i * 18,
            y=(a.y if a.y is not None else src.y + 24) + i * 18,
            face=src.face,
            is_token=True,
            token=src.token.model_copy() if src.token else None,
            ability=src.ability.model_copy() if src.ability else None,
            copy_of=CopyInfo(source_id=src.id, source_name=src.name, modifications=a.modifications),
            quantity=1,
        )
        state.cards[new_id] = c
        state.zone(key).append(new_id)
    n = f"{a.count} copies" if a.count != 1 else "a copy"
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" created {n} of "), ops.card_part(state, src)])


def delete_card(state: GameState, a: A.DeleteCard) -> None:
    targets = ops.cards(state, a.card_ids)
    for c in targets:
        if not ops.is_ephemeral(c):
            raise ActionError(f"{c.name} is a real card; move it to a zone instead")
        if c.protected and not a.force:
            raise ActionError(f"{c.name} is protected — confirm to delete it")
    names = group(state, targets)
    for c in targets:
        ops.delete(state, c)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" removed "), names])


def set_face(state: GameState, a: A.SetFace) -> None:
    c = ops.card(state, a.card_id)
    before = ops.card_part(state, c)
    c.face = a.face if a.face is not None else (c.face + 1) % max(1, a.faces)
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
    before = {c.id: seers(state, c) for c in targets}
    turned_up: list[CardInstance] = []
    turned_down: list[CardInstance] = []
    for c in targets:
        new = (not c.face_down) if a.face_down is None else a.face_down
        if new == c.face_down:
            continue
        c.face_down = new
        c.face_down_kind = (a.kind or ("exile" if zone_of(c) == "exile" else "generic")) if new else None
        # A face-down card is anonymous to everyone but its controller from now on.
        c.revealed_to = []
        (turned_down if new else turned_up).append(c)
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
        if not _on_battlefield(c):
            raise ActionError(f"{c.name} is not on the battlefield")
    dest = zone_key(pid, "battlefield")
    for c in targets:
        if c.zone == dest:
            continue
        ops.remove_from_zone(state, c)
        ops.insert(state, c, dest)
        c.controller = pid
        c.attacking = None
        c.blocking = None
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
            ops.remove_from_zone(state, c)
            ops.insert(state, c, dest)
            c.controller = c.owner
            c.attacking = None
            c.blocking = None
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
