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
    "reconcile",  # one answer per question (options grouped by ``group``) after manual play
    "order",  # choose every option, in order (trigger order, library order)
]


class DecisionOption(BaseModel):
    id: str = Field(max_length=64)
    label: str = Field(max_length=200)
    card_id: str | None = None  # a card the option refers to (only sent to the chooser)
    group: str | None = Field(default=None, max_length=64)  # reconcile: the question this answers


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
    # "Always yes this turn" and friends: the prompt's identity and the situation it was asked in.
    # A remembered answer only applies to the same key in the same context. Server-only.
    memory_key: str | None = None
    memory_context: str = ""
    # Server-only continuation: which rules step to run with the answer and its arguments.
    # Never sent to any client.
    resume: dict[str, Any] | None = None
    # Presentation hints for the decider's prompt (e.g. a payment's suggested sources), shown only
    # to the player deciding. Never needed to resolve the decision.
    display: dict[str, Any] | None = None


class TurnCount(BaseModel):
    """A per-player counter that is only meaningful during one turn (it resets itself)."""

    turn: int = 0
    count: int = 0


class ControlMark(BaseModel):
    """When a permanent came under its current controller's control (for summoning sickness)."""

    controller: str
    turn: int


# -- automation levels and options ---------------------------------------------------------
AutomationLevel = Literal["off", "assisted", "full"]
Highlights = Literal["off", "subtle", "full"]


class AutomationOptions(BaseModel):
    """Per-feature automation switches. The levels are presets of these; changing any single
    option makes the table's preset "custom" (see ``preset_name``)."""

    auto_mana_payment: bool = False  # pay without asking when one payment is clearly right
    auto_combat_damage: bool = False  # deal combat damage without a confirmation
    auto_sba: bool = False  # perform state-based actions without a confirmation
    auto_priority_pass: bool = False  # pass for players per their RESPONSE setting (else: stop everyone)
    auto_cleanup: bool = False  # cleanup step: discard to hand size and remove damage
    auto_token_creation: bool = False  # supported effects create their tokens (M16)
    auto_counters: bool = False  # supported effects put their counters (M16)
    auto_trigger_stacking: bool = False  # supported triggers go on the stack by themselves (M16)
    auto_shuffle: bool = False  # supported effects shuffle when they say so (M16)
    highlights: Highlights = "off"  # legal-action highlights (the table default; players may override locally)


AUTOMATION_PRESETS: dict[str, AutomationOptions] = {
    "off": AutomationOptions(),
    # ASSISTED: the engine understands the rules and prepares everything, players confirm the
    # important steps (payments, state-based actions, combat damage, created objects).
    "assisted": AutomationOptions(auto_priority_pass=True, auto_cleanup=True, auto_shuffle=True, highlights="subtle"),
    "full": AutomationOptions(
        auto_mana_payment=True, auto_combat_damage=True, auto_sba=True, auto_priority_pass=True, auto_cleanup=True,
        auto_token_creation=True, auto_counters=True, auto_trigger_stacking=True, auto_shuffle=True, highlights="full",
    ),
}
PRESET_LABELS = {"off": "sandbox", "assisted": "assisted", "full": "full"}


def preset_name(level: str, options: AutomationOptions) -> str:
    """"sandbox" / "assisted" / "full", or "custom" when the options differ from the level's preset."""
    if level == "off":
        return "sandbox"
    return PRESET_LABELS[level] if options == AUTOMATION_PRESETS[level] else "custom"


# -- per-player automation preferences --------------------------------------------------------
Response = Literal["off", "auto", "on"]
# Temporary "pass until …" overrides. Whatever is set, the player still gets every decision that
# is theirs (targets, blockers, discard…), and a forced stop always wins.
PassUntil = Literal[
    "next_action",  # until another player does something (casts, activates, plays, attacks)
    "stack_changes",  # until an object is added to or leaves the stack ("resolve one")
    "stack_empty",  # until the stack is empty ("resolve all until decision")
    "next_step",  # until the next step or phase
    "next_turn",  # until the next turn
    "my_turn",  # until my next turn
    "combat",  # until combat begins
]
Payment = Literal["auto", "ask", "manual"]
SourceProtection = Literal["prefer", "save"]  # "normal" is the absence of an entry
TriggerAutoResolve = Literal["off", "safe", "on"]
YieldKind = Literal["always_yield", "yes_this_turn", "no_this_turn"]


class Yield(BaseModel):
    """A remembered answer ("always yes this turn" …). ``key`` names the ability/prompt,
    ``context`` fingerprints the situation it was given in: a different context voids it."""

    kind: YieldKind
    key: str = Field(max_length=120)
    context: str = Field(default="", max_length=200)
    turn: int = 0  # for the *_this_turn kinds


class PlayerPrefs(BaseModel):
    # RESPONSE: OFF passes whenever the rules allow, AUTO stops at your stops and when you could
    # respond, ON stops at every priority (for bluffing). See docs/AUTOMATION_UX.md.
    response: Response = "auto"
    # Magic-style stops, used by RESPONSE AUTO while the stack is empty. The active player's first
    # main phase is always a stop (so a turn can't run past its owner) unless RESPONSE is OFF and
    # they have nothing at all to do.
    stops_my_turn: list[str] = Field(default_factory=lambda: ["main1", "main2"])
    stops_their_turn: list[str] = Field(default_factory=list)
    # Stop on public conditions too (cards in hand and untapped mana), so stopping doesn't tell the
    # table that you really have a response.
    bluff_stops: bool = False
    payment: Payment = "auto"
    mana_sources: dict[str, SourceProtection] = Field(default_factory=dict)  # card id -> PREFER / SAVE
    auto_resolve_own_triggers: TriggerAutoResolve = "safe"
    auto_order_identical_triggers: bool = True
    # -- temporary overrides --
    hold_priority: bool = False  # keep priority after casting / activating
    full_control: bool = False  # no smart passing at all: every priority is a stop
    force_stop: bool = False  # the next priority is a stop, whatever else is set (consumed)
    pass_until: PassUntil | None = None
    pass_mark: str = Field(default="", max_length=400)  # the situation when pass_until was set
    stop_after: str | None = None  # object id: stop once it has left the stack ("hold after this resolves")
    yields: list[Yield] = Field(default_factory=list, max_length=50)

    def stops(self, mine: bool) -> list[str]:
        return self.stops_my_turn if mine else self.stops_their_turn


# -- game objects, last known information, events -------------------------------------------
class ObjectSnapshot(BaseModel):
    """An object as it last existed in a public zone (Last Known Information, rule 608.2h).
    Recorded *before* it left, never reconstructed from where it went."""

    object_id: str
    card: str  # the physical card instance (may be gone: tokens cease to exist)
    printing: str | None = None
    name: str = ""
    owner: str
    controller: str
    zone: str
    turn: int = 0
    tapped: bool = False
    face_down: bool = False
    face: int = 0
    is_token: bool = False
    token_power: str | None = None
    token_toughness: str | None = None
    commander_key: str | None = None
    counters: dict[str, int] = Field(default_factory=dict)
    damage: int = 0
    effects: list[str] = Field(default_factory=list)  # "+3/+3", "Flying" … (manual effect markers)
    attacking: bool = False
    blocking: bool = False
    attached_to: str | None = None
    text: str = ""  # a custom token's rules text (it has no printing to look up)


EventKind = Literal[
    "zone_change",  # an object moved between zones (or ceased to exist: to_zone None)
    "damage",  # damage dealt (to a creature, planeswalker or player): not the same as life loss
    "life_loss",
    "life_gain",
    "counters",  # counters put on / removed from an object (amount signed)
    "player_counters",  # poison, energy, experience, rad, tickets … (amount signed)
    "tapped",
    "untapped",
    "spell_cast",  # a player cast a spell (the object is the spell on the stack)
    "cycled",  # a player cycled a card (702.29: "when you cycle …")
    "crewed",
    "turned_face_up",  # 702.37e (morph)  # a Vehicle became crewed (702.122)
]


class Event(BaseModel):
    """Something that happened. Events of one table step share a ``batch``: they happened
    simultaneously (destroy all creatures is one batch of zone changes, not N)."""

    batch: int
    kind: EventKind
    turn: int = 0
    object_id: str | None = None  # the object as it was (for zone changes: the old object, see ``lki``)
    new_object_id: str | None = None  # zone changes: the object it became
    card: str | None = None
    player: str | None = None  # the player affected (life, player counters, damage to a player)
    source: str | None = None  # the source object's id, when known
    from_zone: str | None = None
    to_zone: str | None = None
    amount: int = 0
    counter: str | None = None
    combat: bool = False
    manual: bool = False  # caused by a sandbox action, not by the rules engine


MAX_EVENTS = 500  # unconsumed events kept (a trigger collector consumes them; M16)
LKI_TURNS = 2  # how long last known information is kept


class ContinuousEffect(BaseModel):
    """A continuous effect from a resolved spell or ability (CR 611.2c): the objects it affects are
    fixed when it begins. See ``app.rules.layers``."""

    id: str
    affected: list[str] = Field(default_factory=list)  # rules object ids
    layer: Literal["1", "2", "3", "4", "5", "6", "7a", "7b", "7c", "7d"]
    source: str | None = None  # source object id
    controller: str
    power: int | None = None
    toughness: int | None = None
    add_keywords: list[str] = Field(default_factory=list)
    remove_keywords: list[str] = Field(default_factory=list)
    add_types: list[str] = Field(default_factory=list)  # layer 4: "becomes an artifact creature"
    duration: Literal["end_of_turn", "permanent"] = "end_of_turn"
    timestamp: int = 0
    label: str = ""


class TargetRef(BaseModel):
    """A chosen target: a player, or a rules object (card id + the object it was when chosen)."""

    id: str
    object_id: str | None = None


class PendingTrigger(BaseModel):
    """A triggered ability that has triggered but isn't on the stack yet (603.3)."""

    id: str
    controller: str
    source_card: str  # physical card (may be gone: a token that died)
    source_object: str
    name: str = ""
    ability: dict[str, Any]  # the ability's definition (data, see app.rules.scripts)
    key: str = ""  # identical triggers share a key (AUTO ORDER IDENTICAL TRIGGERS)
    ordered: bool = False  # its controller already chose the order


class StackEntry(BaseModel):
    """Rules metadata for an object on the stack: what it does and what it targets."""

    kind: Literal["spell", "trigger", "activated"]
    controller: str
    source_card: str | None = None
    source_object: str | None = None
    name: str = ""
    effects: list[dict[str, Any]] = Field(default_factory=list)
    targets: list[TargetRef] = Field(default_factory=list)
    target_spec: dict[str, Any] | None = None
    optional: bool = False  # "you may …": asked on resolution (603.5)
    x: int | None = None


class ReconcileItem(BaseModel):
    """Something the engine can't work out from the table after manual play (see reconcile)."""

    id: str = Field(max_length=64)
    card: str | None = None
    player: str | None = None
    question: str = Field(max_length=300)


class RulesState(BaseModel):
    paused: bool = False  # the host paused automation: intents are refused, the sandbox works
    step: str = ""  # "<turn>:<phase>" the engine last acted in; a mismatch means a manual step change
    priority: str | None = None  # player who may act
    passed: list[str] = Field(default_factory=list)  # players who passed in succession
    decision: Decision | None = None
    prefs: dict[str, PlayerPrefs] = Field(default_factory=dict)  # per-player automation preferences
    # Per-card automation override (right-click → Automation): "manual" cards are never automated;
    # the engine asks their controller to resolve them by hand and doesn't enforce their timing.
    card_modes: dict[str, Literal["manual", "assisted"]] = Field(default_factory=dict)
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
    regen_shields: dict[str, int] = Field(default_factory=dict)  # object id -> regeneration shields this turn
    echo_done: list[str] = Field(default_factory=list)  # "<object>:<controller>" whose echo upkeep came
    flashback: list[str] = Field(default_factory=list)  # stack objects cast with flashback (exiled as they leave)
    # Combat bookkeeping; the attack/block markers on the table are the visible truth.
    blocked: list[str] = Field(default_factory=list)  # attackers that became blocked (stay blocked)
    no_attackers: bool = False  # nobody attacked: skip blockers and damage (rule 508.8)
    blockers_pending: list[str] = Field(default_factory=list)  # defending players still to declare
    combat_round: Literal["", "first", "done"] = ""
    # Commanders offered the move to the command zone, and from which zone (asked once per arrival).
    commander_offered: dict[str, str] = Field(default_factory=dict)
    overrides: int = 0  # manual (sandbox) actions taken while automation was on
    sba_declined: str = ""  # ASSISTED: the state-based actions the table chose to leave for now
    # Manual table changes made while automation wasn't running (off or paused): the rules
    # bookkeeping may no longer describe the table; RESUME reconciles (app/rules/reconcile.py).
    unsynced: bool = False
    reconcile: list[ReconcileItem] = Field(default_factory=list)
    # Game-object identity (rule 400.7): a card that changes zones becomes a new object. The
    # physical card keeps its id; its rules object is "<card id>.<n>".
    objects: dict[str, int] = Field(default_factory=dict)
    next_object: int = 0
    lki: dict[str, ObjectSnapshot] = Field(default_factory=dict)  # object id -> last known information
    batch: int = 0  # last event batch number
    events: list[Event] = Field(default_factory=list)  # events since the engine last acted (this intent's, or manual ones)
    events_dropped: bool = False  # manual play produced more events than are kept
    actions: int = 0  # player actions (not passes) taken, for "pass until next action"
    last_actor: str | None = None
    engine_version: int = 0  # RULES_ENGINE_VERSION that last acted on this table
    effects: list[ContinuousEffect] = Field(default_factory=list)
    timestamp: int = 0  # last timestamp handed out (613.7)
    pending_triggers: list[PendingTrigger] = Field(default_factory=list)
    trigger_batch: int = 0  # last event batch the trigger collector looked at
    stack: dict[str, StackEntry] = Field(default_factory=dict)  # stack card id -> what it does
    # Each player's intents this turn, for REPEAT LAST VALIDATED SEQUENCE (payloads, newest last).
    recent: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    recent_turn: int = 0

    def lands_this_turn(self, player: str, turn: int) -> int:
        entry = self.lands_played.get(player)
        return entry.count if entry and entry.turn == turn else 0

    def spells_this_turn(self, player: str, turn: int) -> int:
        entry = self.spells_cast.get(player)
        return entry.count if entry and entry.turn == turn else 0

    def prefs_for(self, player: str) -> PlayerPrefs:
        return self.prefs.get(player) or PlayerPrefs()

    def object_id(self, card_id: str) -> str:
        return f"{card_id}.{self.objects.get(card_id, 0)}"

    def card_mode(self, card_id: str) -> str:
        return self.card_modes.get(card_id, "auto")


def start_rules(state: GameState) -> RulesState:
    """Turn automation on for a table that had none: the active player gets priority in the
    current step. What the table can't tell (did that creature arrive this turn? was a land
    played?) is not invented: ``app.rules.reconcile`` asks, or the card stays manual."""
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


# -- bookkeeping after every applied step ---------------------------------------------------------
TRACKED_ZONES = ("battlefield", "stack")  # zones whose objects get last known information


def _zone_name(key: str) -> str:
    return key.rsplit(":", 1)[-1]


def snapshot(state: GameState, card_id: str) -> ObjectSnapshot:
    c = state.cards[card_id]
    rules = state.rules
    token = c.token
    return ObjectSnapshot(
        object_id=rules.object_id(card_id) if rules else card_id, card=card_id, printing=c.card_id, name=c.name,
        owner=c.owner, controller=c.controller, zone=c.zone, turn=state.turn.number, tapped=c.tapped,
        face_down=c.face_down, face=c.face, is_token=c.is_token,
        token_power=token.power if token else None, token_toughness=token.toughness if token else None,
        commander_key=c.commander_key, counters=dict(c.counters), damage=c.damage,
        effects=[e.value or e.name for e in c.effects], attacking=c.attacking is not None,
        blocking=c.blocking is not None, attached_to=c.attached_to, text=token.text if token else "",
    )


class Capture:
    """The table just before one step is applied (in memory only, never saved): what ``track``
    compares against to find zone changes, counters and taps, and the objects' last known
    information for anything that leaves the battlefield or the stack."""

    __slots__ = ("zones", "snaps", "resources")

    def __init__(self, state: GameState) -> None:
        self.zones = {cid: c.zone for cid, c in state.cards.items()}
        self.snaps = {
            cid: snapshot(state, cid) for cid, c in state.cards.items() if _zone_name(c.zone) in TRACKED_ZONES
        }
        self.resources = {pid: dict(p.resources) for pid, p in state.players.items()}


def capture(state: GameState) -> Capture | None:
    return Capture(state) if state.rules is not None else None


def emit(state: GameState, kind: EventKind, **fields: Any) -> None:
    """Record an event of the step being applied (handlers call this for what a table diff can't
    show: damage as opposed to life loss, life gained and lost in the same step)."""
    rules = state.rules
    if rules is None:
        return
    rules.events.append(Event(batch=rules.batch + 1, kind=kind, turn=state.turn.number, **fields))


def track(state: GameState, before: Capture | None = None, *, manual: bool = False) -> None:
    """Deterministic bookkeeping after every applied step (sandbox or rules): whose turn started
    when, when each permanent came under its controller's control, which physical card is which
    rules object, last known information, and the step's events as one simultaneous batch.
    Pure: it reads only the table (and the step's ``emit``s), so replay reproduces it exactly."""
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
    if before is not None:
        _diff(state, rules, before, manual)
    pending = [e for e in rules.events if e.batch > rules.batch]
    if pending:
        rules.batch += 1
        for e in pending:
            e.batch = rules.batch
            e.manual = e.manual or manual
    if len(rules.events) > MAX_EVENTS:
        del rules.events[: len(rules.events) - MAX_EVENTS]
        rules.events_dropped = True  # reconciliation can't rely on the event history any more
    oldest = state.turn.number - LKI_TURNS
    for oid in [o for o, snap in rules.lki.items() if snap.turn < oldest]:
        del rules.lki[oid]


def _diff(state: GameState, rules: RulesState, before: Capture, manual: bool) -> None:
    departures = state.departures()
    for card_id, old_zone in before.zones.items():
        card = state.cards.get(card_id)
        new_zone = card.zone if card is not None else departures.get(card_id)
        if card is not None and new_zone == old_zone:
            continue
        old_name = _zone_name(old_zone)
        new_name = _zone_name(new_zone) if new_zone else None
        if card is not None and old_name == new_name and old_name != "battlefield":
            continue  # e.g. a hand passed between players' libraries is still a library card
        if old_name == new_name == "battlefield":
            continue  # a control change is not a zone change: same object (rule 400.7 doesn't apply)
        old_oid = rules.object_id(card_id)
        snap = before.snaps.get(card_id)
        if snap is not None:
            rules.lki[old_oid] = snap.model_copy(update={"turn": state.turn.number})
        new_oid = None
        if card is not None:
            rules.next_object += 1
            rules.objects[card_id] = rules.next_object
            new_oid = rules.object_id(card_id)
        else:
            rules.objects.pop(card_id, None)
        if old_name in ("library", "hand") and new_name in ("library", "hand", None) and snap is None:
            continue  # private shuffling around: new objects, but nothing public happened
        emit(state, "zone_change", object_id=old_oid, new_object_id=new_oid, card=card_id,
             player=(card.controller if card is not None else snap.controller if snap else None),
             from_zone=old_zone, to_zone=new_zone)
    for card_id, card in state.cards.items():
        if card_id not in before.zones and _zone_name(card.zone) in TRACKED_ZONES:
            emit(state, "zone_change", new_object_id=rules.object_id(card_id), card=card_id, player=card.controller,
                 to_zone=card.zone)  # created: a token, a copy, an ability on the stack
    for card_id, snap in before.snaps.items():
        card = state.cards.get(card_id)
        if card is None or card.zone != snap.zone:
            continue
        oid = rules.object_id(card_id)
        for kind in set(snap.counters) | set(card.counters):
            delta = card.counters.get(kind, 0) - snap.counters.get(kind, 0)
            if delta:
                emit(state, "counters", object_id=oid, card=card_id, counter=kind, amount=delta)
        if card.tapped != snap.tapped:
            emit(state, "tapped" if card.tapped else "untapped", object_id=oid, card=card_id)
    for pid, old in before.resources.items():
        p = state.players.get(pid)
        if p is None:
            continue
        for kind in set(old) | set(p.resources):
            delta = p.resources.get(kind, 0) - old.get(kind, 0)
            if delta:
                emit(state, "player_counters", player=pid, counter=kind, amount=delta)
    departures.clear()
