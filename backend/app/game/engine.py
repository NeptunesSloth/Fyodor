"""Applies resolved actions to game state (pure and deterministic)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.handlers import cards, mulligan, objects, players, turn, zones
from app.game.state import GameState

Handler = Callable[[GameState, Any], None]

HANDLERS: dict[str, Handler] = {
    "draw": zones.draw,
    "move": zones.move,
    "set_position": zones.set_position,
    "shuffle": zones.shuffle,
    "mill": zones.mill,
    "mulligan": zones.mulligan,
    "mulligan_take": mulligan.take,
    "mulligan_keep": mulligan.keep,
    "mulligan_bottom": mulligan.bottom,
    "mulligan_finish": mulligan.finish,
    "reveal": zones.reveal,
    "hide": zones.hide,
    "look_top": zones.look_top,
    "reveal_top": zones.reveal_top,
    "search_start": zones.search_start,
    "search_end": zones.search_end,
    "end_view": zones.end_view,
    "tap": cards.tap,
    "untap_all": cards.untap_all,
    "counter": cards.counter,
    "set_counter": cards.set_counter,
    "create_token": cards.create_token,
    "copy_card": cards.copy_card,
    "delete_card": cards.delete_card,
    "set_face": cards.set_face,
    "flip": cards.flip,
    "face_down": cards.face_down,
    "note": cards.note,
    "set_controller": cards.set_controller,
    "set_commander": cards.set_commander,
    "life": players.life,
    "set_life": players.set_life,
    "resource": players.resource,
    "set_resource": players.set_resource,
    "commander_damage": players.commander_damage,
    "commander_tax": players.commander_tax,
    "set_monarch": players.set_monarch,
    "set_initiative": players.set_initiative,
    "set_day_night": players.set_day_night,
    "city_blessing": players.city_blessing,
    "rename_player": players.rename_player,
    "roll": turn.roll,
    "coin": turn.coin,
    "chat": turn.chat,
    "phase": turn.phase,
    "next_turn": turn.next_turn,
    "attack": turn.attack,
    "block": turn.block,
    "clear_combat": turn.clear_combat,
    "create_ability": turn.create_ability,
    "resolve_top": turn.resolve_top,
    "rotate": objects.rotate,
    "set_lock": objects.set_lock,
    "set_protect": objects.set_protect,
    "attach": objects.attach,
    "detach": objects.detach,
    "group": objects.make_group,
    "ungroup": objects.ungroup,
    "stack_adjust": objects.stack_adjust,
    "split_stack": objects.split_stack,
    "expand_stack": objects.expand_stack,
    "merge_tokens": objects.merge_tokens,
    "add_mana": objects.add_mana,
    "clear_mana": objects.clear_mana,
    "add_reminder": objects.add_reminder,
    "dismiss_reminder": objects.dismiss_reminder,
    "configure": objects.configure,
}

# Actions that change nothing worth undoing or logging separately.
UNLOGGED = frozenset({"set_position", "hide"})


def apply(state: GameState, action: A.Action) -> None:
    """Apply a resolved action in place. On ``ActionError`` the state may be partially
    modified; callers rebuild it from history (see ``history.History``)."""
    handler = HANDLERS.get(action.type)
    if handler is None:  # pragma: no cover - guarded by the discriminated union
        raise ActionError(f"Unknown action {action.type}")
    if action.actor not in state.players:
        raise ActionError("Actions must be performed by a seated player")
    state.seq += 1
    try:
        handler(state, action)
    except ActionError:
        state.seq -= 1
        raise
