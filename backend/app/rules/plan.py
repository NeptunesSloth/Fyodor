"""The scratch table the rules engine works on while compiling one intent."""

from __future__ import annotations

import secrets
from typing import Any

from app.game import actions as A
from app.game.control import controller_of
from app.game.errors import ActionError
from app.game.ops import down_public, seen_move, zone_name
from app.game.rules_state import (
    AutomationOptions,
    Decision,
    DecisionOption,
    PlayerPrefs,
    RulesState,
    capture,
    track,
    wither_put_by,
)
from app.game.state import CardInstance, GameState
from app.game.visibility import publicly_visible
from app.rules import characteristics as chars
from app.rules.characteristics import CardInfo, Characteristics

MAX_STEPS = 400  # a safety valve: no single intent may expand into more table actions
ARROW_TARGETS = 20  # the most objects one arrow points at (A.CreateArrow.targets)
ENGINE_ARROWS = 190  # the engine's target arrows stop here (the table takes 200: handlers/marks.py; the rest is the players')


class Plan:
    """A scratch copy of the table plus the table actions carried out on it so far."""

    x_choice: int | None = None  # the X announced for the spell being cast, while its targets are chosen (selectors read it)
    # -- cost changers (wave 4I) -- 601.2f: the total cost locked in before the player was asked to pay it; a cast or
    # activation resumed after that payment prompt pays exactly this (casting._rerun), whatever the table says now
    locked_cost: str | None = None
    # -- review 22B -- a cost paid as a spell or ability resolves (118.12: "unless …", "you may …"), not one to cast or activate: "Players can't
    # pay life or sacrifice creatures to cast spells or activate abilities" doesn't reach it (Angel of Jubilation ruling 2012-05-01)
    resolution_cost: bool = False
    # -- life payments (wave 29C) -- 119.4: the life a spell's additional costs ("pay X life") will also pay: Phyrexian mana can be paid with
    # life only up to what is left of the life total after it (casting.find_payment ``reserve``)
    reserved_life: int = 0

    def __init__(self, state: GameState, actor: str, info: CardInfo, rng: Any) -> None:
        self.state = state.model_copy(deep=True)
        self.actor = actor
        self.info = info
        self.rng = rng
        self.steps: list[dict[str, Any]] = []
        self.max_steps = MAX_STEPS
        self.hold: str | None = None  # a player keeping priority right now (HOLD PRIORITY, a cancelled cast)
        self.probe_903: list[tuple[str, str]] | None = None  # a look ahead for 903.9b (replacements.ask_903_9b_first)
        # -- review (face-down ids) -- whether each card is face down in view (as the intent began, then after each of its moves)
        self.began: dict[str, bool] | None = {cid: down_public(c) for cid, c in self.state.cards.items()}
        self.moved: dict[str, bool] = {}  # card -> did one of its moves this intent make it a card others have seen (ops.seen_move)

    began: dict[str, bool] | None = None

    def renumber_face_down(self) -> bool:
        """406.3, 708.5: at the end of the intent (so nothing that is still working with the old ids breaks), the cards that became face
        down where others see them get new ids: one recorded step, then the rules state is re-dumped by the caller."""
        if self.began is None:
            return False
        fresh = [cid for cid, seen in self.moved.items() if seen and (c := self.state.cards.get(cid)) is not None and down_public(c)]
        if fresh:
            self.do({"type": "renumber", "card_ids": fresh})
        return bool(fresh)

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
        from app.rules import (
            graveyard_order,  # (-- graveyard order (wave 40C) -- 404.3: graveyard_order → plan)
        )

        if len(self.steps) >= self.max_steps:
            raise ActionError("The rules engine stopped: too many steps for one action")
        if payload.get("type") in ("move", "mill"):
            # Zone-change replacement effects (614): unearth's "exile it instead", "If ~ would die,
            # exile it instead", Rest in Peace-like statics, madness, 903.9b — app/rules/replacements.py
            from app.rules.replacements import replace_move  # (replacements → plan for type hints only)

            payload = graveyard_order.unordered(self, replace_move(self, payload, actor))
        if payload.get("type") in ("move", "mill", "put_top_face_down"):
            payload = {**payload, "keep_ids": True}  # (renumber_face_down)
        if payload.get("type") == "rules_sync" and self.renumber_face_down():
            payload = {**payload, "rules": self.rules.model_dump(mode="json")}  # (the ids changed)
        action = A.parse_action(payload)
        resolved = resolve(self.state, action, actor=actor or self.actor, cards=self.info, rng=self.rng, trusted=True)
        leaving = self._battlefield_lki(payload)
        before = capture(self.state) if resolved.type != "renumber" else None
        if before is not None:  # (the turn log: what a permanent was as it left, layers applied)
            before.types = self._battlefield_types(payload)
        entered_before = (self.state.turn.number, len(self.rules.turn_log.entered)) if self.state.rules else None
        gy_seen = graveyard_order.before(self, payload)
        HANDLERS[resolved.type](self.state, resolved)
        if before is not None and self.began is not None:
            for cid, zone in before.zones.items():
                if (c := self.state.cards.get(cid)) is not None and zone_name(zone) != zone_name(c.zone):
                    was, self.began[cid] = self.began.get(cid, False), down_public(c)
                    self.moved[cid] = self.moved.get(cid, False) or seen_move(zone, c.zone, was)
        track(self.state, before, actor=resolved.actor or None, group=getattr(resolved, "group", 0),
              put_by=wither_put_by(resolved), declared=getattr(resolved, "declared", False))  # (5H, 7C, 17D; 45C: the attack declaration's tap)
        if gy_seen is not None:  # (wave 40C) two or more cards into one graveyard at once: its owner may arrange them (404.3)
            graveyard_order.after(self, gy_seen)
        if entered_before is not None:  # -- refused modal/conditional (wave 3R1) -- what entered was, as it entered (608.2i)
            log = self.rules.turn_log
            for entry in log.entered[entered_before[1] if log.turn == entered_before[0] else 0:]:
                card = self.state.cards.get(entry.card)
                if entry.types is None and card is not None and self.oid(card) == entry.object_id:
                    now = self.ch(card)
                    entry.types, entry.subtypes = sorted(now.types), sorted(now.subtypes)
        for oid, (pt, abilities, keywords, traits, base) in leaving.items():  # last known information (608.2h)
            snap = self.rules.lki.get(oid)
            if snap is not None:
                if pt is not None:  # power / toughness
                    snap.power, snap.toughness = pt
                if base is not None:  # (wave 30J) and the base ones, 208.4b
                    snap.base_power, snap.base_toughness = base
                # -- quoted grants (wave 2D) -- its abilities, keywords and types as they last existed (603.10a)
                snap.abilities, snap.keywords, snap.traits = abilities, keywords, traits
        self.state.renames().clear()
        self.steps.append(resolved.model_dump(mode="json"))
        if payload.get("type") == "rules_mana" and self.rules.kept_mana:  # -- refused copy/mana (wave 3R3) --
            from app.rules.kept_mana import clamp  # (never more kept than the pool holds)

            clamp(self.state)
        return resolved

    def target_arrows(self, source: str, ids: Any, *, actor: str | None = None) -> None:
        """-- target limits (wave 29C) -- the arrows from a spell or ability to its targets: one arrow points at up to 20 objects
        (``CreateArrow``), so a spell with more targets ("up to X target …", "any number of target …") gets several. (review 29C: arrows only
        show the targets: past ``ENGINE_ARROWS`` on the table none are added, as the table refuses more than 200 and that would refuse the
        cast or the resolution itself)"""
        # (-- cast keywords (wave 43D) -- a target paid as a cost, "Kicker—Sacrifice an artifact or Goblin." with the Goblin chosen as the target (Goblin
        # Barrage's ruling), is a token that ceased to exist (111.7): no arrow to a thing that isn't on the table)
        ids = [i for i in dict.fromkeys(ids) if i in self.state.cards or i in self.state.players]
        for i in range(0, len(ids), ARROW_TARGETS):
            if len(self.state.arrows) >= ENGINE_ARROWS:
                return
            self.do({"type": "create_arrow", "source": source, "targets": ids[i:i + ARROW_TARGETS], "kind": "target"}, actor=actor)

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

    def _battlefield_lki(self, payload: dict[str, Any]) -> dict[str, tuple[Any, Any, Any, Any, Any]]:
        """What a step may move off the battlefield looks like right now: the current power /
        toughness of the creatures (608.2h) and — quoted grants, wave 2D — the abilities, keywords
        and types of any permanent when they differ from the printed ones (603.10a: abilities that
        trigger as it leaves look back at the abilities it had; 700.4: an animated land dies as a
        creature)."""
        from app.rules import granted  # (granted → plan for type hints only)

        out: dict[str, tuple[Any, Any, Any, Any, Any]] = {}
        for cid in payload.get("card_ids") or []:
            card = self.state.cards.get(cid) if isinstance(cid, str) else None
            if card is not None and card.zone.endswith(":battlefield"):
                now = self.ch(card)
                abilities, keywords, traits = granted.last_existed(chars.of(card, self.info), now)
                if now.pt is not None or abilities is not None or keywords is not None or traits is not None:
                    out[self.oid(card)] = (now.pt, abilities, keywords, traits, now.base_pt)
        return out

    def note(self, message: str, card_ids: list[str] | tuple[str, ...] = (), *, actor: str | None = None) -> None:
        from app.game.ops import shown  # (review 18F: a granter is read as its name, never its object id)

        self.do({"type": "rules_log", "text": shown(self.state, message), "card_ids": list(card_ids)}, actor=actor)

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
           memory_key: str | None = None, memory_context: str = "", display: dict[str, Any] | None = None, decider: str | None = None) -> None:
    from app.game.ops import shown  # (review 18F: a granter is read as its name)

    source_id = source.id if source is not None and publicly_visible(plan.state, source) else None
    options = [o.model_copy(update={"label": shown(plan.state, o.label)}) if "‹" in o.label else o for o in options]
    plan.rules.decision = Decision(
        id=secrets.token_hex(6), player=player, kind=kind, prompt=shown(plan.state, prompt)[:300], options=options,  # type: ignore[arg-type]
        min_choices=min_choices, max_choices=max_choices, source_id=source_id, resume=resume,
        memory_key=memory_key, memory_context=memory_context, display=display,
        # -- controlling another player (wave 18H) -- 723.5: who makes this choice for ``player`` (None: they do)
        decider=(by if (by := decider or controller_of(plan.state, player)) != player else None),
    )
    plan.rules.priority = None
