"""A running game: current state + history + out-of-band notices (undo/redo, joins)."""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import ValidationError

from app.game import engine
from app.game.actions import Action, parse_action
from app.game.errors import ActionError
from app.game.history import History
from app.game.ops import pname, text
from app.game.resolve import CardInfo, resolve
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

    # -- actions ---------------------------------------------------------------------
    def perform(self, actor: str, payload: dict[str, Any] | Action) -> Action:
        """Validate, resolve, apply and record one action. Raises ActionError / ValidationError."""
        if actor not in self.state.players:
            raise ActionError("Only seated players can act")
        action = parse_action(payload) if isinstance(payload, dict) else payload
        resolved = resolve(self.state, action, actor=actor, cards=self.cards)
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
        return build_view(self.state, viewer, extra_log=self.notices, meta=info)


__all__ = ["ActionError", "GameSession", "ValidationError"]
