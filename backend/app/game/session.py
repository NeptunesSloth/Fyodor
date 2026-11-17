"""A running game: current state + history + out-of-band notices (undo/redo, joins)."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import ValidationError

from app.cards.repository import CardRepository, RulesCards
from app.game import autoseat, dummy, engine, out_of_game, table_rights, undo_requests, undo_rights
from app.game.actions import INTENT_TYPES, Action, parse_action
from app.game.control import is_controlled
from app.game.errors import ActionError, AutomationError
from app.game.history import History
from app.game.ops import pname, text
from app.game.resolve import CardInfo, NoCardInfo, resolve
from app.game.state import GameState, LogEntry, LogPart
from app.game.views import build_view
from app.rules import RulesRegistry, Suggestion, taught

log = logging.getLogger(__name__)

NOTICE_LIMIT = 200
# -- controlling another player (wave 18H) -- what a controlled player may still send (723.5, 723.6): their rules intents
# (routed or refused by the engine; a concede always goes through), their own stops, and table chatter. Every other table
# tool would make a choice the controller makes, so it waits until the control ends (or the host pauses automation).
CONTROLLED_MAY = (INTENT_TYPES - {"set_card_automation"}) | {"chat", "set_position", "end_view", "rename_player",
                                                            "set_appearance", "set_table_playmat"}


def describe(action: Action) -> str:
    return action.type.replace("_", " ")


class GameSession:
    def __init__(self, state: GameState, *, cards: CardInfo | None = None, history: History | None = None,
                 history_limit: int = 500, rules: RulesRegistry | None = None) -> None:
        self.state = state
        if history is None and state.taught is None:  # -- Teach Fyodor -- a new game keeps the taught library it started with
            state.taught = taught.snapshot()
        cards = taught.unwrap(cards)
        # the rules read card data through the repository's cache (no image checks): CardRepository.rules_card
        self.cards = taught.wrap(RulesCards(cards) if isinstance(cards, CardRepository) else cards, state.taught)
        self.rules = rules
        self.suggestions: list[Suggestion] = []
        self.history = history or History(state, limit=history_limit)
        self.notices: list[LogEntry] = []
        self.updated_at = time.time()
        # Named table snapshots ("Before board wipe"): kept beside the game, saved with it.
        self.table_snapshots: list[dict[str, Any]] = []
        self.rules_failure: dict[str, Any] | None = None  # the last unexpected rules-engine failure
        self.undo_request: undo_requests.UndoRequest | None = None  # -- quick undo request -- waiting for the table (in memory)
        self._answering = False  # -- target dummy -- the server is answering for the dummy (app/game/dummy.py)
        self._dummy_gave_up: list[dict[str, Any]] | None = None  # the answers it last couldn't give (said once)
        self._bot_acting = False  # -- test opponent -- the server is playing for an opponent (app/game/bot.py)
        self.bot_memory: dict[str, Any] = {}  # -- test opponent -- what it tried this priority window (in memory: never replayed)

    # -- actions ---------------------------------------------------------------------
    def perform(self, actor: str, payload: dict[str, Any] | Action, *, trusted: bool = False, host: bool = False) -> Action:
        """Validate, resolve, apply and record one action. Raises ActionError / ValidationError.

        ``trusted`` is only for actions the server builds itself (e.g. restoring a snapshot). ``host``: the actor counts as the
        host for the table's card permissions (the host's seat at a LAN table, every seat at a hot-seat one; app/game/table_rights.py)."""
        if actor not in self.state.players:
            raise ActionError("Only seated players can act")
        action = parse_action(payload) if isinstance(payload, dict) else payload
        if not trusted and action.type not in CONTROLLED_MAY:
            self._check_not_controlled(actor)
        if not trusted and (out := out_of_game.refusal(self.state, actor, action.type)) is not None:
            raise ActionError(out)  # -- out of the game -- 800.4a: a player who left no longer takes part
        if not trusted and not self._answering and dummy.is_dummy(self.state, actor):
            raise ActionError("The target dummy acts on its own")  # (a hot-seat table can act as any seat: not as this one)
        if not trusted and not self._bot_acting and autoseat.is_bot(self.state, actor):
            raise ActionError("That opponent plays on its own")  # -- test opponent -- (app/game/bot.py)
        was, rng = undo_requests.before(self.state), undo_requests.Recorder()  # -- quick undo request --
        try:
            resolved = resolve(self.state, action, actor=actor, cards=self.cards, trusted=trusted, rng=rng)
        except ActionError:
            raise
        except Exception as exc:
            if action.type not in INTENT_TYPES and action.type != "configure":
                raise
            # A rules bug must never break game night: compiling works on a scratch copy, so
            # nothing was applied. Remember the failure for EXPORT RULES SCENARIO.
            log.exception("Rules engine failed on %s", action.type)
            self.rules_failure = {
                "intent": action.model_dump(mode="json", exclude={"r"}), "actor": actor, "seq": self.state.seq,
                "error": f"{type(exc).__name__}: {exc}"[:500], "at": time.time(),
            }
            raise AutomationError(
                f"{AutomationError.PREFIX}: Fyodor couldn't carry out {action.type.replace('_', ' ')}. Nothing changed. "
                "Resolve it manually with the table tools, pause automation, or export a rules scenario."
            ) from exc
        if not trusted:  # -- table permissions -- on the resolved action: placeholders are real ids, a macro's steps filled in
            table_rights.check(self.state, resolved, actor, host=host)
        try:
            engine.apply(self.state, resolved)
        except ActionError:
            self.state = self.history.rebuild()
            raise
        except Exception:
            log.exception("Unexpected error applying %s; restoring state", resolved.type)
            self.state = self.history.rebuild()
            raise
        resolved.shown = undo_requests.classify(resolved, was, self.state, rng.used)  # -- quick undo request --
        self.history.record(resolved, self.state)
        self.suggestions = self.rules.after_action(self.state, resolved) if self.rules else []
        self.updated_at = time.time()
        self._drop_stale_request()
        if not self._answering:
            self._answer_for_dummy()
        return resolved

    def _answer_for_dummy(self) -> None:
        """-- target dummy -- answer for the dummy until nothing waits for it (app/game/dummy.py): recorded actions of its own, after
        the action that put the question to it. A question it can't answer is left to the table (pause automation, or Reset dummy)."""
        suggestions = self.suggestions  # (the player's own action's suggestions stay the ones shown)
        self._answering = True
        try:
            for _ in range(dummy.MAX_ANSWERS):
                todo = dummy.to_answer(self.state, self.cards)
                if todo is None:
                    self._dummy_gave_up = None
                    return
                pid, tries = todo
                for payload in tries:
                    try:
                        self.perform(pid, payload, host=True)
                        break
                    except (ActionError, ValidationError):
                        continue
                    except Exception:  # noqa: BLE001 - the player's own action is already applied: never fail it for the dummy
                        log.exception("The target dummy's answer failed: %s", payload.get("type"))
                        continue
                else:
                    if tries != self._dummy_gave_up:  # (said once; tried again after each action: the table may have changed)
                        self._notice(None, [pname(self.state, pid), text(" can't answer this by itself. Pause automation to go on by "
                                                                             "hand, or use Reset dummy.")])
                    self._dummy_gave_up = tries
                    return
            log.warning("The target dummy answered %d times in a row; stopping", dummy.MAX_ANSWERS)
        finally:
            self._answering = False
            self.suggestions = suggestions

    def perform_bot(self, actor: str, payload: dict[str, Any]) -> Action:
        """-- test opponent -- one action the server plays for an opponent (app/game/bot.py): an ordinary recorded action of its own."""
        self._bot_acting = True
        try:
            return self.perform(actor, payload, host=True)
        finally:
            self._bot_acting = False

    def _glued(self, end: int) -> int:
        """-- target dummy -- how many of the history's actions just before position ``end`` are the dummy's answers: they go with the
        player's action they answered, so undo and redo take them back and put them back together with it. -- test opponent -- so do an
        opponent's plays: they follow from the player's action before them (passing into its turn), and the server would play them again
        at once after an undo of them alone."""
        n = 0
        while end - n > 1 and autoseat.non_human(self.state, self.history.actions[end - n - 1].actor):
            n += 1
        return n

    def _check_not_controlled(self, actor: str) -> None:
        if is_controlled(self.state, actor):
            raise ActionError("Another player is making your choices right now (you can still concede)")

    def undo(self, actor: str, *, host: bool = False, others: list[str] | None = None, approved: str | None = None) -> Action:
        """``host``: the actor counts as the host for the table's undo setting (see app/game/undo_rights.py).
        -- quick undo request -- ``others``: who would approve a request from ``actor`` (None at a hot-seat table): when there is
        someone to ask, an undo of something already seen asks them first. ``approved``: the table approved this undo (its label)."""
        self._check_not_controlled(actor)
        glued = self._glued(self.history.cursor)  # -- target dummy -- its answers on top go back with the action they answered
        if approved is None:
            if (out := out_of_game.history_refusal(self.state, actor, host=host)) is not None:
                raise ActionError(out)  # -- out of the game (gaps5) -- a player who left doesn't take the game's actions back (the host may)
            self.history.cursor -= glued  # (the checks are about that action, not the dummy's answers)
            try:
                undo_rights.check(self.state, self.history, actor, host=host, op="undo")  # -- undo policy (gap 3) --
                if others and (kind := undo_requests.shown(undo_rights.entry(self.history, "undo"))) is not None:
                    raise ActionError(f"{undo_requests.reason(kind)} Ask the table to undo it.")
            finally:
                self.history.cursor += glued
        if glued:
            state, gone = self.history.undo_to(self.history.cursor - glued - 1)
            undone = gone[0]
        else:
            state, undone = self.history.undo()
        self.state = state
        said = f" undid: {describe(undone)}" if approved is None else f" undid: {approved} (with the table's approval)"
        self._notice(actor, [pname(self.state, actor), text(said)])
        self._drop_stale_request()
        return undone

    def undo_to(self, actor: str, position: int, *, host: bool = False, others: list[str] | None = None) -> list[Action]:
        """-- undo back to here -- take back every action after history ``position`` at once (a whole combat, a whole turn), under
        the same rules as undoing them one at a time: the table's undo setting must allow each of them, and when there is someone to
        ask, none may have shown hidden information or a random result (those still go one at a time, through a request, or the
        host's Restore from here)."""
        self._check_not_controlled(actor)
        if (out := out_of_game.history_refusal(self.state, actor, host=host)) is not None:
            raise ActionError(out)
        while 0 <= position < self.history.cursor and autoseat.non_human(self.state, self.history.actions[position].actor):
            position += 1  # -- target dummy -- its answers stay with the action they answered
        if not 0 <= position < self.history.cursor:
            raise ActionError("Nothing to undo back to there")
        policy = self.state.settings.undo_policy
        for i, a in enumerate(self.history.actions[position:self.history.cursor], start=position + 1):
            if autoseat.non_human(self.state, a.actor):
                continue  # (the dummy's answers and an opponent's plays go with the action they followed)
            if policy == "host" and not host:
                raise ActionError("Only the host may undo at this table (the host's undo setting).")
            if policy == "own" and a.actor != actor:
                raise ActionError(f"Players may only undo their own actions at this table: #{i} ({describe(a)}) was another player's.")
            if others and (kind := undo_requests.shown(a)) is not None:
                raise ActionError(f"{undo_requests.reason(kind)} (#{i}, {describe(a)}) Undo up to it one action at a time, or ask the host"
                                  " to restore from there.")
        state, undone = self.history.undo_to(position)
        self.state = state
        self._notice(actor, [pname(self.state, actor), text(f" undid {len(undone)} action{'s' if len(undone) != 1 else ''} back to #{position}")])
        self._drop_stale_request()
        return undone

    def redo(self, actor: str, *, host: bool = False) -> Action:
        self._check_not_controlled(actor)
        if (out := out_of_game.history_refusal(self.state, actor, host=host)) is not None:
            raise ActionError(out)  # -- out of the game (gaps5) --
        undo_rights.check(self.state, self.history, actor, host=host, op="redo")  # -- undo policy (gap 3) --
        state, redone = self.history.redo(self.state)
        while self.history.can_redo and autoseat.non_human(state, self.history.actions[self.history.cursor].actor):
            state, _ = self.history.redo(state)  # -- target dummy -- its answers come back with the action they answered
        self.state = state
        self._notice(actor, [pname(self.state, actor), text(f" redid: {describe(redone)}")])
        self._drop_stale_request()
        return redone

    def _drop_stale_request(self) -> None:
        """-- quick undo request -- any change to the table ends a request (it would no longer take back the last action)."""
        req = self.undo_request
        if req is not None and not req.current(self.history):
            self.undo_request = None
            self._notice(None, [pname(self.state, req.by), text(f"'s undo request ({req.label}) was cancelled: the table moved on.")])

    def notice(self, message: str, actor: str | None = None) -> None:
        self._notice(actor, [text(message)])

    def _notice(self, actor: str | None, parts: list[LogPart]) -> None:
        self.notices.append(
            LogEntry(seq=self.state.seq, ts=time.time(), turn=self.state.turn.number, phase=self.state.turn.phase,
                     actor=actor, parts=parts, kind="system")
        )
        del self.notices[:-NOTICE_LIMIT]
        self.updated_at = time.time()

    # -- views -----------------------------------------------------------------------
    @contextmanager
    def reading(self) -> Iterator[None]:
        """-- big boards (views) -- one read pass for several views of the table as it is now (a broadcast builds one per viewer): the
        characteristics every view derives are worked out once, not once per viewer. What a pass keeps is the table's (a player's own
        answers are kept under that player), and the block must not change the table."""
        if self.state.rules is None or self.cards is None:
            yield
            return
        from app.rules import read_pass

        with read_pass.scope(self.state, self.cards):
            yield

    def view(self, viewer: str, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        info = {
            "can_undo": self.history.can_undo,
            "can_redo": self.history.can_redo,
            "suggestions": [{"module": x.module, "message": x.message, "level": x.level} for x in self.suggestions],
            **(meta or {}),
        }
        view = build_view(self.state, viewer, extra_log=self.notices, meta=info)
        pregame = self.state.pregame
        seat = pregame.seats.get(viewer) if pregame is not None and not pregame.finished else None
        if seat is not None and seat.status == "deciding" and view.get("pregame"):  # -- opening hand (wave 18C) -- 103.5b, own hand only
            from app.rules.opening_hand import powder_cards

            if powder := powder_cards(self.state, viewer, self.cards or NoCardInfo()):
                view["pregame"]["mine"] = {"powder": powder}
        if self.state.rules is not None:
            from app.rules.view import rules_view  # only needed for tables with rules automation

            rules = rules_view(self.state, viewer, self.cards or NoCardInfo())
            if rules is not None:
                if self.rules_failure is not None:  # public: what failed, not the error internals
                    rules["failure"] = {"intent": self.rules_failure["intent"]["type"], "at": self.rules_failure["at"]}
                view["rules"] = rules
        return view


__all__ = ["ActionError", "GameSession", "ValidationError"]
