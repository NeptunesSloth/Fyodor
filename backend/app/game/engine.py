"""Applies resolved actions to game state (pure and deterministic)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.handlers import cards, marks, mulligan, objects, players, response, rules, solo, turn, zones
from app.game.rules_state import capture, track, wither_put_by
from app.game.state import GameState
from app.rules import stickers101

Handler = Callable[[GameState, Any], None]

HANDLERS: dict[str, Handler] = {
    "rules_sticker101": stickers101.apply_action,
    "draw": zones.draw,
    "move": zones.move,
    "set_position": zones.set_position,
    "shuffle": zones.shuffle,
    "mill": zones.mill,
    "mulligan": zones.mulligan,
    "put_top_face_down": zones.put_top_face_down,
    "mulligan_take": mulligan.take,
    "mulligan_keep": mulligan.keep,
    "mulligan_bottom": mulligan.bottom,
    "mulligan_powder": mulligan.powder,
    "mulligan_finish": mulligan.finish,
    "response_open": response.open_window,
    "response_pass": response.pass_,
    "response_respond": response.respond,
    "response_auto": response.auto,
    "response_close": response.close,
    "reveal": zones.reveal,
    "hide": zones.hide,
    "look_top": zones.look_top,
    "reveal_top": zones.reveal_top,
    "reveal_until": zones.reveal_until,
    "cascade": zones.cascade,
    "fetch_card": zones.fetch_card,
    "discard_random": zones.discard_random,
    "search_start": zones.search_start,
    "search_end": zones.search_end,
    "end_view": zones.end_view,
    "tap": cards.tap,
    "untap_all": cards.untap_all,
    "phase_shift": cards.phase_shift,
    "counter": cards.counter,
    "set_counter": cards.set_counter,
    "create_token": cards.create_token,
    "copy_card": cards.copy_card,
    "delete_card": cards.delete_card,
    "merge": cards.merge,
    "meld": cards.meld,
    "set_face": cards.set_face,
    "flip": cards.flip,
    "face_down": cards.face_down,
    "note": cards.note,
    "set_controller": cards.set_controller,
    "set_commander": cards.set_commander,
    "return_to_owner": cards.return_to_owner,
    "add_effect": marks.add_effect,
    "remove_effect": marks.remove_effect,
    "set_damage": marks.set_damage,
    "set_choice": marks.set_choice,
    "set_stack_info": marks.set_stack_info,
    "set_exile_group": marks.set_exile_group,
    "create_arrow": marks.create_arrow,
    "remove_arrow": marks.remove_arrow,
    "set_copy_source": marks.set_copy_source,
    "cleanup": marks.cleanup,
    "remove_player": players.remove_player,
    "set_appearance": players.set_appearance,
    "restore_state": players.restore_state,
    "run_macro": objects.run_macro,
    "spawn_card": solo.spawn_card,
    "load_deck": solo.load_deck,
    "reset_deck": solo.reset_deck,
    "restart_game": solo.restart_game,
    "set_table_playmat": players.set_table_playmat,
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
    "configure": objects.configure,
    # rules engine: intents replay their compiled steps; the other two are server-built steps
    **{t: rules.apply_intent for t in A.INTENT_TYPES},
    "rules_sync": rules.rules_sync,
    "rules_log": rules.rules_log,
    "rules_mana": rules.rules_mana,
    "rules_damage": rules.rules_damage,
    "rules_life_changes": rules.rules_life_changes,
    "renumber": zones.renumber,
}

# Actions that change nothing worth undoing or logging separately.
UNLOGGED = frozenset({"set_position", "hide"})

# With rules automation on, every other sandbox action is a *manual override*: it still works, and
# the log marks it as done by hand. These don't count: rules intents and their steps, table
# arrangement, annotations, chat/dice, settings, opening hands and the response helper.
NOT_OVERRIDES = A.INTENT_TYPES | A.SERVER_ONLY_TYPES | frozenset({
    "set_position", "hide", "note", "chat", "roll", "coin", "rename_player", "set_appearance", "set_table_playmat",
    "configure", "create_arrow", "remove_arrow", "rotate", "set_lock", "set_protect", "group", "ungroup",
    "add_effect", "remove_effect", "set_choice", "set_stack_info", "set_exile_group", "set_copy_source",
    "mulligan_take", "mulligan_keep", "mulligan_bottom", "mulligan_powder", "mulligan_finish", "response_open", "response_pass",
    "response_respond", "response_auto", "response_close", "restore_state", "end_view",
})


def apply(state: GameState, action: A.Action) -> None:
    """Apply a resolved action in place. On ``ActionError`` the state may be partially
    modified; callers rebuild it from history (see ``history.History``)."""
    handler = HANDLERS.get(action.type)
    if handler is None:  # pragma: no cover - guarded by the discriminated union
        raise ActionError(f"Unknown action {action.type}")
    if action.actor not in state.players or state.players[action.actor].left:
        raise ActionError("Actions must be performed by a seated player")
    state.seq += 1
    log_start = len(state.log)
    # Rules intents (and reconciling settings changes) track each of their own steps.
    before = capture(state) if action.type not in A.INTENT_TYPES and action.type != "configure" else None
    try:
        handler(state, action)
    except ActionError:
        state.seq -= 1
        state.departures().clear()
        state.renames().clear()
        raise
    if state.arrows:
        marks.prune_arrows(state)
    rules = state.rules
    if rules is not None:
        manual = action.type not in NOT_OVERRIDES
        if manual and action.type in ('set_face', 'flip', 'face_down', 'merge'):
            # A manual loss/regain between intents has no native World timing
            # authority, even if its final copiable values match the old ones.
            changed_worlds80 = getattr(action, 'card_ids', None) or [getattr(action, 'card_id', None)]
            for cid80 in changed_worlds80:
                if isinstance(cid80, str):
                    rules.world_intervals80.pop(rules.object_id(cid80), None)
        if manual and state.settings.automation != "off" and not rules.paused:
            rules.overrides += 1
            for entry in state.log[log_start:]:
                entry.manual = True
        elif manual:
            # Automation isn't running: the bookkeeping may drift from the table. Resuming or
            # turning automation back on reconciles (app/rules/reconcile.py).
            rules.unsynced = True
        track(state, before, manual=manual, actor=action.actor, put_by=wither_put_by(action),
              non_discard=bool(getattr(action, "non_discard", False)))  # (actor: wave 5H)
    state.departures().clear()
    state.renames().clear()
