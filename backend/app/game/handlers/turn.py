"""Turn/phase tracking, combat markers, the stack, dice and chat."""

from __future__ import annotations

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.handlers.cards import untap_permanents
from app.game.ops import log, pname, text
from app.game.state import COMBAT_PHASES, PHASES, STACK, AbilityDef, CardInstance, GameState

PHASE_LABELS = {
    "untap": "Untap",
    "upkeep": "Upkeep",
    "draw": "Draw",
    "main1": "Precombat main",
    "begin_combat": "Beginning of combat",
    "declare_attackers": "Declare attackers",
    "declare_blockers": "Declare blockers",
    "combat_damage": "Combat damage",
    "end_combat": "End of combat",
    "main2": "Postcombat main",
    "end": "End step",
    "cleanup": "Cleanup",
}


def clear_combat_markers(state: GameState) -> int:
    n = 0
    for c in state.cards.values():
        if c.attacking or c.blocking:
            c.attacking = None
            c.blocking = None
            n += 1
    return n


def phase(state: GameState, a: A.Phase) -> None:
    current = PHASES.index(state.turn.phase)
    if a.to == "next":
        if current == len(PHASES) - 1:
            raise ActionError("Cleanup is the last step — use Next turn")
        target = current + 1
    elif a.to == "prev":
        if current == 0:
            raise ActionError("Already at the untap step")
        target = current - 1
    else:
        target = PHASES.index(a.to)
    new_phase = PHASES[target]
    if state.turn.phase in COMBAT_PHASES and new_phase not in COMBAT_PHASES:
        clear_combat_markers(state)
    state.turn.phase = new_phase
    log(state, a.actor, a.ts, [text(f"— {PHASE_LABELS[new_phase]} —")], kind="phase")


def next_turn(state: GameState, a: A.NextTurn) -> None:
    order = state.seat_order
    if a.player:
        nxt = ops.player(state, a.player, a.actor)
    else:
        nxt = order[(order.index(state.turn.active_player) + 1) % len(order)]
    clear_combat_markers(state)
    state.turn.number += 1
    state.turn.active_player = nxt
    state.turn.phase = "untap"
    parts = [text(f"Turn {state.turn.number}: "), pname(state, nxt)]
    if state.settings.auto_untap:
        n = untap_permanents(state, nxt)
        if n:
            parts.append(text(f" untapped {n} permanent{'s' if n != 1 else ''}"))
    log(state, a.actor, a.ts, parts, kind="turn")


def attack(state: GameState, a: A.Attack) -> None:
    targets = ops.cards(state, a.card_ids)
    if a.target:
        if a.target.kind == "player":
            ops.player(state, a.target.id, a.actor)
        else:
            ops.card(state, a.target.id)
    for c in targets:
        if ops.zone_name(c.zone) != "battlefield":
            raise ActionError(f"{c.name or 'That card'} is not on the battlefield")
    for c in targets:
        c.attacking = a.target.model_copy() if a.target else None
        if a.target is None:
            for other in state.cards.values():
                if other.blocking == c.id:
                    other.blocking = None
    if a.target is None:
        log(state, a.actor, a.ts, [ops.group(state, targets), text(" stopped attacking")])
        return
    who = pname(state, a.target.id) if a.target.kind == "player" else ops.card_part(state, state.cards[a.target.id])
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" attacks "), who, text(" with "), ops.group(state, targets)])


def block(state: GameState, a: A.Block) -> None:
    c = ops.card(state, a.card_id)
    if ops.zone_name(c.zone) != "battlefield":
        raise ActionError("Blockers must be on the battlefield")
    if a.attacker_id is None:
        c.blocking = None
        log(state, a.actor, a.ts, [ops.card_part(state, c), text(" stopped blocking")])
        return
    attacker = ops.card(state, a.attacker_id)
    c.blocking = attacker.id
    log(state, a.actor, a.ts, [ops.card_part(state, c), text(" blocks "), ops.card_part(state, attacker)])


def clear_combat(state: GameState, a: A.ClearCombat) -> None:
    clear_combat_markers(state)
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" cleared combat")])


def create_ability(state: GameState, a: A.CreateAbility) -> None:
    if a.r is None or not a.r.ids:
        raise ActionError("unresolved ability")
    source = ops.card(state, a.source_id) if a.source_id else None
    new_id = a.r.ids[0]
    ability = AbilityDef(
        text=a.text,
        source_id=source.id if source else None,
        source_card_id=source.card_id if source and ops.visible_to_all_players(state, source) else None,
        source_name=source.name if source and ops.visible_to_all_players(state, source) else None,
        kind=a.kind,
    )
    c = CardInstance(id=new_id, name=ability.source_name or "Ability", owner=a.actor, controller=a.actor, zone=STACK, ability=ability)
    state.cards[new_id] = c
    state.zone(STACK).append(new_id)
    parts = [pname(state, a.actor), text(" put an ability on the stack")]
    if ability.source_name:
        parts.append(text(f" ({ability.source_name})"))
    parts.append(text(f": {a.text}"))
    log(state, a.actor, a.ts, parts)


def resolve_top(state: GameState, a: A.ResolveTop) -> None:
    stack = state.zone(STACK)
    if not stack:
        raise ActionError("The stack is empty")
    top = state.cards[stack[-1]]
    dest = (a.r.destinations.get(top.id) if a.r else None) or "delete"
    part = ops.card_part(state, top)
    if dest == "delete" or ops.is_ephemeral(top) and not dest.endswith(":battlefield"):
        ops.delete(state, top)
        log(state, a.actor, a.ts, [text("Resolved "), part])
        return
    x = y = None
    if a.r and top.id in a.r.positions:
        x, y = a.r.positions[top.id]
    ops.move_card(state, top, dest, x=x, y=y)
    log(state, a.actor, a.ts, [text("Resolved "), part, text(f" → {ops.zone_label(state, dest, top.owner)}")])


def roll(state: GameState, a: A.Roll) -> None:
    if a.r is None or len(a.r.results) != a.count:
        raise ActionError("unresolved roll")
    dice = f"d{a.sides}" if a.count == 1 else f"{a.count}d{a.sides}"
    if a.count == 1:
        msg = f" rolled {a.r.results[0]} on a {dice}"
    else:
        msg = f" rolled {dice}: {', '.join(map(str, a.r.results))} (total {sum(a.r.results)})"
    log(state, a.actor, a.ts, [pname(state, a.actor), text(msg)], kind="dice")


def coin(state: GameState, a: A.Coin) -> None:
    if a.r is None or len(a.r.results) != a.count:
        raise ActionError("unresolved coin flip")
    faces = ["heads" if r else "tails" for r in a.r.results]
    msg = f" flipped a coin: {faces[0]}" if a.count == 1 else f" flipped {a.count} coins: {', '.join(faces)} ({sum(a.r.results)} heads)"
    log(state, a.actor, a.ts, [pname(state, a.actor), text(msg)], kind="dice")


def chat(state: GameState, a: A.Chat) -> None:
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f": {a.text}")], kind="chat")
