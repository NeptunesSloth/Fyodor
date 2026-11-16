"""Life, resources, commander damage/tax and table-wide markers."""

from __future__ import annotations

from app.game import actions as A
from app.game import ops
from app.game.errors import ActionError
from app.game.ops import log, pname, text
from app.game.rules_state import emit
from app.game.state import DEFAULT_RESOURCES, GameState, LifeChange, zone_key

LIFE_HISTORY_LIMIT = 200
COMMANDER_DAMAGE_LETHAL = 21
POISON_LETHAL = 10


def change_life(state: GameState, pid: str, new_value: int, *, group: int = 0, paid: bool = False, cause: str | None = None) -> int:
    p = state.players[pid]
    before = p.life
    p.life = new_value
    if new_value != before:  # life loss and life gain are events (damage is a separate one)
        emit(state, "life_loss" if new_value < before else "life_gain", player=pid, amount=abs(new_value - before), **({"group": group} if group and new_value < before else {}), **({"cause110m": cause} if cause and new_value > before else {}))
        if paid and new_value < before:
            emit(state, "life_paid", player=pid, amount=before - new_value)
    last = p.life_history[-1] if p.life_history else None
    # Consecutive clicks on the same player's life collapse into one history step (40 → 35, not 40 → 39 → …).
    if last and last.seq == state.seq - 1 and last.after == before:
        last.after = new_value
        last.seq = state.seq
    else:
        p.life_history.append(LifeChange(turn=state.turn.number, before=before, after=new_value, seq=state.seq))
        del p.life_history[:-LIFE_HISTORY_LIMIT]
    return before


def life(state: GameState, a: A.Life) -> None:
    pid = ops.player(state, a.player, a.actor)
    before = change_life(state, pid, state.players[pid].life + a.delta, group=a.group, paid=a.paid, cause=a.cause110m)
    verb = "gained" if a.delta > 0 else "lost"
    log(state, a.actor, a.ts, [pname(state, pid), text(f" {verb} {abs(a.delta)} life ({before} → {state.players[pid].life})")], kind="life")


def set_life(state: GameState, a: A.SetLife) -> None:
    pid = ops.player(state, a.player, a.actor)
    before = change_life(state, pid, a.value)
    log(state, a.actor, a.ts, [pname(state, pid), text(f"'s life set to {a.value} (was {before})")], kind="life")


def resource(state: GameState, a: A.Resource) -> None:
    pid = ops.player(state, a.player, a.actor)
    p = state.players[pid]
    before = p.resources.get(a.key, 0)
    p.resources[a.key] = before + a.delta
    parts = [pname(state, pid), text(f" {a.key}: {before} → {p.resources[a.key]}")]
    if a.key == "poison" and before < POISON_LETHAL <= p.resources[a.key]:
        parts.append(text(f" — {POISON_LETHAL}+ poison counters!"))
    log(state, a.actor, a.ts, parts)


def set_resource(state: GameState, a: A.SetResource) -> None:
    pid = ops.player(state, a.player, a.actor)
    p = state.players[pid]
    if a.value is None:
        if a.key in DEFAULT_RESOURCES:
            p.resources[a.key] = 0
        else:
            p.resources.pop(a.key, None)
        log(state, a.actor, a.ts, [pname(state, pid), text(f" removed the {a.key} counter")])
        return
    before = p.resources.get(a.key, 0)
    p.resources[a.key] = a.value
    log(state, a.actor, a.ts, [pname(state, pid), text(f" {a.key}: {before} → {a.value}")])


def commander_damage(state: GameState, a: A.CommanderDamage) -> None:
    pid = ops.player(state, a.player, a.actor)
    if not any(c.commander_key == a.commander for c in state.cards.values()):
        raise ActionError("Unknown commander")
    p = state.players[pid]
    before = p.commander_damage.get(a.commander, 0)
    after = max(0, before + a.delta)
    p.commander_damage[a.commander] = after
    name = state.commander_name(a.commander)
    parts = [pname(state, pid), text(f" took {a.delta} commander damage from {name} ({before} → {after})")] if a.delta >= 0 else [
        pname(state, pid), text(f": commander damage from {name} adjusted {before} → {after}")
    ]
    if a.affect_life and after != before:
        change_life(state, pid, p.life - (after - before))
        parts.append(text(f", life {p.life}"))
    if before < COMMANDER_DAMAGE_LETHAL <= after:
        parts.append(text(f" — {COMMANDER_DAMAGE_LETHAL}+ commander damage!"))
    log(state, a.actor, a.ts, parts)


def commander_tax(state: GameState, a: A.CommanderTax) -> None:
    owner = next((c.owner for c in state.cards.values() if c.commander_key == a.commander), None)
    if owner is None:
        raise ActionError("Unknown commander")
    taxes = state.players[owner].commander_tax
    before = taxes.get(a.commander, 0)
    if a.value is not None:
        after = a.value
    elif a.delta is not None:
        after = max(0, before + a.delta)
    else:
        raise ActionError("Give a delta or a value")
    taxes[a.commander] = after
    log(state, a.actor, a.ts, [text(f"Commander tax for {state.commander_name(a.commander)}: {before} → {after}")])


def set_monarch(state: GameState, a: A.SetMonarch) -> None:
    if a.player:
        ops.player(state, a.player, a.actor)
    state.table.monarch = a.player
    log(state, a.actor, a.ts, [pname(state, a.player), text(" became the monarch")] if a.player else [text("No one is the monarch")])


def set_initiative(state: GameState, a: A.SetInitiative) -> None:
    if a.player:
        ops.player(state, a.player, a.actor)
    state.table.initiative = a.player
    log(state, a.actor, a.ts, [pname(state, a.player), text(" took the initiative")] if a.player else [text("No one has the initiative")])


def set_day_night(state: GameState, a: A.SetDayNight) -> None:
    state.table.day_night = a.value
    log(state, a.actor, a.ts, [text(f"It became {a.value}") if a.value else text("Day/night tracking cleared")])


def city_blessing(state: GameState, a: A.CityBlessing) -> None:
    pid = ops.player(state, a.player, a.actor)
    state.players[pid].city_blessing = a.value
    log(state, a.actor, a.ts, [pname(state, pid), text(" got the city's blessing" if a.value else " lost the city's blessing")])


def rename_player(state: GameState, a: A.RenamePlayer) -> None:
    pid = ops.player(state, a.player, a.actor)
    old = state.players[pid].name
    state.players[pid].name = a.name
    log(state, a.actor, a.ts, [text(f"{old} is now called {a.name}")])


def remove_player(state: GameState, a: A.RemovePlayer) -> None:
    """Host tool (API-checked): a player leaves the table for good."""
    pid = ops.player(state, a.player, a.actor)
    if len(state.seat_order) <= 1:
        raise ActionError("The last player can't leave the table")
    name = state.players[pid].name
    for c in list(state.cards.values()):
        if c.id not in state.cards:
            continue
        if c.owner == pid:
            ops.delete(state, c)  # everything they own leaves the game
        elif c.controller == pid and ops.zone_name(c.zone) == "battlefield":
            ops.remove_from_zone(state, c)
            ops.insert(state, c, zone_key(c.owner, "battlefield"))
            c.controller = c.owner
    order = state.seat_order
    if state.turn.active_player == pid:
        state.turn.active_player = order[(order.index(pid) + 1) % len(order)]
        state.turn.phase = "untap"
    state.seat_order = [p for p in order if p != pid]
    state.players[pid].left = True
    if state.pregame is not None:
        state.pregame.seats.pop(pid, None)
    if state.response is not None:
        state.response.waiting = [p for p in state.response.waiting if p != pid]
    for key in ("monarch", "initiative"):
        if getattr(state.table, key) == pid:
            setattr(state.table, key, None)
    log(state, a.actor, a.ts, [text(f"{name} left the table; the cards they own left the game.")])


def set_appearance(state: GameState, a: A.SetAppearance) -> None:
    p = state.players[a.actor]
    if a.clear_sleeve:
        p.sleeve = None
    elif a.sleeve:
        p.sleeve = a.sleeve
    if a.clear_playmat:
        p.playmat = None
    elif a.playmat is not None:
        p.playmat = a.playmat
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" changed their table look")], kind="minor")


def set_table_playmat(state: GameState, a: A.SetTablePlaymat) -> None:
    state.table.playmat = a.playmat
    log(state, a.actor, a.ts, [pname(state, a.actor), text(" changed the table playmat" if a.playmat else " removed the table playmat")],
        kind="minor")


RESTORE_FIELDS = ("players", "seat_order", "cards", "zones", "turn", "table", "arrows", "pregame", "settings", "auto_pass",
                  "planechase")  # (-- planechase -- the planar deck goes back with the settings that say whether there is one)


def restore_state(state: GameState, a: A.RestoreState) -> None:
    """Replace the table with an earlier state. Private views and response checks end; the log
    and the game's secret ordering key stay, so hidden cards stay anonymous afterwards."""
    old = GameState.model_validate(a.state)
    if old.id != state.id:
        raise ActionError("That state belongs to another game")
    for name in RESTORE_FIELDS:
        setattr(state, name, getattr(old, name))
    state.views = []
    state.response = None
    state.passed_at = None
    log(state, a.actor, a.ts, [pname(state, a.actor), text(f" restored the table: {a.label}")])
