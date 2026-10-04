"""A running game: current state + history + out-of-band notices (undo/redo, joins)."""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import ValidationError

from app.game import engine
from app.game.actions import INTENT_TYPES, Action, parse_action
from app.game.errors import ActionError, AutomationError
from app.game.history import History
from app.game.ops import pname, text
from app.game.resolve import CardInfo, NoCardInfo, resolve
from app.game.state import GameState, LogEntry, LogPart
from app.game.views import build_view
from app.rules import RulesRegistry, Suggestion

log = logging.getLogger(__name__)

NOTICE_LIMIT = 200


def describe(action: Action) -> str:
    return action.type.replace("_", " ")


class GameSession:
    def __init__(self, state: GameState, *, cards: CardInfo | None = None, history: History | None = None,
                 history_limit: int = 500, rules: RulesRegistry | None = None) -> None:
        self.state = state
        self.cards = cards
        self.rules = rules
        self.suggestions: list[Suggestion] = []
        self.history = history or History(state, limit=history_limit)
        self.notices: list[LogEntry] = []
        self.updated_at = time.time()
        # Named table snapshots ("Before board wipe"): kept beside the game, saved with it.
        self.table_snapshots: list[dict[str, Any]] = []
        self.rules_failure: dict[str, Any] | None = None  # the last unexpected rules-engine failure

    # -- actions ---------------------------------------------------------------------
    def perform(self, actor: str, payload: dict[str, Any] | Action, *, trusted: bool = False) -> Action:
        """Validate, resolve, apply and record one action. Raises ActionError / ValidationError.

        ``trusted`` is only for actions the server builds itself (e.g. restoring a snapshot)."""
        if actor not in self.state.players:
            raise ActionError("Only seated players can act")
        action = parse_action(payload) if isinstance(payload, dict) else payload
        try:
            resolved = resolve(self.state, action, actor=actor, cards=self.cards, trusted=trusted)
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
        try:
            engine.apply(self.state, resolved)
        except ActionError:
            self.state = self.history.rebuild()
            raise
        except Exception:
            log.exception("Unexpected error applying %s; restoring state", resolved.type)
            self.state = self.history.rebuild()
            raise
        self.history.record(resolved, self.state)
        self.suggestions = self.rules.after_action(self.state, resolved) if self.rules else []
        self.updated_at = time.time()
        return resolved

    def undo(self, actor: str) -> Action:
        state, undone = self.history.undo()
        self.state = state
        self._notice(actor, [pname(self.state, actor), text(f" undid: {describe(undone)}")])
        return undone

    def redo(self, actor: str) -> Action:
        state, redone = self.history.redo(self.state)
        self.state = state
        self._notice(actor, [pname(self.state, actor), text(f" redid: {describe(redone)}")])
        return redone

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
