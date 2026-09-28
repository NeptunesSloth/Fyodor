from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.game.actions import Action
from app.game.state import GameState

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Suggestion:
    """Advisory output of a rules module. Never applied automatically."""

    module: str
    message: str
    level: Literal["info", "warning"] = "info"
    card_ids: tuple[str, ...] = ()
    # A suggested action the player may choose to perform (same schema as player actions).
    proposed_action: dict[str, object] | None = None


class RulesModule(Protocol):
    name: str

    def after_action(self, state: GameState, action: Action) -> list[Suggestion]:
        """Inspect the state after ``action`` was applied. Must not mutate ``state``."""
        ...


@dataclass
class RulesRegistry:
    modules: list[RulesModule] = field(default_factory=list)

    def register(self, module: RulesModule) -> None:
        self.modules.append(module)

    def after_action(self, state: GameState, action: Action) -> list[Suggestion]:
        out: list[Suggestion] = []
        for module in self.modules:
            try:
                out.extend(module.after_action(state, action))
            except Exception:  # noqa: BLE001 - an advisory module must never break the table
                log.exception("Rules module %s failed", module.name)
        return out
