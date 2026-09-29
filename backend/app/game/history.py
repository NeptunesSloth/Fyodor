"""Undo/redo by deterministic replay.

``History`` keeps the base state, every resolved action, a cursor, and periodic snapshots.
Undo rebuilds the state at ``cursor - 1`` from the nearest snapshot and replays the
remaining actions; because every action carries its resolved randomness (shuffle order,
dice, new ids) the rebuilt state is identical to the original, including library order.
"""

from __future__ import annotations

import logging
from typing import Any

from app.game import engine
from app.game.actions import ACTION_ADAPTER, Action
from app.game.errors import ActionError
from app.game.state import GameState

log = logging.getLogger(__name__)

SNAPSHOT_EVERY = 20


class History:
    def __init__(self, base: GameState, *, limit: int = 500) -> None:
        self.limit = max(SNAPSHOT_EVERY * 2, limit)
        self.base_seq = base.seq
        self.base: dict[str, Any] = base.model_dump(mode="json")
        self.actions: list[Action] = []
        self.cursor = 0  # number of actions currently applied (relative to base)
        self.snapshots: dict[int, dict[str, Any]] = {}

    # -- recording -------------------------------------------------------------------
    def record(self, action: Action, state_after: GameState) -> None:
        """Remember an action that has just been applied successfully."""
        if self.cursor < len(self.actions):
            del self.actions[self.cursor :]
            self.snapshots = {k: v for k, v in self.snapshots.items() if k <= self.cursor}
        self.actions.append(action)
        self.cursor += 1
        if self.cursor % SNAPSHOT_EVERY == 0:
            self.snapshots[self.cursor] = state_after.model_dump(mode="json")
        if len(self.actions) > self.limit:
            self._trim()

    def _trim(self) -> None:
        """Drop the oldest actions, re-basing on a snapshot."""
        keep_from = min((k for k in self.snapshots if k >= len(self.actions) - self.limit), default=None)
        if keep_from is None or keep_from == 0:
            return
        self.base = self.snapshots[keep_from]
        self.base_seq = int(self.base["seq"])
        self.actions = self.actions[keep_from:]
        self.cursor -= keep_from
        self.snapshots = {k - keep_from: v for k, v in self.snapshots.items() if k > keep_from}

    # -- navigation ------------------------------------------------------------------
    @property
    def can_undo(self) -> bool:
        return self.cursor > 0

    @property
    def can_redo(self) -> bool:
        return self.cursor < len(self.actions)

    def state_at(self, position: int) -> GameState:
        if not 0 <= position <= len(self.actions):
            raise ActionError("No such history position")
        start = max((k for k in self.snapshots if k <= position), default=0)
        state = GameState.model_validate(self.snapshots[start] if start else self.base)
        for action in self.actions[start:position]:
            engine.apply(state, action)
        return state

    def undo(self) -> tuple[GameState, Action]:
        if not self.can_undo:
            raise ActionError("Nothing to undo")
        undone = self.actions[self.cursor - 1]
        self.cursor -= 1
        return self.state_at(self.cursor), undone

    def redo(self, current: GameState) -> tuple[GameState, Action]:
        if not self.can_redo:
            raise ActionError("Nothing to redo")
        action = self.actions[self.cursor]
        engine.apply(current, action)
        self.cursor += 1
        if self.cursor % SNAPSHOT_EVERY == 0:
            self.snapshots[self.cursor] = current.model_dump(mode="json")
        return current, action

    def rebuild(self) -> GameState:
        """Recover the current state (used after a failed, partially applied action)."""
        return self.state_at(self.cursor)

    # -- persistence -----------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "base": self.base,
            "actions": [a.model_dump(mode="json") for a in self.actions],
            "cursor": self.cursor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, limit: int = 500) -> History:
        base = GameState.model_validate(data["base"])
        history = cls(base, limit=limit)
        history.actions = [ACTION_ADAPTER.validate_python(a) for a in data.get("actions", [])]
        history.cursor = max(0, min(int(data.get("cursor", len(history.actions))), len(history.actions)))
        # Rebuild snapshots lazily by replaying once.
        state = GameState.model_validate(history.base)
        for i, action in enumerate(history.actions, start=1):
            engine.apply(state, action)
            if i % SNAPSHOT_EVERY == 0:
                history.snapshots[i] = state.model_dump(mode="json")
        return history
