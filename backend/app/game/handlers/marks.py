"""Manual tracking on the table: effects, damage, choices, stack notes, exile groups, arrows
and cleanup. Nothing here enforces rules, expires, or happens without a player asking."""

from __future__ import annotations

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.handlers import response
from app.game.handlers.turn import clear_combat_markers
from app.game.ops import group, log, pname, text
from app.game.state import STACK, Arrow, CardInstance, CopyInfo, Effect, GameState, StackInfo
from app.game.visibility import publicly_visible


def _public(state: GameState, cards: list[CardInstance]) -> None:
    for c in cards:
        if ops.zone_name(c.zone) not in ("battlefield", STACK) and c.zone != STACK:
            raise ActionError("Markers go on cards on the battlefield or the stack")


def add_effect(state: GameState, a: A.AddEffect) -> None:
    if a.r is None or len(a.r.ids) < len(a.card_ids):
        raise ActionError("unresolved effect")
    targets = ops.cards(state, a.card_ids)
    _public(state, targets)
    for c, eid in zip(targets, a.r.ids, strict=False):
        c.effects.append(Effect(id=eid, name=a.name, value=a.value, text=a.text, color=a.color))
    label = f"{a.name} {a.value}".strip() if a.value else a.name
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" gave {label} to "), group(state, targets)], kind="minor")


def remove_effect(state: GameState, a: A.RemoveEffect) -> None:
    targets = ops.cards(state, a.card_ids)
    removed = 0
    for c in targets:
        before = len(c.effects)
        c.effects = [] if a.effect_id is None else [e for e in c.effects if e.id != a.effect_id]
        removed += before - len(c.effects)
    if not removed:
        raise ActionError("No such effect")


def set_damage(state: GameState, a: A.SetDamage) -> None:
    targets = ops.cards(state, a.card_ids)
    _public(state, targets)
    if a.value is None and a.delta is None:
        raise ActionError("Give a value or a change")
    for c in targets:
        c.damage = max(0, a.value if a.value is not None else c.damage + (a.delta or 0))
    shown = ", ".join(str(c.damage) for c in targets)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" marked damage on "), group(state, targets), text(f": {shown}")],
        kind="minor")


def set_choice(state: GameState, a: A.SetChoice) -> None:
    c = ops.card(state, a.card_id)
    if a.value:
        c.choices[a.key] = a.value
        if len(c.choices) > 12:
            raise ActionError("That's a lot of choices for one card (12 max)")
        parts = [pname(state, a.actor), text(" recorded for "), ops.card_part(state, c), text(f" — {a.key}: {a.value}")]
    else:
        if c.choices.pop(a.key, None) is None:
            raise ActionError("No such choice")
        parts = [pname(state, a.actor), text(f" cleared {a.key} on "), ops.card_part(state, c)]
    log(state, a.actor, a.ts, parts, kind="minor")


def set_stack_info(state: GameState, a: A.SetStackInfo) -> None:
    c = ops.card(state, a.card_id)
    if c.zone != STACK:
        raise ActionError("X, modes and cast labels are for spells and abilities on the stack")
    info = c.stack_info or StackInfo()
    if a.x is not None:
        info.x = a.x
    if a.clear_x:
        info.x = None
    if a.modes is not None:
        info.modes = [m for m in a.modes if m]
    if a.tags is not None:
        info.tags = [t for t in a.tags if t]
    c.stack_info = info if (info.x is not None or info.modes or info.tags) else None
    bits = ([f"X = {info.x}"] if info.x is not None else []) + info.modes + info.tags
    log(state, a.actor, a.ts, [ops.card_part(state, c), text(": " + (", ".join(bits) or "annotations cleared"))], kind="minor")


def set_exile_group(state: GameState, a: A.SetExileGroup) -> None:
    targets = ops.cards(state, a.card_ids)
    for c in targets:
        if ops.zone_name(c.zone) not in ("exile", "foretell"):
            raise ActionError("Exile groups are for cards in exile")
        c.exile_group = a.group or None
    what = f"“{a.group}”" if a.group else "general exile"
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" filed "), group(state, targets), text(f" under {what}")],
        kind="minor")


def _endpoint(state: GameState, ref: str) -> str:
    if ref in state.players:
        return state.players[ref].name
    c = ops.card(state, ref)
    if not publicly_visible(state, c) and not (c.face_down and ops.zone_name(c.zone) == "battlefield"):
        raise ActionError("Arrows connect public objects and players")
    return c.name if publicly_visible(state, c) else "a face-down card"


def create_arrow(state: GameState, a: A.CreateArrow) -> None:
    if a.r is None or not a.r.ids:
        raise ActionError("unresolved arrow")
    src = _endpoint(state, a.source)
    names = [_endpoint(state, t) for t in a.targets]
    if len(state.arrows) >= 200:
        raise ActionError("Too many arrows on the table — clear some")
    state.arrows.append(Arrow(id=a.r.ids[0], owner=a.actor, source=a.source, targets=list(dict.fromkeys(a.targets)),
                              kind=a.kind, label=a.label))
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f": {src} → {', '.join(names)}" + (f" ({a.label})" if a.label else ""))],
        kind="minor")


def remove_arrow(state: GameState, a: A.RemoveArrow) -> None:
    before = len(state.arrows)
    state.arrows = [ar for ar in state.arrows if ar.id != a.arrow_id]
    if len(state.arrows) == before:
        raise ActionError("No such arrow")


def prune_arrows(state: GameState) -> None:
    """Arrows whose ends left the table disappear (called after zone changes)."""
    def alive(ref: str) -> bool:
        if ref in state.players:
            return not state.players[ref].left
        c = state.cards.get(ref)
        return c is not None and (ops.zone_name(c.zone) == "battlefield" or c.zone == STACK)
    state.arrows = [ar for ar in state.arrows if alive(ar.source) and any(alive(t) for t in ar.targets)]
    for ar in state.arrows:
        ar.targets = [t for t in ar.targets if alive(t)]


def set_copy_source(state: GameState, a: A.SetCopySource) -> None:
    c = ops.card(state, a.card_id)
    src = ops.card(state, a.source_id)
    if src.id == c.id:
        raise ActionError("A card can't copy itself")
    if not publicly_visible(state, src):
        raise ActionError("Copy something everyone can see")
    mods = c.copy_of.modifications if c.copy_of else ""
    c.copy_of = CopyInfo(source_id=src.id, source_name=src.name, modifications=mods)
    c.card_id, c.name = src.card_id, src.name
    if src.token and not src.card_id:
        c.token = src.token.model_copy()
    log(state, a.actor, a.ts, [ops.card_part(state, c), text(" is now copying "), ops.card_part(state, src)])


def cleanup(state: GameState, a: A.Cleanup) -> None:
    scope = set(a.card_ids) if a.card_ids else None
    in_scope = [c for c in state.cards.values() if scope is None or c.id in scope]
    done: list[str] = []
    for what in dict.fromkeys(a.what):
        if what == "combat":
            clear_combat_markers(state)
            done.append("combat")
        elif what == "damage":
            for c in in_scope:
                c.damage = 0
            done.append("damage")
        elif what == "effects":
            for c in in_scope:
                c.effects = []
            done.append("temporary effects")
        elif what == "arrows":
            state.arrows = []
            done.append("arrows")
        elif what == "mana":
            for p in state.players.values():
                p.mana = {}
                p.mana_units = []  # (wave 18B)
            done.append("mana pools")
        elif what == "exile_groups":
            for c in in_scope:
                c.exile_group = None
            done.append("exile groups")
        elif what == "response":
            response.clear(state)
            state.auto_pass = {}
            done.append("response state")
        elif what == "tokens":
            doomed = [c for c in in_scope if c.is_token and not c.protected and c.commander_key is None]
            for c in doomed:
                if c.id in state.cards:
                    ops.delete(state, c)
            prune_arrows(state)
            done.append(f"{len(doomed)} token{'s' if len(doomed) != 1 else ''}")
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" cleared " + ", ".join(done))])
