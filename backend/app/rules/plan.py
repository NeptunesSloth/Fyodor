"""The scratch table the rules engine works on while compiling one intent."""

from __future__ import annotations

import secrets
from typing import Any

from app.game import actions as A
from app.game.errors import ActionError
from app.game.rules_state import (
    AutomationOptions,
    Decision,
    DecisionOption,
    PlayerPrefs,
    RulesState,
    capture,
    track,
)
from app.game.state import CardInstance, GameState
from app.game.visibility import publicly_visible
from app.rules import characteristics as chars
from app.rules.characteristics import CardInfo, Characteristics

MAX_STEPS = 400  # a safety valve: no single intent may expand into more table actions


class Plan:
    """A scratch copy of the table plus the table actions carried out on it so far."""

    x_choice: int | None = None  # the X announced for the spell being cast, while its targets are chosen (selectors read it)
    # -- cost changers (wave 4I) -- 601.2f: the total cost locked in before the player was asked to pay it; a cast or
    # activation resumed after that payment prompt pays exactly this (casting._rerun), whatever the table says now
    locked_cost: str | None = None

    def __init__(self, state: GameState, actor: str, info: CardInfo, rng: Any) -> None:
        self.state = state.model_copy(deep=True)
        self.actor = actor
        self.info = info
        self.rng = rng
        self.steps: list[dict[str, Any]] = []
        self.max_steps = MAX_STEPS
        self.hold: str | None = None  # a player keeping priority right now (HOLD PRIORITY, a cancelled cast)
        self.probe_903: list[tuple[str, str]] | None = None  # a look ahead for 903.9b (replacements.ask_903_9b_first)

    @classmethod
    def view(cls, state: GameState, actor: str, info: CardInfo) -> Plan:
        """A read-only plan over ``state`` itself (not a copy), for hints that need selectors and
        derived characteristics. It can't carry out anything: ``do`` always refuses."""
        plan = cls.__new__(cls)
        plan.state, plan.actor, plan.info, plan.rng = state, actor, info, None
        plan.steps, plan.max_steps, plan.hold = [], 0, None
        plan.probe_903 = None
        return plan

    @property
    def rules(self) -> RulesState:
        assert self.state.rules is not None
        return self.state.rules

    def do(self, payload: dict[str, Any], *, actor: str | None = None) -> A.Action:
        """Resolve and apply one table action on the scratch copy, and record it."""
        from app.game.engine import HANDLERS  # the game engine imports resolve → this module
        from app.game.resolve import resolve

        if len(self.steps) >= self.max_steps:
            raise ActionError("The rules engine stopped: too many steps for one action")
        if payload.get("type") in ("move", "mill"):
            # Zone-change replacement effects (614): unearth's "exile it instead", "If ~ would die,
            # exile it instead", Rest in Peace-like statics, madness, 903.9b — app/rules/replacements.py
            from app.rules.replacements import replace_move  # (replacements → plan for type hints only)

            payload = replace_move(self, payload, actor)
        action = A.parse_action(payload)
        resolved = resolve(self.state, action, actor=actor or self.actor, cards=self.info, rng=self.rng, trusted=True)
        leaving = self._battlefield_lki(payload)
        before = capture(self.state)
        if before is not None:  # (the turn log: what a permanent was as it left, layers applied)
            before.types = self._battlefield_types(payload)
        entered_before = (self.state.turn.number, len(self.rules.turn_log.entered)) if self.state.rules else None
        HANDLERS[resolved.type](self.state, resolved)
        track(self.state, before)
        if entered_before is not None:  # -- refused modal/conditional (wave 3R1) -- what entered was, as it entered (608.2i)
            log = self.rules.turn_log
            for entry in log.entered[entered_before[1] if log.turn == entered_before[0] else 0:]:
                card = self.state.cards.get(entry.card)
                if entry.types is None and card is not None and self.oid(card) == entry.object_id:
                    now = self.ch(card)
                    entry.types, entry.subtypes = sorted(now.types), sorted(now.subtypes)
        for oid, (pt, abilities, keywords, traits) in leaving.items():  # last known information (608.2h)
            snap = self.rules.lki.get(oid)
            if snap is not None:
                if pt is not None:  # power / toughness
                    snap.power, snap.toughness = pt
                # -- quoted grants (wave 2D) -- its abilities, keywords and types as they last existed (603.10a)
                snap.abilities, snap.keywords, snap.traits = abilities, keywords, traits
        self.steps.append(resolved.model_dump(mode="json"))
        if payload.get("type") == "rules_mana" and self.rules.kept_mana:  # -- refused copy/mana (wave 3R3) --
            from app.rules.kept_mana import clamp  # (never more kept than the pool holds)

            clamp(self.state)
        return resolved

    def _battlefield_types(self, payload: dict[str, Any]) -> dict[str, list[str]]:
        """Card types (layers applied) of the permanents a step may move off the battlefield: "a
        creature died this turn" asks what it was as it last existed there (608.2i, 700.4) — an
        animated land or a crewed Vehicle was a creature, whatever its printed types."""
        out: dict[str, list[str]] = {}
        for cid in payload.get("card_ids") or []:
            card = self.state.cards.get(cid) if isinstance(cid, str) else None
            if card is not None and card.zone.endswith(":battlefield"):
                out[cid] = sorted(self.ch(card).types)
        return out

    def _battlefield_lki(self, payload: dict[str, Any]) -> dict[str, tuple[Any, Any, Any, Any]]:
        """What a step may move off the battlefield looks like right now: the current power /
        toughness of the creatures (608.2h) and — quoted grants, wave 2D — the abilities, keywords
        and types of any permanent when they differ from the printed ones (603.10a: abilities that
        trigger as it leaves look back at the abilities it had; 700.4: an animated land dies as a
        creature)."""
        from app.rules import granted  # (granted → plan for type hints only)

        out: dict[str, tuple[Any, Any, Any, Any]] = {}
        for cid in payload.get("card_ids") or []:
            card = self.state.cards.get(cid) if isinstance(cid, str) else None
            if card is not None and card.zone.endswith(":battlefield"):
                now = self.ch(card)
                abilities, keywords, traits = granted.last_existed(chars.of(card, self.info), now)
                if now.pt is not None or abilities is not None or keywords is not None or traits is not None:
                    out[self.oid(card)] = (now.pt, abilities, keywords, traits)
        return out

    def note(self, message: str, card_ids: list[str] | tuple[str, ...] = (), *, actor: str | None = None) -> None:
        self.do({"type": "rules_log", "text": message, "card_ids": list(card_ids)}, actor=actor)

    def ch(self, card: CardInstance) -> Characteristics:
        """Current characteristics: printed, then continuous effects in layer order."""
        from app.rules.layers import derive  # layers → plan (type hints only)

        return derive(self.state, card, chars.of(card, self.info), self.info)

    def prefs(self, player: str) -> PlayerPrefs:
        """A player's preferences, created on first change (so they're saved with the rules state)."""
        prefs = self.rules.prefs.get(player)
        if prefs is None:
            prefs = self.rules.prefs[player] = PlayerPrefs()
        return prefs

    @property
    def options(self) -> AutomationOptions:
        return self.state.settings.automation_options

    def oid(self, card: CardInstance | str) -> str:
        """The rules object a physical card currently is (it changes on every zone change)."""
        return self.rules.object_id(card if isinstance(card, str) else card.id)

    def in_game(self, card: CardInstance) -> bool:
        """Not left behind by a player who left the game (their side of the table stays as a record)."""
        live = self.live()
        return card.owner in live and card.controller in live

    def manual(self, card: CardInstance) -> bool:
        """Is this card taken out of automation (right-click → Automation → Manual)?"""
        return self.rules.card_mode(card.id) == "manual"

    # -- table helpers ---------------------------------------------------------------
    def name(self, player: str) -> str:
        return self.state.players[player].name

    @property
    def active(self) -> str:
        return self.state.turn.active_player

    @property
    def turn_player(self) -> str:
        """Who makes the active player's choices: the active player, or — when they have left the
        game and their turn goes on without them (800.4j) — the next player in turn order (800.4h)."""
        return self.active if self.active in self.live() else self.after(self.active)

    def has_active_player(self) -> bool:
        """False while a turn goes on without its active player, who left the game (800.4j)."""
        return self.active in self.live()

    def live(self) -> list[str]:
        return live_players(self.state)

    def apnap(self) -> list[str]:
        """Live players in APNAP order (101.4): the active player, then the others in turn order."""
        order = self.state.seat_order
        live = set(self.live())
        start = order.index(self.active) if self.active in order else 0
        return [p for i in range(len(order)) if (p := order[(start + i) % len(order)]) in live]

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
    out = set(state.rules.conceded) | set(state.rules.lost) if state.rules else set()
    return [p for p in state.seat_order if not state.players[p].left and p not in out]


def require_no_decision(plan: Plan) -> None:
    d = plan.rules.decision
    if d is not None:
        raise ActionError(f"Waiting for {plan.name(d.player)}: {d.prompt}")


def require_priority(plan: Plan) -> None:
    if plan.rules.winner is not None:
        raise ActionError(f"The game is over: {plan.name(plan.rules.winner)} won")
    holder = plan.rules.priority
    if holder != plan.actor:
        raise ActionError("You don't have priority" + (f" ({plan.name(holder)} does)" if holder else ""))


def decide(plan: Plan, *, player: str, kind: str, prompt: str, options: list[DecisionOption], resume: dict[str, Any],
           min_choices: int = 1, max_choices: int = 1, source: CardInstance | None = None,
           memory_key: str | None = None, memory_context: str = "", display: dict[str, Any] | None = None) -> None:
    source_id = source.id if source is not None and publicly_visible(plan.state, source) else None
    plan.rules.decision = Decision(
        id=secrets.token_hex(6), player=player, kind=kind, prompt=prompt[:300], options=options,  # type: ignore[arg-type]
        min_choices=min_choices, max_choices=max_choices, source_id=source_id, resume=resume,
        memory_key=memory_key, memory_context=memory_context, display=display,
    )
    plan.rules.priority = None
