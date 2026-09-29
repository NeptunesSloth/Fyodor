"""The scratch table the rules engine works on while compiling one intent."""

from __future__ import annotations

import secrets
from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import Decision, DecisionOption, RulesState, track
from app.game.state import CardInstance, GameState
from app.game.visibility import publicly_visible
from app.rules import characteristics as chars
from app.rules.characteristics import CardInfo, Characteristics

MAX_STEPS = 400  # a safety valve: no single intent may expand into more table actions


class Plan:
    """A scratch copy of the table plus the table actions carried out on it so far."""

    def __init__(self, state: GameState, actor: str, info: CardInfo, rng: Any) -> None:
        self.state = state.model_copy(deep=True)
        self.actor = actor
        self.info = info
        self.rng = rng
        self.steps: list[dict[str, Any]] = []

    @property
    def rules(self) -> RulesState:
        assert self.state.rules is not None
        return self.state.rules

    def do(self, payload: dict[str, Any], *, actor: str | None = None) -> A.Action:
        """Resolve and apply one table action on the scratch copy, and record it."""
        from app.game.engine import HANDLERS  # the game engine imports resolve → this module
        from app.game.resolve import resolve

        if len(self.steps) >= MAX_STEPS:
            raise ActionError("The rules engine stopped: too many steps for one action")
        action = A.parse_action(payload)
        resolved = resolve(self.state, action, actor=actor or self.actor, cards=self.info, rng=self.rng, trusted=True)
        HANDLERS[resolved.type](self.state, resolved)
        track(self.state)
        self.steps.append(resolved.model_dump(mode="json"))
        return resolved

    def note(self, message: str, card_ids: list[str] | tuple[str, ...] = (), *, actor: str | None = None) -> None:
        self.do({"type": "rules_log", "text": message, "card_ids": list(card_ids)}, actor=actor)

    def ch(self, card: CardInstance) -> Characteristics:
        return chars.of(card, self.info)

    # -- table helpers ---------------------------------------------------------------
    def name(self, player: str) -> str:
        return self.state.players[player].name

    @property
    def active(self) -> str:
        return self.state.turn.active_player

    def live(self) -> list[str]:
        return live_players(self.state)

    def after(self, player: str) -> str:
        """The next live player after ``player`` in turn order."""
        order = self.state.seat_order
        live = set(self.live())
        start = order.index(player) if player in order else -1
        for i in range(1, len(order) + 1):
            p = order[(start + i) % len(order)]
            if p in live:
                return p
        return player


def live_players(state: GameState) -> list[str]:
    conceded = set(state.rules.conceded) if state.rules else set()
    return [p for p in state.seat_order if not state.players[p].left and p not in conceded]


def require_no_decision(plan: Plan) -> None:
    d = plan.rules.decision
    if d is not None:
        raise ActionError(f"Waiting for {plan.name(d.player)}: {d.prompt}")


def require_priority(plan: Plan) -> None:
    holder = plan.rules.priority
    if holder != plan.actor:
        raise ActionError("You don't have priority" + (f" ({plan.name(holder)} does)" if holder else ""))


def decide(plan: Plan, *, player: str, kind: str, prompt: str, options: list[DecisionOption], resume: dict[str, Any],
           min_choices: int = 1, max_choices: int = 1, source: CardInstance | None = None) -> None:
    source_id = source.id if source is not None and publicly_visible(plan.state, source) else None
    plan.rules.decision = Decision(
        id=secrets.token_hex(6), player=player, kind=kind, prompt=prompt[:300], options=options,  # type: ignore[arg-type]
        min_choices=min_choices, max_choices=max_choices, source_id=source_id, resume=resume,
    )
    plan.rules.priority = None
