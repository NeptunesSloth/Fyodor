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

    def __init__(self, state: GameState, actor: str, info: CardInfo, rng: Any) -> None:
        self.state = state.model_copy(deep=True)
        self.actor = actor
        self.info = info
        self.rng = rng
        self.steps: list[dict[str, Any]] = []
        self.max_steps = MAX_STEPS
        self.hold: str | None = None  # a player keeping priority right now (HOLD PRIORITY, a cancelled cast)

    @classmethod
    def view(cls, state: GameState, actor: str, info: CardInfo) -> Plan:
        """A read-only plan over ``state`` itself (not a copy), for hints that need selectors and
        derived characteristics. It can't carry out anything: ``do`` always refuses."""
        plan = cls.__new__(cls)
        plan.state, plan.actor, plan.info, plan.rng = state, actor, info, None
        plan.steps, plan.max_steps, plan.hold = [], 0, None
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
        if payload.get("type") == "move" and self.rules.exile_if_leaves:
            payload = self._exile_instead(payload, actor)
        if payload.get("type") == "move" and (payload.get("to") or {}).get("zone") == "graveyard":
            payload = self._madness(payload, actor)
        action = A.parse_action(payload)
        resolved = resolve(self.state, action, actor=actor or self.actor, cards=self.info, rng=self.rng, trusted=True)
        leaving = self._battlefield_pt(payload)
        before = capture(self.state)
        HANDLERS[resolved.type](self.state, resolved)
        track(self.state, before)
        for oid, (p, t) in leaving.items():  # last known power / toughness (608.2h)
            snap = self.rules.lki.get(oid)
            if snap is not None:
                snap.power, snap.toughness = p, t
        self.steps.append(resolved.model_dump(mode="json"))
        return resolved

    def _battlefield_pt(self, payload: dict[str, Any]) -> dict[str, tuple[int, int]]:
        """Current power / toughness of the creatures a step may move off the battlefield."""
        out: dict[str, tuple[int, int]] = {}
        for cid in payload.get("card_ids") or []:
            card = self.state.cards.get(cid) if isinstance(cid, str) else None
            if card is not None and card.zone.endswith(":battlefield"):
                pt = self.ch(card).pt
                if pt is not None:
                    out[self.oid(card)] = pt
        return out

    def _exile_instead(self, payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
        """Unearth (702.84a): "If it would leave the battlefield, exile it instead of putting it
        anywhere else." Those cards are moved to exile separately; the rest move as asked."""
        dest = payload.get("to") or {}
        if dest.get("zone") in ("exile", "battlefield"):
            return payload
        r = self.rules
        leaving = [c for c in payload["card_ids"] if c in self.state.cards
                   and self.state.cards[c].zone.endswith(":battlefield") and r.object_id(c) in r.exile_if_leaves]
        if not leaving:
            return payload
        r.exile_if_leaves = [o for o in r.exile_if_leaves if o not in {r.object_id(c) for c in leaving}]
        for c in leaving:
            owner = self.state.cards[c].owner
            self.do({"type": "move", "card_ids": [c], "to": {"player": owner, "zone": "exile"}}, actor=actor)
        rest = [c for c in payload["card_ids"] if c not in leaving]
        return {**payload, "card_ids": rest} if rest else {"type": "rules_log", "text": "Exiled instead (unearth)",
                                                            "card_ids": leaving}

    def _madness(self, payload: dict[str, Any], actor: str | None) -> dict[str, Any]:
        """702.35a madness: "If you discard this card, discard it into exile" (a card going from a
        hand to a graveyard is a discard here); then its owner may cast it for its madness cost."""
        from app.rules.casting import MADNESS, keyword_cost  # casting → plan

        hits = []
        for cid in payload["card_ids"]:
            card = self.state.cards.get(cid)
            if card is None or not card.zone.endswith(":hand") or self.manual(card):
                continue
            cost = keyword_cost(self.ch(card), "madness", MADNESS)
            if cost is not None:
                hits.append((cid, cost))
        if not hits:
            return payload
        from app.rules.triggers import _add

        for cid, cost in hits:
            card = self.state.cards[cid]
            self.do({"type": "move", "card_ids": [cid], "to": {"player": card.owner, "zone": "exile"}}, actor=actor)
            self.rules.free_casts.append(cid)
            self.rules.alt_costs[cid] = cost
            _add(self, controller=card.owner, source_card=cid, source_object=self.oid(cid), name=card.name, index=8000,
                 definition={"kind": "triggered", "trigger": "madness", "optional": False, "target": None,
                             "effects": [{"do": "madness_offer", "card": cid, "cost": cost}]})
        rest = [c for c in payload["card_ids"] if c not in {h[0] for h in hits}]
        return {**payload, "card_ids": rest} if rest else {"type": "rules_log", "text": "Discarded into exile (madness)",
                                                            "card_ids": [h[0] for h in hits]}

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
