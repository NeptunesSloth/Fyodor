"""Tabletop object behaviour: rotation, lock/protect, attachments, groups, token stacks,
mana pools, reminders and table settings."""

from __future__ import annotations

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.ops import group, log, pname, text
from app.game.state import ALL, CardInstance, GameState, Reminder

MANA_ORDER = "WUBRGCS"


def _battlefield_cards(state: GameState, ids: list[str]) -> list[CardInstance]:
    cards = ops.cards(state, ids)
    for c in cards:
        if ops.zone_name(c.zone) != "battlefield":
            raise ActionError(f"{c.name or 'That card'} is not on the battlefield")
    return cards


def rotate(state: GameState, a: A.Rotate) -> None:
    targets = _battlefield_cards(state, a.card_ids)
    if a.degrees is None and a.delta is None:
        raise ActionError("Give degrees or delta")
    for c in targets:
        value = a.degrees if a.degrees is not None else c.rotation + (a.delta or 0)
        c.rotation = round(value % 360, 2)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" rotated "), group(state, targets)], kind="minor")


def set_lock(state: GameState, a: A.SetLock) -> None:
    targets = _battlefield_cards(state, a.card_ids)
    value = (not targets[0].locked) if a.value is None else a.value
    for c in targets:
        c.locked = value
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" locked " if value else " unlocked "), group(state, targets)], kind="minor")


def set_protect(state: GameState, a: A.SetProtect) -> None:
    targets = ops.cards(state, a.card_ids)
    value = (not targets[0].protected) if a.value is None else a.value
    for c in targets:
        c.protected = value
    verb = " protected " if value else " removed protection from "
    log(state, a.actor, a.ts, [pname(state, a.actor), text(verb), group(state, targets)], kind="minor")


# ---------------------------------------------------------------------------- attachments


def _ancestors(state: GameState, c: CardInstance) -> set[str]:
    seen: set[str] = set()
    parent = c.attached_to
    while parent and parent not in seen and parent in state.cards:
        seen.add(parent)
        parent = state.cards[parent].attached_to
    return seen


def attach(state: GameState, a: A.Attach) -> None:
    host = ops.card(state, a.to)
    if ops.zone_name(host.zone) != "battlefield":
        raise ActionError("Attach to a permanent on the battlefield")
    targets = _battlefield_cards(state, a.card_ids)
    for i, c in enumerate(targets):
        if c.id == host.id or c.id in _ancestors(state, host):
            raise ActionError("A card can't be attached to itself or to something attached to it")
        c.attached_to = host.id
        offset = a.offset if a.offset is not None else (10.0 + 10.0 * i, -18.0 - 14.0 * i)
        c.attach_offset = (float(offset[0]), float(offset[1]))
        if c.zone == host.zone:
            c.x, c.y = host.x + c.attach_offset[0], host.y + c.attach_offset[1]
        # draw the attachment underneath its host
        ids = state.zone(host.zone)
        if c.id in ids and host.id in ids:
            ids.remove(c.id)
            ids.insert(ids.index(host.id), c.id)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" attached "), group(state, targets), text(" to "), ops.card_part(state, host)])


def detach(state: GameState, a: A.Detach) -> None:
    targets = ops.cards(state, a.card_ids)
    for c in targets:
        c.attached_to = None
        c.attach_offset = None
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" detached "), group(state, targets)], kind="minor")


def children_of(state: GameState, host_id: str) -> list[CardInstance]:
    """Cards attached to ``host_id``, directly or through other attachments."""
    out: list[CardInstance] = []
    frontier = [host_id]
    while frontier:
        parent = frontier.pop()
        for c in state.cards.values():
            if c.attached_to == parent and c not in out:
                out.append(c)
                frontier.append(c.id)
    return out


# ---------------------------------------------------------------------------- groups


def make_group(state: GameState, a: A.Group) -> None:
    if a.r is None or not a.r.ids:
        raise ActionError("unresolved group")
    targets = _battlefield_cards(state, a.card_ids)
    for c in targets:
        c.group = a.r.ids[0]
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" grouped {len(targets)} cards")], kind="minor")


def ungroup(state: GameState, a: A.Ungroup) -> None:
    targets = ops.cards(state, a.card_ids)
    groups = {c.group for c in targets if c.group}
    for c in state.cards.values():
        if c.group in groups:
            c.group = None
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" ungrouped cards")], kind="minor")


# ---------------------------------------------------------------------------- token stacks


def _stack(state: GameState, card_id: str) -> CardInstance:
    c = ops.card(state, card_id)
    if not c.is_token:
        raise ActionError("Only tokens can form logical stacks")
    return c


def stack_adjust(state: GameState, a: A.StackAdjust) -> None:
    c = _stack(state, a.card_id)
    new = c.quantity + a.delta
    if new <= 0:
        ops.delete(state, c)
        log(state, a.actor, a.ts, [pname(state, a.actor), text(f" removed the last {c.name} token")])
        return
    c.quantity = min(new, 10_000)
    verb = f"added {a.delta}" if a.delta > 0 else f"removed {-a.delta}"
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" {verb} {c.name} (×{c.quantity})")])


def _clone(c: CardInstance, new_id: str, quantity: int, dx: float, dy: float) -> CardInstance:
    clone = c.model_copy(deep=True)
    clone.id = new_id
    clone.quantity = quantity
    clone.x, clone.y = c.x + dx, c.y + dy
    clone.attached_to = None
    clone.attach_offset = None
    clone.group = None
    clone.known_to = [ALL]
    return clone


def split_stack(state: GameState, a: A.SplitStack) -> None:
    c = _stack(state, a.card_id)
    if a.r is None or len(a.r.ids) != 1:
        raise ActionError("unresolved split")
    if a.count >= c.quantity:
        raise ActionError(f"The stack only has {c.quantity}")
    clone = _clone(c, a.r.ids[0], a.count, 22.0, 22.0)
    c.quantity -= a.count
    state.cards[clone.id] = clone
    state.zone(c.zone).append(clone.id)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" split {a.count} {c.name} off the stack")], kind="minor")


def expand_stack(state: GameState, a: A.ExpandStack) -> None:
    c = _stack(state, a.card_id)
    if a.r is None or len(a.r.ids) != c.quantity - 1:
        raise ActionError("unresolved expand (the stack changed?)")
    ids = state.zone(c.zone)
    for i, new_id in enumerate(a.r.ids, start=1):
        clone = _clone(c, new_id, 1, (i % 10) * 16.0, (i // 10) * 22.0 + (i % 10) * 3.0)
        state.cards[new_id] = clone
        ids.append(new_id)
    n = c.quantity
    c.quantity = 1
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" spread out {n} {c.name} tokens")], kind="minor")


def _token_signature(c: CardInstance) -> tuple[object, ...]:
    token = c.token.model_dump() if c.token else None
    return (c.card_id, repr(token), c.controller, c.zone, c.tapped, c.face_down, tuple(sorted(c.counters.items())),
            c.copy_of.source_name if c.copy_of else None)


def merge_tokens(state: GameState, a: A.MergeTokens) -> None:
    targets = ops.cards(state, a.card_ids)
    if any(not c.is_token for c in targets):
        raise ActionError("Only tokens can be stacked — real cards never merge")
    if any(c.protected for c in targets):
        raise ActionError("Protected tokens can't be merged; unprotect them first")
    signatures = {_token_signature(c) for c in targets}
    if len(signatures) > 1:
        raise ActionError("Only identical tokens (same token, controller, tapped state and counters) can be stacked")
    keep = targets[0]
    for c in targets[1:]:
        keep.quantity += c.quantity
        for child in children_of(state, c.id):
            child.attached_to = keep.id
        ops.delete(state, c)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" stacked {keep.name} ×{keep.quantity}")])


# ---------------------------------------------------------------------------- mana


def add_mana(state: GameState, a: A.AddMana) -> None:
    pid = ops.player(state, a.player, a.actor)
    pool = state.players[pid].mana
    for color, amount in a.mana.items():
        value = max(0, pool.get(color, 0) + amount)
        if value:
            pool[color] = value
        else:
            pool.pop(color, None)
    added = "".join(f"{{{c}}}" * n for c in MANA_ORDER for k, n in a.mana.items() if k == c and n > 0)
    log(state, a.actor, a.ts, [pname(state, pid), text(f" added {added or 'mana'} to their mana pool")], kind="mana")


def clear_mana(state: GameState, a: A.ClearMana) -> None:
    pid = ops.player(state, a.player, a.actor)
    state.players[pid].mana = {}
    log(state, a.actor, a.ts, [pname(state, pid), text("'s mana pool emptied")], kind="minor")


def empty_mana_pools(state: GameState) -> None:
    for p in state.players.values():
        p.mana = {}


# ---------------------------------------------------------------------------- reminders


def add_reminder(state: GameState, a: A.AddReminder) -> None:
    if a.r is None or not a.r.ids:
        raise ActionError("unresolved reminder")
    if a.card_id:
        ops.card(state, a.card_id)
    state.reminders.append(
        Reminder(id=a.r.ids[0], owner=a.actor, text=a.text, when=a.when, own_turn_only=a.own_turn_only,
                 card_id=a.card_id, created_seq=state.seq)
    )
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" set a reminder ({a.when.replace('_', ' ')}): {a.text}")], kind="minor")


def dismiss_reminder(state: GameState, a: A.DismissReminder) -> None:
    before = len(state.reminders)
    state.reminders = [r for r in state.reminders if r.id != a.reminder_id]
    if len(state.reminders) == before:
        raise ActionError("No such reminder")


def fire_reminders(state: GameState, when: str, ts: float) -> None:
    for r in state.reminders:
        if r.due or r.when != when or r.created_seq >= state.seq:
            continue
        if r.own_turn_only and state.turn.active_player != r.owner:
            continue
        r.due = True
        log(state, r.owner, ts, [text("⏰ Reminder for "), pname(state, r.owner), text(f": {r.text}")], kind="reminder")


# ---------------------------------------------------------------------------- settings


def configure(state: GameState, a: A.Configure) -> None:
    changed = []
    for key in ("undo_policy", "clear_mana_on_step", "auto_untap", "auto_commander_tax"):
        value = getattr(a, key)
        if value is not None:
            setattr(state.settings, key, value)
            changed.append(f"{key.replace('_', ' ')} = {value}")
    if not changed:
        raise ActionError("Nothing to change")
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" changed settings: " + ", ".join(changed))], kind="info")
