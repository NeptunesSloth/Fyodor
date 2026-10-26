"""Applying rules-engine output. Pure replay: nothing here runs rules code.

A rules intent (``play_land``, ``pass_priority``, …) was compiled by ``app.rules.engine`` into
ordinary table actions, recorded on the intent as ``r``. Applying the intent replays exactly those
steps, so undo/redo, saves and history replay never depend on the current rules code.
"""

from __future__ import annotations

from typing import Any

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.handlers.players import change_life
from app.game.ops import log, text
from app.game.rules_state import RulesState, capture, emit, track, wither_put_by
from app.game.state import GameState, LogPart, ManaUnit

_NOT_A_STEP = A.INTENT_TYPES | {"run_macro", "restore_state", "response_open"}


def apply_intent(state: GameState, a: A.Action) -> None:
    steps = getattr(a, "r", None)
    if not steps:
        raise ActionError("unresolved rules intent")
    replay_steps(state, steps)


def replay_steps(state: GameState, steps: list[dict[str, Any]]) -> None:
    """Apply recorded rules steps, with the same per-step bookkeeping the engine did."""
    from app.game.engine import HANDLERS  # the engine imports this module

    for payload in steps:
        step = A.parse_action(payload)
        if step.type in _NOT_A_STEP or step.type == "configure":
            raise ActionError("Invalid rules step")
        before = capture(state) if step.type != "renumber" else None  # (a renumbered card is no zone change)
        HANDLERS[step.type](state, step)
        track(state, before, actor=step.actor or None, group=getattr(step, "group", 0), put_by=wither_put_by(step))  # (5H, 7C, 17D)
        state.renames().clear()


def rules_sync(state: GameState, a: A.RulesSync) -> None:
    state.rules = RulesState.model_validate(a.rules) if a.rules is not None else None


def rules_mana(state: GameState, a: A.RulesMana) -> None:
    if a.empty_all:
        for p in state.players.values():
            p.mana = {}
            p.mana_units = []  # (wave 18B)
        return
    player = state.players.get(a.player)
    if player is None:
        raise ActionError("Unknown player")
    tapped = []
    for cid in a.tap:
        card = ops.card(state, cid)
        if card.tapped:
            raise ActionError(f"{card.name or 'That card'} is already tapped")
        card.tapped = True
        tapped.append(card)
        # A same-action sacrifice hides this intermediate tap from the final-state diff.
        if cid in a.sacrifice:
            emit(state, "tapped", object_id=state.rules.object_id(cid) if state.rules else cid,
                 card=cid, actor=a.actor)
    # -- mana provenance (wave 18B) -- units spent, added, or emptied (the plain pool below is the rest)
    if a.spend_units:
        gone = set(a.spend_units)
        if not gone <= {u.id for u in player.mana_units}:
            raise ActionError("That mana isn't in the pool")
        player.mana_units = [u for u in player.mana_units if u.id not in gone]
    if a.empty_units:
        player.mana_units = [u for u in player.mana_units if u.id in set(a.keep_units)]
    for raw in a.add_units:
        player.mana_seq += 1
        player.mana_units.append(ManaUnit(id=player.mana_seq, **raw))
    pool = player.mana
    for color, amount in a.delta.items():
        value = pool.get(color, 0) + amount
        if value < 0:
            raise ActionError("Not enough mana in the pool")
        if value:
            pool[color] = value
        else:
            pool.pop(color, None)
    if a.life:
        change_life(state, a.player, player.life - a.life)
    if a.label:
        parts = [ops.pname(state, a.player), text(" " + a.label)]
        if tapped:
            parts += [text(" (tapped "), ops.group(state, tapped), text(")")]
        log(state, a.actor, a.ts, parts, kind="mana")
    for cid in a.sacrifice:
        card = ops.card(state, cid)
        # 701.21a: sacrificed to pay for a mana ability (a Treasure …): "whenever you sacrifice …"
        emit(state, "sacrificed", object_id=state.rules.object_id(cid) if state.rules else cid, card=cid,
             player=card.controller)
        if card.is_token:
            ops.delete(state, card)
        else:
            ops.move_card(state, card, f"{card.owner}:graveyard")


def rules_life_changes(state:GameState,action:A.RulesLifeChanges)->None:
    from app.game import ops
    from app.game.handlers.players import change_life

    pieces=[]
    for change in action.changes:
        pid=ops.player(state,change.player,action.actor)
        before=change_life(state,pid,state.players[pid].life+change.delta,group=action.group)
        pieces.extend([ops.pname(state,pid),ops.text(f' {"gains" if change.delta>0 else "loses"} {abs(change.delta)} life ({before} → {state.players[pid].life}); ')])
    ops.log(state,action.actor,action.ts,[ops.text('Life totals: '),*pieces],kind='life')


def rules_damage(state: GameState, a: A.RulesDamage) -> None:
    # Damage is an event of its own (not "change life"): a player dealt damage also loses that
    # much life, a creature gets marked damage, a planeswalker loses loyalty. All of one step's
    # damage is dealt simultaneously (one event batch).
    stack = state.rules.stack if state.rules is not None else {}
    for d in a.dealt:
        spell = next((c for c in state.zones.get("stack", []) if c in stack and state.rules is not None and state.rules.object_id(c) == d.source), None)
        emit(state, "damage", source_targets=[t.id for t in stack[spell].targets] if spell is not None else None,
             object_id=d.target_object, card=d.target if d.target in state.cards else None,
             player=d.target if d.target in state.players else None, source=d.source, amount=d.amount, combat=a.combat,
             excess=d.excess, pair110c=(state.rules.pairs.get(d.target_object) or [None])[0] if state.rules is not None and d.target_object else None, actor=d.source_controller, attacking_player=d.attacking_player if a.combat else None)
        if a.combat and d.amount > 0 and d.target in state.players and state.rules is not None:
            for name in d.creature_names:
                named_hits = state.rules.named_combat_damage.setdefault(name, [])
                if d.target not in named_hits:
                    named_hits.append(d.target)
        if d.amount > 0 and d.source and state.rules is not None:  # -- as long as (wave 35D) -- 120.3: "hasn't dealt (combat) damage yet"
            for mark in (d.source, d.source + "+combat" if a.combat else ""):
                if mark and mark not in state.rules.dealt_damage:
                    state.rules.dealt_damage.append(mark)
    hurt = []
    for cid, n in a.creatures.items():
        card = ops.card(state, cid)
        card.damage += n
        hurt.append(card)
    for cid, n in a.wither.items():  # wither / infect (702.80, 702.90): -1/-1 counters instead of damage
        card = ops.card(state, cid)
        card.counters["-1/-1"] = card.counters.get("-1/-1", 0) + n
        hurt.append(card)
    walkers = []
    for cid, n in a.planeswalkers.items():
        card = ops.card(state, cid)
        left = card.counters.get("loyalty", 0) - n
        if left > 0:
            card.counters["loyalty"] = left
        else:
            card.counters.pop("loyalty", None)
        walkers.append(card)
    for hit in a.commander:
        p = state.players[hit.player]
        p.commander_damage[hit.commander] = p.commander_damage.get(hit.commander, 0) + hit.amount
    for pid, n in a.players.items():
        change_life(state, pid, state.players[pid].life - n)
    for pid, n in a.poison.items():  # infect: poison counters instead of life loss
        p = state.players[pid]
        p.resources["poison"] = p.resources.get("poison", 0) + n
    # Lifelink (702.15b, e): each source with lifelink causes its own life gain event (119.9), so
    # "whenever you gain life" triggers once per source. Keyed by the source card (its controller
    # gains); a player key is one gain for that player (older recordings, one noncombat source).
    gained: dict[str, int] = {}
    for key, n in a.lifelink.items():
        source = state.cards.get(key)
        pid = key if key in state.players else source.controller if source is not None else ""
        if pid not in state.players or n <= 0:
            continue
        change_life(state, pid, state.players[pid].life + n, cause=a.lifelink_cause110m.get(key))  # (wave 110M) a spell's lifelink
        gained[pid] = gained.get(pid, 0) + n
    parts = [text("First-strike combat damage: " if a.first_strike else "Combat damage: " if a.combat else "Damage: ")]
    pieces: list[list[LogPart]] = [[ops.pname(state, pid), text(f" takes {n}")] for pid, n in a.players.items()]
    pieces += [[ops.pname(state, pid), text(f" gets {n} poison")] for pid, n in a.poison.items()]
    if hurt:
        pieces.append([ops.group(state, hurt), text(" dealt damage")])
    if walkers:
        pieces.append([ops.group(state, walkers), text(" lose loyalty")])
    pieces += [[ops.pname(state, pid), text(f" gains {n} life (lifelink)")] for pid, n in gained.items()]
    for i, piece in enumerate(pieces or [[text("none")]]):
        parts += ([text("; ")] if i else []) + piece
    log(state, a.actor, a.ts, parts, kind="combat")


def rules_log(state: GameState, a: A.RulesLog) -> None:
    if a.fold:
        for entry in state.log[-a.fold:]:
            entry.folded = True
    from app.game.visibility import mask_face_down  # -- keyword actions & face-down (wave 3F) -- 708.5

    parts = [text(mask_face_down(state, a.text, refs=a.card_ids))]
    for cid in a.card_ids:
        if cid in state.cards:
            parts += [text(" "), ops.card_part(state, state.cards[cid])]
    log(state, a.actor, a.ts, parts, kind=a.kind)
