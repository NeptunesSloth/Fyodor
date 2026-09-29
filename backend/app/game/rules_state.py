"""Rules-automation state stored on the table (``GameState.rules``).

Only what the table itself can't show lives here: who has priority, the pending decision,
per-turn bookkeeping and so on. Physical facts (zones, tapped, counters, damage, control, life)
stay on the table, and characteristics (current types, power/toughness, abilities) are derived
on demand by ``app.rules.characteristics``. A manual override therefore can't put the two out
of sync; the next computation simply sees the new table.

The behaviour lives in ``app.rules``; this module is data only, so ``GameState`` can include it
without importing the rules engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.game.state import GameState

DecisionKind = Literal[
    "manual_resolution",  # an effect Fyodor doesn't automate: resolve it by hand, then Done
    "declare_attackers",  # answered with the declare_attackers intent
    "declare_blockers",  # answered with the declare_blockers intent
    "choose_one",  # pick exactly one option (modes, "which player", …)
    "choose_cards",  # pick between min and max cards (targets, discard, …)
    "confirm",  # yes / no ("you may …")
]


class DecisionOption(BaseModel):
    id: str = Field(max_length=64)
    label: str = Field(max_length=200)
    card_id: str | None = None  # a card the option refers to (only sent to the chooser)


class Decision(BaseModel):
    """One pending choice, addressed to one player. Everyone else only sees that they're waiting."""

    id: str
    player: str
    kind: DecisionKind
    prompt: str = Field(max_length=300)
    options: list[DecisionOption] = Field(default_factory=list)
    min_choices: int = 1
    max_choices: int = 1
    source_id: str | None = None  # the card this is about (public only if the card is)
    # Server-only continuation: which rules step to run with the answer and its arguments.
    # Never sent to any client.
    resume: dict[str, Any] | None = None


class TurnCount(BaseModel):
    """A per-player counter that is only meaningful during one turn (it resets itself)."""

    turn: int = 0
    count: int = 0


class ControlMark(BaseModel):
    """When a permanent came under its current controller's control (for summoning sickness)."""

    controller: str
    turn: int


class Stops(BaseModel):
    """Steps where the engine stops to give a player priority; elsewhere it passes for them
    while the stack is empty (Arena-style). The active player's first main phase is always a
    stop, so a turn can't run past everyone."""

    own: list[str] = Field(default_factory=lambda: ["main1", "main2"])
    others: list[str] = Field(default_factory=list)
    hold_priority: bool = False  # after casting, keep priority instead of passing (Arena's "full control")
    smart_pass: bool = True  # with something on the stack, pass for me if I have nothing to respond with


class RulesState(BaseModel):
    paused: bool = False  # the host paused automation: intents are refused, the sandbox works
    step: str = ""  # "<turn>:<phase>" the engine last acted in; a mismatch means a manual step change
    priority: str | None = None  # player who may act
    passed: list[str] = Field(default_factory=list)  # players who passed in succession
    decision: Decision | None = None
    stops: dict[str, Stops] = Field(default_factory=dict)
    lands_played: dict[str, TurnCount] = Field(default_factory=dict)
    spells_cast: dict[str, TurnCount] = Field(default_factory=dict)
    loyalty_used: dict[str, int] = Field(default_factory=dict)  # planeswalker -> turn it last used a loyalty ability
    once_per_turn: dict[str, int] = Field(default_factory=dict)  # "<card>:<ability>" -> turn it was activated
    turn_seen: int = 0  # last turn number the bookkeeping saw
    turn_started: dict[str, int] = Field(default_factory=dict)  # player -> number of their latest turn
    controlled_since: dict[str, ControlMark] = Field(default_factory=dict)
    conceded: list[str] = Field(default_factory=list)
    lost: dict[str, str] = Field(default_factory=dict)  # player -> why (0 life, poison, …)
    winner: str | None = None
    drew_from_empty: list[str] = Field(default_factory=list)  # loses at the next state-based check
    deathtouched: list[str] = Field(default_factory=list)  # creatures dealt damage by a deathtouch source
    # Combat bookkeeping; the attack/block markers on the table are the visible truth.
    blocked: list[str] = Field(default_factory=list)  # attackers that became blocked (stay blocked)
    no_attackers: bool = False  # nobody attacked: skip blockers and damage (rule 508.8)
    blockers_pending: list[str] = Field(default_factory=list)  # defending players still to declare
    combat_round: Literal["", "first", "done"] = ""
    # Commanders offered the move to the command zone, and from which zone (asked once per arrival).
    commander_offered: dict[str, str] = Field(default_factory=dict)
    overrides: int = 0  # manual (sandbox) actions taken while automation was on

    def lands_this_turn(self, player: str, turn: int) -> int:
        entry = self.lands_played.get(player)
        return entry.count if entry and entry.turn == turn else 0

    def spells_this_turn(self, player: str, turn: int) -> int:
        entry = self.spells_cast.get(player)
        return entry.count if entry and entry.turn == turn else 0

    def stops_for(self, player: str) -> Stops:
        return self.stops.get(player) or Stops()


def start_rules(state: GameState) -> RulesState:
    """Turn automation on for a table: the active player gets priority in the current step, and
    permanents already on the battlefield count as long-controlled (no summoning sickness)."""
    rules = RulesState(
        step=f"{state.turn.number}:{state.turn.phase}",
        priority=state.turn.active_player,
        turn_seen=state.turn.number,
        turn_started={state.turn.active_player: state.turn.number},
        controlled_since={
            cid: ControlMark(controller=c.controller, turn=0)
            for cid, c in state.cards.items()
            if c.zone.endswith(":battlefield")
        },
    )
    state.rules = rules
    return rules


def track(state: GameState) -> None:
    """Deterministic bookkeeping after every applied action (sandbox or rules): note whose turn
    started when, and when each permanent came under its controller's control. Pure: it reads
    only the table, so replaying history reproduces it exactly."""
    rules = state.rules
    if rules is None:
        return
    if rules.turn_seen != state.turn.number:
        rules.turn_seen = state.turn.number
        rules.turn_started[state.turn.active_player] = state.turn.number
    on_battlefield: set[str] = set()
    for card_id, card in state.cards.items():
        if not card.zone.endswith(":battlefield"):
            continue
        on_battlefield.add(card_id)
        mark = rules.controlled_since.get(card_id)
        if mark is None or mark.controller != card.controller:
            rules.controlled_since[card_id] = ControlMark(controller=card.controller, turn=state.turn.number)
    for card_id in [c for c in rules.controlled_since if c not in on_battlefield]:
        del rules.controlled_since[card_id]
