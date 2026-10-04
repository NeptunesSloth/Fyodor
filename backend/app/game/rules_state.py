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

from pydantic import BaseModel, Field, model_validator

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
    "divide",  # 601.2d: an amount (at least 1) per option, adding up to the total (answered with amounts)
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
    # 800.4a: True when it came under this controller's control while on the battlefield (a
    # control-changing effect, done by hand: ``set_controller``), False when it entered the
    # battlefield under this control (reanimated "under your control"), None when unknown (an
    # older save, or automation turned on mid-game).
    changed: bool | None = None


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
# "self": the player taps their own mana and costs are paid from the mana pool only (the table's
# rule: the engine never taps anyone's lands). "auto"/"ask"/"manual" remain for engine tests only.
Payment = Literal["self", "auto", "ask", "manual"]
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
    payment: Payment = "self"
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


# -- copy system (wave 2F): copy recipes (CR 707, 613.2) ----------------------------------------
class CopyExcept(BaseModel):
    """The exceptions of one copy effect (707.9): values it sets or adds as part of the copying
    process, which then belong to the copy's copiable values (707.9a-b). Applied in this order:
    name, power/toughness (707.9d: a characteristic-defining ability for P/T isn't copied), types
    added or supertypes removed ("it isn't legendary"), colors set (707.9d), abilities gained
    (707.9a: keyword lines like "Haste", or a quoted ability's text)."""

    name: str | None = Field(default=None, max_length=200)
    power: str | None = Field(default=None, max_length=8)
    toughness: str | None = Field(default=None, max_length=8)
    add_types: list[str] = Field(default_factory=list)
    add_subtypes: list[str] = Field(default_factory=list)
    add_supertypes: list[str] = Field(default_factory=list)
    remove_supertypes: list[str] = Field(default_factory=list)
    set_colors: list[str] | None = None
    add_text: list[str] = Field(default_factory=list)
    add_colors: list[str] = Field(default_factory=list)  # "in addition to its other colors"
    # -- token copies & attach on entry (wave 5J) -- "except it's a 4/4 black Zombie": its creature types are these
    # (205.1a: they replace the copied ones; other subtypes stay), changeling isn't copied (707.9d)
    set_creature_types: list[str] | None = None


class CopyRecipe(BaseModel):
    """What a copy's copiable values are built from (707.2, 707.3): the printed values of a card
    (``printing`` and the ``face`` that was up, 707.8) or the values a token's creating effect
    defined (``token``: the TokenDef fields, 111.3), then every copy effect's exceptions in order
    (``excepts``, 707.9). A recipe, not a snapshot of a live object: counters, status and
    non-copy effects are never in it (707.2), and a copy of a copy starts from the first copy's
    recipe and adds its own exceptions (707.3). Built by app/rules/copying.py."""

    printing: str | None = Field(default=None, max_length=64)
    face: int = 0
    token: dict[str, Any] | None = None  # {"name", "power", "toughness", "colors", "type_line", "text"}
    excepts: list[CopyExcept] = Field(default_factory=list)
    source: str = Field(default="", max_length=200)  # the name of what was copied (for labels)


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
    token_type_line: str | None = None  # (a token's types and colors, for what it was: 608.2h)
    # Its power and toughness as it last existed (layers applied, counters included): recorded by
    # the rules engine as it moves the object (608.2h), None for moves made by hand
    power: int | None = None
    toughness: int | None = None
    token_colors: list[str] = Field(default_factory=list)
    commander_key: str | None = None
    counters: dict[str, int] = Field(default_factory=dict)
    damage: int = 0
    effects: list[str] = Field(default_factory=list)  # "+3/+3", "Flying" … (manual effect markers)
    attacking: bool = False
    blocking: bool = False
    attached_to: str | None = None
    attached_player: str | None = None  # -- attached events (wave 4L) -- the player an Aura enchanted (a Curse)
    # -- sagas & attached-object triggers (wave 3S) -- the permanents (card ids) attached to it as it
    # last existed: "When enchanted creature dies" looks back in time (603.10a)
    attached: list[str] = Field(default_factory=list)
    text: str = ""  # a custom token's rules text (it has no printing to look up)
    # -- quoted grants (wave 2D) --
    # Its abilities and keywords as they last existed (603.10a: leaves-the-battlefield abilities look
    # back in time; 608.2h), recorded by the rules engine as it moves the object — only when they
    # differ from the printed ones (granted by a resolved effect or a static ability, or lost): each
    # ability line as {index, text, kind, keywords, cost, intrinsic}. None: the printed ones.
    abilities: list[dict[str, Any]] | None = None
    keywords: list[str] | None = None
    # Its types, subtypes, supertypes and colors as they last existed, when layer 4 / 5 had changed them
    # (an animated land or a crewed Vehicle died as a creature, 700.4): {"types": […], "subtypes": […],
    # "supertypes": […], "colors": […]}. None: the printed ones.
    traits: dict[str, list[str]] | None = None
    # -- copy system (wave 2F): its copiable values if a copy effect applied to it (613.2), so its
    # last known information has the copied abilities (a dying Clone's "dies" trigger, 603.10a)
    copy_recipe: CopyRecipe | None = None
    # -- stack interaction (wave 5B) -- the X a spell on the stack had (202.3e: its mana value counts it),
    # so "that spell's mana value" after it was countered reads it as it last existed (608.2h)
    x: int | None = None


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
    "land_played",  # -- entry forms (wave 5F) -- a player played a land (305.1: "when you play another land")
    "mana_added",  # a mana ability produced mana (106.3, 106.12a); convoke/improvise/delve never do
    "drew",  # a player drew a card (121.2: one event per card)
    "crewed",
    "turned_face_up",  # 702.37e (morph)  # a Vehicle became crewed (702.122)
    # 701.21a: a permanent was sacrificed (emitted just before it moves, in the same batch; the
    # object is the permanent as it was — "whenever you sacrifice …" looks back in time, 603.10a)
    "sacrificed",
    # -- copy system (wave 2F): a copy of a spell was put onto the stack (707.10: not cast); the
    # object is the copy, ``source`` the spell it copies, ``player`` its controller
    "spell_copied",
    # -- counters & designations (wave 3E): ``counter`` = "monarch" | "initiative" | "day" | "night" |
    # "ring" (701.54d: the Ring tempted ``player``) | "dungeon" (309.7: ``player`` completed a dungeon)
    "designation",
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
    # -- counters (wave 5H) -- counters put on an object: the player who put them (the step's actor: 122.6, 122.6a)
    actor: str | None = None
    group: int = 0  # -- counters (wave 7C) -- counters one instruction put in several steps share it (122.6); 0: alone


MAX_EVENTS = 500  # unconsumed events kept (a trigger collector consumes them; M16)
LKI_TURNS = 2  # how long last known information is kept


# -- this turn's history (conditional / instead clauses, wave 1B) --------------------------------------
class Departure(BaseModel):
    """A permanent that left the battlefield this turn, for "if a creature died this turn" / "if a
    permanent left the battlefield under your control this turn" (CR 700.4: dies = put into a
    graveyard from the battlefield). What it was is read from its last known information
    (608.2i: such an effect looks back in time at the object as it last existed there)."""

    card: str = Field(max_length=64)
    object_id: str = Field(max_length=80)  # the object as it last existed on the battlefield (its ``lki`` key)
    controller: str = Field(max_length=64)  # who controlled it as it left
    to: str = Field(default="", max_length=20)  # the zone it went to: "graveyard", "exile", "hand", "library" …
    # its card types as it last existed (layers applied: an animated land, a crewed Vehicle), when
    # the rules engine moved it; None (moved by hand): its printed types from the last known information
    types: list[str] | None = None


class Arrival(BaseModel):
    """A card (never a token: 111.1) put into a graveyard this turn from anywhere, for "if you descended this
    turn" (700.11: a permanent card put into your graveyard — it needn't still be there). Whether it is a
    permanent card is read from the card when the condition is asked."""

    card: str = Field(max_length=64)
    owner: str = Field(max_length=64)  # whose graveyard it went to


# -- refused modal/conditional (wave 3R1) --
class Entry(BaseModel):
    """A permanent that entered the battlefield this turn (a token created there included, 111.1), for "if two or
    more nonland permanents entered the battlefield under your control this turn" (celebration), "if another
    creature entered …", "as long as ~ entered this turn". 608.2i: what it was is what it was as it entered — its
    card types and subtypes then (layers applied), when the rules engine put it there (``types`` None: put there
    by hand, read from the object as it is or last existed)."""

    card: str = Field(max_length=64)
    object_id: str = Field(max_length=80)  # the object it became on the battlefield
    controller: str = Field(max_length=64)  # who controlled it as it entered
    types: list[str] | None = None
    subtypes: list[str] | None = None
    # -- entry forms (wave 5F) -- whether it entered tapped ("When this land enters untapped", "Whenever a permanent
    # you control enters tapped": part of the event, 603.2); None: not known (an older save)
    tapped: bool | None = None
# -- end refused modal/conditional (wave 3R1) --


# -- this-turn history (wave 4D) --
class CastNote(BaseModel):
    """A spell cast this turn, as it became cast (601.2i; 608.2i: "if you've cast a noncreature spell this turn"
    reads the spell as it was then — whether it resolved, was countered or is still on the stack doesn't matter).
    Spells on the stack are public: a face-down spell is recorded with its face-down characteristics (708.2)."""

    player: str = Field(max_length=64)
    object_id: str = Field(max_length=80)
    types: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)
    supertypes: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    mv: float = 0
    cast_from: str | None = Field(default=None, max_length=20)  # "hand", "graveyard", "exile", "command" …
    became: str | None = Field(default=None, max_length=80)  # the permanent a permanent spell became (608.3)


class TurnFact(BaseModel):
    """Something a player did, or that happened to a player, this turn (608.2i): ``kind`` "token" (111.2: ``player``
    created a token — its owner), "discard" (701.9a), "sacrifice" (701.21a), "damage" (``player`` was dealt
    ``amount`` damage, ``combat``; ``source_types`` / ``source_supertypes`` the source as it was then), "scry" /
    "surveil" (701.22, 701.25; nothing about the cards), "counters" (``amount`` ``counter`` counters were put on a
    permanent ``player`` controlled). ``types`` …: the object concerned, as it was then."""

    kind: str = Field(max_length=20)
    player: str = Field(max_length=64)
    object_id: str | None = Field(default=None, max_length=80)
    types: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)
    supertypes: list[str] = Field(default_factory=list)
    token: bool = False
    amount: int = 1
    combat: bool = False
    counter: str | None = Field(default=None, max_length=40)
    source_types: list[str] = Field(default_factory=list)
    source_supertypes: list[str] = Field(default_factory=list)
    # -- damage history (wave 6B) -- "damaged" facts (a permanent was dealt ``amount`` damage; ``object_id`` the
    # permanent): the object that dealt it
    source: str | None = Field(default=None, max_length=80)
    actor: str | None = Field(default=None, max_length=64)  # -- long tail (wave 16D) -- "counters" facts: the player who put them (122.6)
# -- end this-turn history (wave 4D) --


class TurnLog(BaseModel):
    """What happened during one turn that later text can ask about (608.2i): who attacked (508.1),
    life gained and lost (damage included, 120.3a), cards drawn, permanents that left the
    battlefield, cards that left a graveyard or went into one. Recorded deterministically from the
    steps applied to the table (``track`` / ``emit``) and the declaration of attackers, so replays,
    saves and undo reproduce it exactly. Only this turn's and the previous turn's logs are kept."""

    turn: int = 0
    attacked: list[str] = Field(default_factory=list)  # players who declared one or more attackers
    gained: dict[str, int] = Field(default_factory=dict)  # player -> life gained
    lost: dict[str, int] = Field(default_factory=dict)  # player -> life lost
    drew: dict[str, int] = Field(default_factory=dict)  # player -> cards drawn
    left: list[Departure] = Field(default_factory=list)
    left_graveyard: list[str] = Field(default_factory=list)  # the owner of each card that left a graveyard
    entered_graveyard: list[Arrival] = Field(default_factory=list)
    entered: list[Entry] = Field(default_factory=list)  # -- refused modal/conditional (wave 3R1) -- onto the battlefield
    # -- this-turn history (wave 4D; app/rules/history.py) --
    casts: list[CastNote] = Field(default_factory=list)  # spells cast, as they became cast (601.2i)
    facts: list[TurnFact] = Field(default_factory=list)  # tokens created, discards, sacrifices, damage to players …
    attackers: dict[str, list[str]] = Field(default_factory=dict)  # player -> creatures (objects) declared as attackers
    # "<source object>:<ability index>" -> how many times that ability resolved this turn (copies included)
    resolved: dict[str, int] = Field(default_factory=dict)
    # -- end this-turn history (wave 4D) --


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
    add_subtypes: list[str] = Field(default_factory=list)  # layer 4: "becomes a Goblin in addition to its other types" (701.47a)
    # Rule-modifying effects on the objects (not a layer; 611.2c duration): "can't block this turn"
    # — the names scripts.statics uses (cant_block, cant_be_blocked, …).
    imposes: list[str] = Field(default_factory=list)
    # A group the effect applies to whenever it's evaluated ("Creatures can't block this turn":
    # a rule-modifying effect isn't locked to the objects there when it began, 611.2c): a
    # selector key, read for ``controller`` ("you"), ``source_card`` for "other".
    who: str | None = Field(default=None, max_length=2000)
    source_card: str | None = None
    # 611.2a: how long it lasts — "until end of turn" (ends at cleanup, 514.2), "permanent" (the
    # game), "next_turn" ("until your next turn": ends as ``until_player``'s next turn begins,
    # 500.4), "source_on_battlefield" / "source_controlled" / "source_tapped" ("for as long as ~
    # remains on the battlefield / you control ~ / ~ remains tapped", 611.2b: ends as soon as
    # that stops being true; app/rules/delayed.py expires them).
    # -- quoted grants (wave 2D) -- "while_counter": "for as long as that creature has a bounty counter on
    # it" (``counter`` names the kind; an affected object that has none left drops out, and the effect
    # ends with the last one: 611.2b, app/rules/delayed.expire).
    duration: Literal["end_of_turn", "permanent", "next_turn", "source_on_battlefield", "source_controlled",
                      "source_tapped", "source_controlled_tapped", "while_counter"] = "end_of_turn"
    counter: str | None = None  # while_counter: the kind of counter
    until_player: str | None = None  # next_turn: whose next turn; source_controlled: who must control the source
    turn: int = 0  # the turn the effect began (next_turn: it ends on a later turn of until_player)
    timestamp: int = 0
    # ``RulesState.next_object`` when the effect began: the last object to enter a zone before it, so
    # the effect can be ordered against static abilities (their timestamp is their source's, 613.7a/d).
    object_seq: int = 0
    label: str = ""
    # The table markers ("until your next turn", …) this effect wrote: removed when it ends, and
    # only those (another effect's marker with the same wording stays). None: an effect from a
    # game saved before effects remembered their markers (app/rules/delayed._end).
    markers: list[str] | None = None
    # -- animation (agent A2): the type-, color- and ability-changing parts of "becomes a …" -------
    # Layer 4 (613.1d). ``set_types``: the card types replace the object's (205.1a; the subtypes
    # of a card type it no longer has drop with it) — None when the effect only adds types
    # ("in addition to its other types", "it's still a land", "becomes an artifact creature":
    # 205.1b, ``add_types``). ``add_supertypes``: "becomes a legendary …" (205.4b: the others
    # stay). ``set_creature_types``: replaces its creature types, other subtypes stay (205.1a /
    # 205.1b "[creature type] creature") — None: unchanged; ``all_creature_types``: "with all
    # creature types" (every creature type, as changeling has, 702.73a).
    set_types: list[str] | None = None
    add_supertypes: list[str] = Field(default_factory=list)
    set_creature_types: list[str] | None = None
    all_creature_types: bool = False
    # -- land types set (wave 12D) -- 305.7: "target land becomes an Island": its land types are replaced by these basic
    # land types, it loses the abilities of its rules text (and any copiable effects) and gains the types' mana abilities.
    set_land_types: list[str] | None = None
    # Layer 5 (613.1e, 105.3): ``set_colors`` replaces its colors ([]: colorless) — None: unchanged;
    # ``add_colors``: "in addition to its other colors".
    set_colors: list[str] | None = None
    add_colors: list[str] = Field(default_factory=list)
    # Layer 6 (613.1f): "loses all abilities" (its printed abilities and everything granted before
    # this effect's timestamp; later grants apply again) and quoted abilities it gains (their text).
    remove_abilities: bool = False
    add_abilities: list[str] = Field(default_factory=list)
    # -- copy system (wave 2F): layer 1a (613.2a) — a copy effect: the affected objects' copiable
    # values become this recipe's (707.2-707.5); the latest (by timestamp) applies (613.7)
    copy_recipe: CopyRecipe | None = None
    # -- control (wave 3K) -- layer 2 (613.1b): the player who controls the affected objects while this
    # effect applies ("gain control of target creature until end of turn", "exchange control of …");
    # the latest by timestamp wins (613.7); app/rules/layers.control_sync applies it to the table.
    new_controller: str | None = None


class TargetRef(BaseModel):
    """A chosen target: a player, or a rules object (card id + the object it was when chosen)."""

    id: str
    object_id: str | None = None


class ObjectRef(BaseModel):
    """A stable reference to one rules object (400.7): the physical card, which object it was, and
    where it was then. A later reference finds it only while the card is still that object in that
    zone; otherwise only its last known information remains (``snapshot``, or ``RulesState.lki``;
    608.2h)."""

    card: str = Field(max_length=64)
    object_id: str = Field(max_length=80)
    zone: str | None = Field(default=None, max_length=80)
    snapshot: ObjectSnapshot | None = None  # as it last existed, when it had already left (603.10a)


class TriggerEvent(BaseModel):
    """What a triggered ability triggered on (603.2), captured as it triggered and carried with it
    to the stack and through resolution (603.3, 608.2k): the resolving ability reads this, never the
    board as it is later. One event for a "one or more" trigger holds every object of the batch
    (603.2c)."""

    kind: str = Field(max_length=40)  # the condition's event: "die", "draw", "gain_life", …
    batch: int = 0
    objects: list[ObjectRef] = Field(default_factory=list)  # the object(s) the event happened to
    # For a zone change: the object each became where it went (400.7e: a "dies" ability can find
    # it in the graveyard, and only there)
    new_objects: list[ObjectRef] = Field(default_factory=list)
    players: list[str] = Field(default_factory=list)  # the player it was about (who drew / gained / was dealt damage)
    source: ObjectRef | None = None  # the source of damage dealt
    amount: int = 0  # life gained or lost, damage dealt (summed over a "one or more" batch)
    count: int = 0  # how many objects / events the batch had
    defended: str | None = None  # -- combat (wave 5C) -- "Whenever you attack a player": the player attacked (508.3e)
    # -- damage wordings (wave 6B) -- "Whenever ~ blocks or becomes blocked by a creature, …": that creature (509.3c-d)
    other: ObjectRef | None = None


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
    event: TriggerEvent | None = None  # what it triggered on


class DelayedTrigger(BaseModel):
    """A delayed triggered ability (CR 603.7), created as a spell or ability resolved (603.7a) and
    waiting for its trigger event. Everything it will need is captured now: the objects it refers
    to as ObjectRefs (603.7c: still affected whatever their characteristics become, but not once
    they have left the zone they are expected in — a new object isn't them, 400.7), its source
    and controller as they were (603.7d-e), and the effects to carry out. When its event happens
    it triggers like any other triggered ability (a PendingTrigger, put on the stack in APNAP
    order, 603.3b) and resolves with these refs as its own resolution context
    (app/rules/context.py); it never rescans the table for "it". See app/rules/delayed.py."""

    id: str
    controller: str  # 603.7d-e: whoever controlled the creating spell or ability as it resolved
    source_card: str | None = None  # 603.7d-e: the spell, or the ability's source
    source_object: str | None = None
    name: str = ""
    # When it triggers: {"kind": "step", "step": "end" | "upkeep", "whose": "next" | "you" | "next_turn"}
    # ("at the beginning of the next end step / your next end step / the next turn's upkeep /
    # your next upkeep"), or {"kind": "event", "event": "die" | "leave"} about the object(s) bound
    # as ``refs["watch"]`` ("when that creature dies this turn")
    when: dict[str, Any]
    effects: list[dict[str, Any]] = Field(default_factory=list)
    refs: dict[str, Any] = Field(default_factory=dict)  # its resolution bindings (app/rules/context.py)
    event: dict[str, Any] | None = None  # the creating trigger's TriggerEvent, for "it" of a "When ~ dies, … at the beginning of …"
    turn: int = 0  # the turn and step it was created in ("the next end step" is after this one)
    step: str = ""
    once: bool = True  # 603.7b: it triggers only once (an "each" duration would say otherwise)
    until_turn: int | None = None  # "this turn": it stops watching at that turn's cleanup (514.2)

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, data: Any) -> Any:
        """Older saves kept "at the beginning of the next end step, move it" as a plain dict
        ({"card", "object", "to", "name"}: unearth, dash)."""
        if isinstance(data, dict) and "when" not in data and "card" in data and "to" in data:
            return {"id": f"legacy:{data['object']}", "controller": "", "source_card": data["card"],
                    "source_object": data["object"], "name": data.get("name", ""),
                    "when": {"kind": "step", "step": "end", "whose": "next"},
                    "effects": [{"do": "delayed_move", "card": data["card"], "object": data["object"], "to": data["to"]}]}
        return data


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
    # A modal spell (700.2): the chosen modes, and one target slot per chosen mode (700.2c, 700.2f);
    # "use_targets" effects switch to a slot. Empty for a spell with one target list.
    modes: list[int] = Field(default_factory=list)
    slots: list[list[TargetRef]] = Field(default_factory=list)
    slot_specs: list[dict[str, Any] | None] = Field(default_factory=list)
    # Target groups (115.1, 601.2c): one per word "target", in printed order — "up to two target
    # creatures", "target creature and another target creature". ``group_specs`` are the
    # definition's groups ({"what", "min", "max", "distinct_from"?, "divide"?}), ``groups`` the
    # chosen targets of each, ``division`` the amount per target of each divided group (601.2d;
    # empty for the others). ``targets`` stays the flat list of all of them. Empty for a spell or
    # ability with one plain "target" (target_spec) or modes (slots).
    groups: list[list[TargetRef]] = Field(default_factory=list)
    group_specs: list[dict[str, Any]] = Field(default_factory=list)
    division: list[list[int]] = Field(default_factory=list)
    # 702.33d: how many times the spell was kicked (a copy keeps it: 707.10)
    kicked: int = 0
    # A triggered ability: what it triggered on (603.2), for "it", "that player", "that much"
    event: TriggerEvent | None = None
    # -- copy system (wave 2F): a copy of a spell or ability (707.10): the object id of what it
    # copies. A copy isn't cast (or activated); its cost-paying objects are the original's.
    copy_of: str | None = None


class CostContribution(BaseModel):
    """One mana symbol of a spell's total cost paid by something that isn't mana (CR 702.51a
    convoke, 702.126a improvise, 702.66a delve): which object, and which symbol it paid."""

    kind: Literal["convoke", "improvise", "delve"]
    card: str = Field(max_length=64)
    object_id: str = Field(default="", max_length=80)  # the object as it was when used
    name: str = Field(default="", max_length=200)
    pays: str = Field(max_length=8)  # "1" (one generic), "G", "W/U", "2/G", "G/P"


class PaymentRecord(BaseModel):
    """How a spell's total cost was paid (601.2f-h), kept for "mana spent to cast it", "if its
    kicker/alternative cost was paid", "the creatures that convoked it" … Contributions are NOT
    mana spent (702.51a: "rather than pay that mana")."""

    card: str = Field(max_length=64)
    controller: str = Field(max_length=64)
    total_cost: str = Field(default="", max_length=200)  # the locked-in total cost, e.g. "{3}{G}{G}"
    mana_spent: dict[str, int] = Field(default_factory=dict)  # actual mana, by type (W U B R G C)
    contributions: list[CostContribution] = Field(default_factory=list)
    life: int = 0  # life paid (Phyrexian mana, …)
    tapped: list[str] = Field(default_factory=list)  # permanents tapped for mana while paying (engine-paid)
    sacrificed: list[str] = Field(default_factory=list)
    sacrificed_objects: list[str] = Field(default_factory=list)  # (wave 3D) the object ids they were: last known information
    discarded: list[str] = Field(default_factory=list)
    exiled: list[str] = Field(default_factory=list)  # cards exiled to pay (from a graveyard, or the source)
    returned: list[str] = Field(default_factory=list)  # permanents returned to hand to pay
    tapped_for_cost: list[str] = Field(default_factory=list)  # "Tap an untapped creature you control" (not for mana)
    kicked: int = 0  # 702.33d: times its kicker cost was paid
    alternative: str | None = None  # "evoke", "dash", "flashback", "madness", "face_down", "free", …
    additional: list[str] = Field(default_factory=list)  # "buyback", "kicker", …
    x: int | None = None
    # -- refused modal/conditional (wave 3R1) -- how the spell was cast, for "if you cast it [from your hand]",
    # "if this spell was cast from a graveyard" and addendum ("if you cast this spell during your main phase"):
    # the zone it was cast from (None: not cast — a copy, 707.10 — or an ability's record, or an older save);
    # whether it was cast during its caster's own main phase; ``mana_known`` False for a card moved onto the
    # stack by hand (cast by hand: what paid for it is unknown, so no "mana was spent" condition can hold)
    cast_from: str | None = Field(default=None, max_length=20)
    cast_main: bool = False
    mana_known: bool = True


class Permission(BaseModel):
    """An effect that lets a player cast a spell or play a land they otherwise couldn't (CR 601.3,
    305.1): from a zone other than their hand, as though it had flash, without paying its mana
    cost, or once during each of their turns. Granted by a resolved spell or ability
    (``app.rules.permissions``); static abilities of permanents are read from the table instead
    and never stored."""

    id: str
    player: str
    play: bool = False  # lands ("you may play …" covers both: 701.13 — "play" a land or cast a spell)
    cast: bool = False  # spells
    zone: Literal["hand", "graveyard", "exile", "library_top", "any"] = "any"  # where the card must be
    # A specific object ("you may play that card this turn"): the permission follows the object,
    # not the card (400.7h/i): once it changes zones it is a new object and the permission is spent
    object_id: str | None = None
    card: str | None = None
    filter: str | None = None  # a selector key the spell must match ("creature spells")
    free: bool = False  # "without paying its mana cost": an alternative cost of {0} (118.9)
    flash: bool = False  # "as though it had flash" (601.3b)
    once: bool = False  # "once during each of your turns"
    used_turn: int = 0  # (once) the turn it was used
    until: Literal["end_of_turn", "end_of_next_turn", "next_end_step", "permanent"] = "end_of_turn"
    turn: int = 0  # the turn it was granted (for end_of_next_turn)
    source: str | None = None  # the granting object
    label: str = Field(default="", max_length=120)
    # -- as long as (wave 9B) -- "mana of any type can be spent to cast that spell" ("type") / "you may spend mana as though it
    # were mana of any color to cast it" ("color"): applies only to mana spent casting with this permission (118.14, 609.4b)
    spend: Literal["", "type", "color"] = ""


class CostModifier(BaseModel):
    """A cost increase or reduction that applies to spells as their total cost is determined
    (601.2f): generic mana only (118.7a), never below {0}. Static ones ("Creature spells you cast
    cost {1} less to cast.") are read from the table; effects with a duration are stored here."""

    id: str
    controller: str  # whose "you" (the source's controller)
    delta: int  # +N: costs {N} more; −N: costs {N} less
    caster: Literal["you", "opponent", "any"] = "you"
    filter: str | None = None  # a selector key the spell must match, or None for every spell
    # "permanent" (a static, read from the table), "end_of_turn" ("… you cast this turn cost …": ends in
    # cleanup, 514.2) or "next_turn" ("Until your next turn, …": ends as its controller's next turn begins)
    until: Literal["end_of_turn", "permanent", "next_turn"] = "end_of_turn"
    turn: int = 0  # the turn it was created
    source: str | None = None
    label: str = Field(default="", max_length=120)
    mana: str = Field(default="", max_length=1)  # -- cost changers (wave 4I) -- a colored change ("{W} more"): its color


class TopReveal(BaseModel):
    """"Play with the top card of your library revealed." / "You may look at the top card of your
    library any time." — while ``source`` is on the battlefield under ``player``'s control, that
    player's top library card is visible to everyone or to its owner (401.5). Refreshed by the
    engine from the table; ``app.game.visibility`` checks the source is still there."""

    source: str  # the permanent's card id
    player: str
    to: Literal["all", "owner"]


class ReconcileItem(BaseModel):
    """Something the engine can't work out from the table after manual play (see reconcile)."""

    id: str = Field(max_length=64)
    card: str | None = None
    player: str | None = None
    question: str = Field(max_length=300)


class DungeonMark(BaseModel):
    """-- counters & designations (wave 3E) -- A dungeon card a player owns in the command zone
    (309.2b) and the room their venture marker is on (309.4)."""

    dungeon: str = Field(max_length=60)  # its name ("Lost Mine of Phandelver")
    room: str = Field(max_length=60)  # the room's name


class RulesState(BaseModel):
    paused: bool = False  # the host paused automation: intents are refused, the sandbox works
    step: str = ""  # "<turn>:<phase>" the engine last acted in; a mismatch means a manual step change
    priority: str | None = None  # player who may act
    passed: list[str] = Field(default_factory=list)  # players who passed in succession
    # -- core review -- the player the engine passes for once, Arena-style, right after they cast a spell or activated an
    # ability: consumed by engine.advance once the triggers that cast caused are on the stack (117.3c, 603.3)
    auto_pass: str | None = None
    decision: Decision | None = None
    prefs: dict[str, PlayerPrefs] = Field(default_factory=dict)  # per-player automation preferences
    # Per-card automation override (right-click → Automation): "manual" cards are never automated;
    # the engine asks their controller to resolve them by hand and doesn't enforce their timing.
    card_modes: dict[str, Literal["manual", "assisted"]] = Field(default_factory=dict)
    lands_played: dict[str, TurnCount] = Field(default_factory=dict)
    extra_land_plays: dict[str, TurnCount] = Field(default_factory=dict)  # -- wave 8A -- "You may play an additional land this turn."
    spells_cast: dict[str, TurnCount] = Field(default_factory=dict)
    mana_cast: dict[str, TurnCount] = Field(default_factory=dict)  # -- wave 15B -- mana spent to cast spells this turn (700.14 expend)
    loyalty_used: dict[str, int] = Field(default_factory=dict)  # planeswalker -> turn it last used a loyalty ability
    # -- activation costs (wave 4H) -- exerted permanents (701.43a): object id -> the player who exerted it; it doesn't
    # untap during that player's next untap step (app/rules/engine.start_next_turn)
    exerted: dict[str, str] = Field(default_factory=dict)
    # -- next untap step (wave 6A) -- "doesn't untap during its controller's / your next untap step" (502.3;
    # app/rules/next_untap.py): {"oid": object id, "player": a player id, or "controller" (read at the untap step)}
    stay_tapped: list[dict[str, str]] = Field(default_factory=list)
    once_per_turn: dict[str, int] = Field(default_factory=dict)  # "<card>:<ability>" -> turn it was activated
    # Activation restrictions and trigger limits (app/rules/restrictions.py): how many times an
    # object's ability was activated / triggered — "<object id>:<ability index>:t<turn>" -> count this
    # turn, "<object id>:<ability index>:game" -> count this game (602.5b, 400.7: per object).
    ability_uses: dict[str, int] = Field(default_factory=dict)
    # -- modal triggered/activated abilities (wave 1A) --
    # "Choose one that hasn't been chosen [this turn]": the modes already chosen for that ability of
    # that object (app/rules/modal_abilities.py) — "<object id>:<ability index>:game" (the game) or
    # "<object id>:<ability index>:t<turn>" (that turn) -> mode numbers. Kept per object (400.7: a new
    # object has no memory) and not per controller; a mode counts once it was chosen, whether or not
    # the ability resolved.
    modes_chosen: dict[str, list[int]] = Field(default_factory=dict)
    turn_seen: int = 0  # last turn number the bookkeeping saw
    turn_started: dict[str, int] = Field(default_factory=dict)  # player -> number of their latest turn
    controlled_since: dict[str, ControlMark] = Field(default_factory=dict)
    # -- control (wave 3K) -- the cards whose controller a layer-2 effect set (so that when the effect ends
    # they revert to their owner, 613.1b), not one a player moved by hand
    control_changed: list[str] = Field(default_factory=list)
    conceded: list[str] = Field(default_factory=list)
    lost: dict[str, str] = Field(default_factory=dict)  # player -> why (0 life, poison, …)
    winner: str | None = None
    drew_from_empty: list[str] = Field(default_factory=list)  # loses at the next state-based check
    deathtouched: list[str] = Field(default_factory=list)  # creatures dealt damage by a deathtouch source
    prevention: dict[str, int] = Field(default_factory=dict)  # player / object id -> damage to prevent this turn
    regen_shields: dict[str, int] = Field(default_factory=dict)  # object id -> regeneration shields this turn
    linked_exile: dict[str, list[str]] = Field(default_factory=dict)  # source object -> cards exiled "until it leaves"
    # -- exiled with (wave 6D) -- source object -> the objects its abilities exiled (607.2a: "the exiled card",
    # "cards exiled with ~"; app/rules/exiled_with.py)
    exiled_with: dict[str, list[str]] = Field(default_factory=dict)
    delayed: list[DelayedTrigger] = Field(default_factory=list)  # delayed triggered abilities (603.7; app/rules/delayed.py)
    exile_if_leaves: list[str] = Field(default_factory=list)  # objects exiled instead of leaving (unearth)
    # Replacement / prevention records with a duration (app/rules/replacements.py): "Prevent all
    # combat damage that would be dealt this turn" and friends. Each: {"id", "kind", "turn",
    # "controller", "source", "scope"}; a record for another turn has expired (614.3, 615.3).
    replacements: list[dict[str, Any]] = Field(default_factory=list)
    # -- refused grants/replacements (wave 3R2) -- 614.10 "skips their next …" effects waiting for that
    # occurrence (app/rules/skips.py): {"id", "player", "what": "untap"|"upkeep"|"draw"|"combat"|"turn", "label"}
    skips: list[dict[str, Any]] = Field(default_factory=list)
    # -- extra turns (wave 8A) -- 500.7 (app/rules/extra_turns.py): the extra turns waiting (the last is taken first),
    # {"player", "label"}; and the player whose regular turn was the latest (the turn order goes on after them)
    extra_turns: list[dict[str, Any]] = Field(default_factory=list)
    turn_base: str | None = None
    # … and "can't gain life this turn / for the rest of the game" (614.17; app/rules/cant_gain.py):
    # {"id", "player", "controller", "turn" (None: the rest of the game), "label"}
    cant_gain: list[dict[str, Any]] = Field(default_factory=list)
    # -- cast limits (wave 5E) -- "… can't cast spells this turn / until your next turn" (601.3, 602.5;
    # app/rules/cast_limits.py): {"id", "player", "controller", "until": "turn"|"next_turn", "turn", "filter", "from",
    # "act", "label"}
    cast_limits: list[dict[str, Any]] = Field(default_factory=list)
    # … and a player's hexproof / shroud / protection from resolved effects (702.11c, 702.16, 702.18;
    # app/rules/player_shields.py): {"id", "player", "controller", "shield": "hexproof"|"shroud"|"protection", "quality",
    # "until": "turn"|"next_turn", "turn", "label"}
    player_shields: list[dict[str, Any]] = Field(default_factory=list)
    # … and abilities granted to graveyard cards this turn (app/rules/graveyard_grants.py): "gains flashback until
    # end of turn" — {"id", "oid" (the card as the object it was then, 400.7), "card", "turn", "flashback", "controller"}
    graveyard_grants: list[dict[str, Any]] = Field(default_factory=list)
    # -- mana riders (wave 5A) -- "Until end of turn, whenever a player taps an Island for mana, that player adds an
    # additional {U}." (High Tide; app/rules/tap_mana.py): {"turn", "controller", "def"}
    tap_mana: list[dict[str, Any]] = Field(default_factory=list)
    # 903.9b: commanders just put into their owner's hand / library (card id -> "hand" | "library")
    # whose owner hasn't yet said whether it goes to the command zone instead (asked before priority)
    pending_903_9b: dict[str, str] = Field(default_factory=dict)
    # 903.9b asked *before* the move, as a resolving effect is about to put a commander into its
    # owner's hand or library: "<object id>><hand|library>" -> "yes" (command zone) / "no",
    # consumed by that move (app/rules/replacements.ask_903_9b_first)
    answers_903_9b: dict[str, str] = Field(default_factory=dict)
    # "As ~ enters, choose …" answers given while a permanent spell / land is about to enter (card
    # id -> {"color": "Blue"}), consumed by the entry (614.12a)
    entry_choices: dict[str, dict[str, str]] = Field(default_factory=dict)
    devoured: dict[str, int] = Field(default_factory=dict)  # -- keyword mechanics (wave 9D) -- object -> permanents it devoured (702.82b)
    buyback: list[str] = Field(default_factory=list)  # stack objects cast with buyback
    dashed: list[str] = Field(default_factory=list)
    evoked: list[str] = Field(default_factory=list)  # evoked spells: sacrificed as they enter (702.74)
    rebound_cast: list[str] = Field(default_factory=list)  # rebound spells cast from a hand (on the stack)
    rebounding: list[str] = Field(default_factory=list)  # exiled by rebound: cast at the owner's next upkeep  # dashed spells: haste + back to hand at end step
    suspended: list[str] = Field(default_factory=list)  # cards exiled with suspend (702.62)
    free_casts: list[str] = Field(default_factory=list)
    alt_costs: dict[str, str] = Field(default_factory=dict)  # card -> the cost to pay instead (madness)  # cards the engine lets be cast without paying (suspend)
    suspend_haste: list[str] = Field(default_factory=list)  # suspended creature spells: haste when they enter
    renowned: list[str] = Field(default_factory=list)  # rules objects that became renowned (702.112)
    monstrous: list[str] = Field(default_factory=list)  # rules objects that became monstrous (701.37b)
    levels: dict[str, int] = Field(default_factory=dict)  # -- Class (wave 16A) -- 716.2b: rules object -> class level (none: level 1, 716.2d)
    suspected: list[str] = Field(default_factory=list)  # rules objects that are suspected (701.60: -- suspect (wave 12A) --)
    prepared: dict[str, str] = Field(default_factory=dict)  # -- prepared (wave 13C, 722.3) -- permanent's rules object -> its copy in exile
    damaged: dict[str, int] = Field(default_factory=dict)  # player -> last turn they were dealt damage (bloodthirst)
    echo_done: list[str] = Field(default_factory=list)  # "<object>:<controller>" whose echo upkeep came
    flashback: list[str] = Field(default_factory=list)  # stack objects cast with flashback (exiled as they leave)
    # Combat bookkeeping; the attack/block markers on the table are the visible truth.
    blocked: list[str] = Field(default_factory=list)  # attackers that became blocked (stay blocked)
    no_attackers: bool = False  # nobody attacked: skip blockers and damage (rule 508.8)
    blockers_pending: list[str] = Field(default_factory=list)  # defending players still to declare
    combat_round: Literal["", "first", "done"] = ""
    # -- multiple blocks (wave 13B, 14A) -- 510.1c-d: how a creature divides its combat damage among the creatures it is
    # blocked by / blocks (creature card -> target card or player -> damage), answered before the round is dealt and dropped once it is
    block_split: dict[str, dict[str, int]] = Field(default_factory=dict)
    # -- combat (wave 5C) -- 500.8: the phases still to come after the current one when effects added some (the
    # last is the phase that would have come next), and how many combat phases began this turn
    extra_phases: list[str] = Field(default_factory=list)
    combats: int = 0
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
    # A permanent's later timestamp, when it got one after entering (613.7e: an Aura, Equipment or
    # Fortification each time it becomes attached; 613.7g: a double-faced permanent each time it
    # transforms): card id -> a number from the ``next_object`` counter, so it orders against the
    # objects' entry timestamps and resolved effects' ``object_seq``. The object's identity
    # (``objects``) is untouched. Read by ``app.rules.layers.timestamp``.
    restamped: dict[str, int] = Field(default_factory=dict)
    # -- transform (wave 11A) -- 701.27f: card id -> the ``next_object`` number when that double-faced permanent last
    # transformed (a ``face`` change on the battlefield); an ability put on the stack earlier (its own object number is
    # lower) no longer transforms it. Cleared when it becomes a new object (400.7).
    transformed: dict[str, int] = Field(default_factory=dict)
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
    draws_this_turn: dict[str, int] = Field(default_factory=dict)  # player -> cards drawn (for "your second card")
    draws_turn: int = 0
    # Aura spells on the stack -> what they target (303.4a); they enter attached to it (303.4f).
    aura_targets: dict[str, TargetRef] = Field(default_factory=dict)
    # Battles on the battlefield (object id) -> their protector (310.9; app/rules/battles.py).
    protectors: dict[str, str] = Field(default_factory=dict)
    # -- chosen player (wave 4J) -- "As ~ enters, choose an opponent / a player": object id -> the chosen player's id
    # (the permanent's "Chosen opponent: <name>" entry is only the display; app/rules/chosen.py). Older saves have
    # only the display name: chosen.player_of resolves it when exactly one player has that name.
    chosen_players: dict[str, str] = Field(default_factory=dict)
    # How each spell was paid for (stack object id -> record); follows the spell onto the battlefield.
    payments: dict[str, PaymentRecord] = Field(default_factory=dict)
    # Each player's intents this turn, for REPEAT LAST VALIDATED SEQUENCE (payloads, newest last).
    recent: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    recent_turn: int = 0
    # Cast / play permissions granted by effects, cost modifiers with a duration, and which top
    # library cards are revealed by permanents on the table (app/rules/permissions.py).
    permissions: list[Permission] = Field(default_factory=list)
    cost_modifiers: list[CostModifier] = Field(default_factory=list)
    top_reveals: list[TopReveal] = Field(default_factory=list)
    # -- conditional / instead clauses (wave 1B) --  this turn's and last turn's history (TurnLog)
    turn_log: TurnLog = Field(default_factory=TurnLog)
    last_turn_log: TurnLog | None = None
    # -- replacement effects stage 2 (wave 2E; app/rules/replace.py) --
    # Cards each player actually drew in the step ``replace_step_key`` ("<turn>:<phase>"), counted as
    # they're drawn (for "except the first one they draw in each of their draw steps", 504.1).
    replace_step_key: str = ""
    replace_step_draws: dict[str, int] = Field(default_factory=dict)
    # -- counters & designations (wave 3E; app/rules/designations.py) --
    # 309.2a / 309.4: each player's dungeon card in the command zone and the room their venture marker is on
    dungeons: dict[str, DungeonMark] = Field(default_factory=dict)
    completed_dungeons: dict[str, list[str]] = Field(default_factory=dict)  # 309.7: player -> dungeons completed, in order
    ring_tempted: dict[str, int] = Field(default_factory=dict)  # 701.54c: player -> times the Ring tempted them (their emblem)
    ring_bearers: dict[str, str] = Field(default_factory=dict)  # 701.54a: player -> their Ring-bearer (rules object id)
    # -- keyword actions & face-down (wave 3F) -- firebending (702.189a): the {R} each player added that
    # they don't lose as steps end until end of combat (player -> how much of the red in their pool)
    combat_mana: dict[str, int] = Field(default_factory=dict)
    # -- refused copy/mana (wave 3R3; app/rules/kept_mana.py) -- "Until end of turn, you don't lose this mana as
    # steps and phases end" (500.4, 106.4): {"player", "mana": {sym: n}, "until": "end_of_turn" | "end_of_combat",
    # "turn"}; never more than that player's pool holds (spending uses the other mana first)
    kept_mana: list[dict[str, Any]] = Field(default_factory=list)
    # -- refused look/cast-free (wave 3R5) -- a free cast made while a spell or ability resolves (608.2g):
    # {"card", "ctx", "e"} — the resolution to continue once that cast is done or abandoned
    # (app/rules/permissions.free_cast_done); and the stack objects cast "without paying" whose
    # "If that spell would be put into your graveyard, exile it instead" applies (614.1a)
    free_cast_then: dict[str, Any] | None = None
    exile_if_graveyard: list[str] = Field(default_factory=list)
    # -- counters (wave 5H) -- keyword counters (122.1b) on permanents: card id -> kind -> [next_object, timestamp]
    # as the last counter of that kind was put on it (613.7c: all counters of a kind share the newest timestamp), so
    # layer 6 orders them against effects that add or remove abilities (613.1f, 613.7; app/rules/layers.py)
    counter_stamps: dict[str, dict[str, list[int]]] = Field(default_factory=dict)

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
# ContinuousEffect.source of the copy effect of a card entering as a copy (app/rules/copying.py,
# 707.5): set up on the card's object before it moves, it follows the card to the object it becomes
# on the battlefield (:func:`_diff`) — whatever number that object gets.
ENTERING_COPY = "entering:"


def _zone_name(key: str) -> str:
    return key.rsplit(":", 1)[-1]


def snapshot(state: GameState, card_id: str) -> ObjectSnapshot:
    c = state.cards[card_id]
    rules = state.rules
    token = c.token
    if token is not None and token.back is not None and c.face == 1:  # -- wave 3F -- a transformed double-faced token
        token = token.back
    return ObjectSnapshot(
        object_id=rules.object_id(card_id) if rules else card_id, card=card_id, printing=c.card_id, name=c.name,
        owner=c.owner, controller=c.controller, zone=c.zone, turn=state.turn.number, tapped=c.tapped,
        face_down=c.face_down, face=c.face, is_token=c.is_token,
        token_power=token.power if token else None, token_toughness=token.toughness if token else None,
        token_type_line=token.type_line if token else None, token_colors=list(token.colors) if token else [],
        commander_key=c.commander_key, counters=dict(c.counters), damage=c.damage,
        effects=[e.value or e.name for e in c.effects], attacking=c.attacking is not None,
        blocking=c.blocking is not None, attached_to=c.attached_to, text=token.text if token else "",
        attached_player=c.attached_player,  # -- attached events (wave 4L) --
        x=c.stack_info.x if c.zone == "stack" and c.stack_info is not None else None,  # (wave 5B)
    )


class Capture:
    """The table just before one step is applied (in memory only, never saved): what ``track``
    compares against to find zone changes, counters and taps, and the objects' last known
    information for anything that leaves the battlefield or the stack."""

    __slots__ = ("zones", "snaps", "resources", "types", "designations")

    def __init__(self, state: GameState) -> None:
        self.zones = {cid: c.zone for cid, c in state.cards.items()}
        self.snaps = {
            cid: snapshot(state, cid) for cid, c in state.cards.items() if _zone_name(c.zone) in TRACKED_ZONES
        }
        self.resources = {pid: dict(p.resources) for pid, p in state.players.items()}
        # -- counters & designations (wave 3E) -- the monarch (725), the initiative (726), day / night (731)
        self.designations = (state.table.monarch, state.table.initiative, state.table.day_night)
        # card id -> card types as they are now (layers applied) for the permanents the rules engine
        # is about to move off the battlefield (set by Plan.do; empty for a step made by hand)
        self.types: dict[str, list[str]] = {}


def capture(state: GameState) -> Capture | None:
    return Capture(state) if state.rules is not None else None


def emit(state: GameState, kind: EventKind, **fields: Any) -> None:
    """Record an event of the step being applied (handlers call this for what a table diff can't
    show: damage as opposed to life loss, life gained and lost in the same step)."""
    rules = state.rules
    if rules is None:
        return
    rules.events.append(Event(batch=rules.batch + 1, kind=kind, turn=state.turn.number, **fields))
    if kind in ("life_gain", "life_loss", "drew"):  # -- conditional / instead clauses (wave 1B) --
        _note_player_fact(state, kind, fields.get("player"), int(fields.get("amount") or 1))


# -- this turn's history (conditional / instead clauses, wave 1B) --------------------------------------
def turn_log_now(state: GameState) -> TurnLog | None:
    """This turn's log, for writing: a new turn starts a fresh one, and the one just ended is kept
    as ``last_turn_log`` — only if it really was the turn before, so "last turn" never reads an
    older one."""
    rules = state.rules
    if rules is None:
        return None
    n = state.turn.number
    log = rules.turn_log
    if log.turn != n:
        rules.last_turn_log = log if log.turn == n - 1 else None
        log = rules.turn_log = TurnLog(turn=n)
    return log


def _note_player_fact(state: GameState, kind: str, player: str | None, amount: int) -> None:
    log = turn_log_now(state)
    if log is None or not player:
        return
    book = {"life_gain": log.gained, "life_loss": log.lost, "drew": log.drew}[kind]
    book[player] = book.get(player, 0) + amount


def note_attack(state: GameState, player: str, attackers: list[str] | None = None) -> None:
    """508.1: ``player`` declared one or more attackers this turn ("if you attacked this turn"); ``attackers``: the
    objects declared (wave 4D: "if you attacked with two or more creatures this turn" — every combat of the turn)."""
    log = turn_log_now(state)
    if log is not None and player not in log.attacked:
        log.attacked.append(player)
    if log is not None and attackers:  # -- this-turn history (wave 4D) --
        seen = log.attackers.setdefault(player, [])
        seen += [a for a in attackers if a not in seen]


def track(state: GameState, before: Capture | None = None, *, manual: bool = False, actor: str | None = None,
          group: int = 0) -> None:
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
            rules.controlled_since[card_id] = ControlMark(controller=card.controller, turn=state.turn.number,
                                                          changed=mark is not None)
    for card_id in [c for c in rules.controlled_since if c not in on_battlefield]:
        del rules.controlled_since[card_id]
    if before is not None:
        _diff(state, rules, before, manual, actor, group)  # (actor: wave 5H, group: wave 7C)
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


def _entry_order(state: GameState, before: Capture) -> list[tuple[str, str]]:
    """The step's cards in the order they get their new object numbers (613.7d: a timestamp as
    they enter a zone). 613.7m: objects entering the battlefield simultaneously are timestamped in
    APNAP order — the active player's first (among them, in the order the step lists them), then
    each other player's in turn order; everything else keeps the table's order."""
    seats = state.seat_order
    start = seats.index(state.turn.active_player) if state.turn.active_player in seats else 0
    apnap = {p: (i - start) % len(seats) for i, p in enumerate(seats)} if seats else {}

    def key(item: tuple[int, tuple[str, str]]) -> tuple[int, int, int]:
        i, (card_id, old_zone) = item
        card = state.cards.get(card_id)
        if card is None or _zone_name(card.zone) != "battlefield" or _zone_name(old_zone) == "battlefield":
            return (0, 0, i)
        listed = state.zones.get(card.zone, [])
        return (1, apnap.get(card.controller, len(seats)), listed.index(card_id) if card_id in listed else i)

    changed = [(cid, zone) for cid, zone in before.zones.items()
               if (card := state.cards.get(cid)) is None or card.zone != zone]  # (the rest: no new object)
    return [item for _, item in sorted(enumerate(changed), key=key)]


# -- counters (wave 5H) -- the keyword counters whose keyword the engine gives the object (122.1b, 613.1f): static
# keywords it already carries out ("exalted" and "decayed" counters are left to the players)
KEYWORD_COUNTERS = frozenset({"flying", "first strike", "double strike", "deathtouch", "haste", "hexproof",
                              "indestructible", "lifelink", "menace", "reach", "shadow", "trample", "vigilance"})


def _diff(state: GameState, rules: RulesState, before: Capture, manual: bool, actor: str | None = None,
          group: int = 0) -> None:
    departures = state.departures()
    for card_id, old_zone in _entry_order(state, before):
        card = state.cards.get(card_id)
        new_zone = card.zone if card is not None else departures.get(card_id)
        if card is not None and new_zone == old_zone:
            continue
        old_name = _zone_name(old_zone)
        new_name = _zone_name(new_zone) if new_zone else None
        if card is not None and old_name == new_name and old_name != "battlefield":
            continue  # e.g. a hand passed between players' libraries is still a library card
        if {old_name, new_name} == {"battlefield", "phased"}:
            continue  # -- phasing (wave 13D) -- 702.26d: phasing is no zone change: same object, no leave / enter triggers
        if old_name == new_name == "battlefield":
            continue  # a control change is not a zone change: same object (rule 400.7 doesn't apply)
        old_oid = rules.object_id(card_id)
        snap = before.snaps.get(card_id)
        if snap is not None:
            rules.lki[old_oid] = snap.model_copy(update={"turn": state.turn.number})
            rules.lki[old_oid].copy_recipe = copy_recipe_of(rules, old_oid)  # -- copy system (wave 2F) --
            # -- sagas & attached-object triggers (wave 3S): what was attached to it (603.10a) --
            rules.lki[old_oid].attached = [c for c, s in before.snaps.items() if s.attached_to == card_id]
        new_oid = None
        rules.restamped.pop(card_id, None)  # a new object gets its own timestamp as it enters (613.7d)
        rules.transformed.pop(card_id, None)
        rules.counter_stamps.pop(card_id, None)  # (wave 5H: its counters are gone, 122.2)
        if card is not None:
            rules.next_object += 1
            rules.objects[card_id] = rules.next_object
            new_oid = rules.object_id(card_id)
            if new_name == "battlefield" and old_name == "stack":  # -- refused grants/replacements (wave 3R2) --
                for rec in rules.replacements:  # 609.7a: a shield on a permanent spell covers the permanent it became
                    oids = ((rec.get("match") or {}).get("source") or {}).get("oids")
                    if isinstance(oids, list) and "becomes:" + old_oid in oids:
                        oids.append(new_oid)
            if new_name == "battlefield":  # 707.5: the copy effect it is entering with is the new object's
                for eff in rules.effects:
                    if eff.layer == "1" and eff.source == ENTERING_COPY + card_id and old_oid in eff.affected:
                        eff.affected.append(new_oid)
        else:
            rules.objects.pop(card_id, None)
        if old_name in ("library", "hand") and new_name in ("library", "hand", None) and snap is None:
            continue  # private shuffling around: new objects, but nothing public happened
        if old_name == "battlefield" and snap is not None:  # -- conditional / instead clauses (wave 1B) --
            log = turn_log_now(state)
            if log is not None:
                log.left.append(Departure(card=card_id, object_id=old_oid, controller=snap.controller, to=new_name or "",
                                          types=before.types.get(card_id)))
        elif old_name == "graveyard" and (log := turn_log_now(state)) is not None:
            log.left_graveyard.append(old_zone.split(":")[0])  # (a zone key is "<owner>:graveyard")
        if new_name == "graveyard" and new_zone and card is not None and card.card_id is not None \
                and (log := turn_log_now(state)) is not None:  # (a token is no card: it never "descends")
            log.entered_graveyard.append(Arrival(card=card_id, owner=new_zone.split(":")[0]))
        if new_name == "battlefield" and card is not None and new_oid is not None \
                and (log := turn_log_now(state)) is not None:  # -- refused modal/conditional (wave 3R1) --
            log.entered.append(Entry(card=card_id, object_id=new_oid, controller=card.controller,
                                     tapped=card.tapped))  # (-- entry forms (wave 5F) --)
        emit(state, "zone_change", object_id=old_oid, new_object_id=new_oid, card=card_id,
             player=(card.controller if card is not None else snap.controller if snap else None),
             from_zone=old_zone, to_zone=new_zone)
    for card_id, card in state.cards.items():
        if card_id not in before.zones and _zone_name(card.zone) in TRACKED_ZONES:
            if card_id not in rules.objects:  # a created object is numbered like one that entered (613.7d)
                rules.next_object += 1
                rules.objects[card_id] = rules.next_object
            emit(state, "zone_change", new_object_id=rules.object_id(card_id), card=card_id, player=card.controller,
                 to_zone=card.zone)  # created: a token, a copy, an ability on the stack
            if _zone_name(card.zone) == "battlefield" and (log := turn_log_now(state)) is not None:  # (wave 3R1)
                log.entered.append(Entry(card=card_id, object_id=rules.object_id(card_id), controller=card.controller,
                                         tapped=card.tapped))  # (-- entry forms (wave 5F) --)
    for card_id, snap in before.snaps.items():
        card = state.cards.get(card_id)
        if card is None or card.zone != snap.zone:
            continue
        oid = rules.object_id(card_id)
        for kind in sorted(set(snap.counters) | set(card.counters)):  # (sorted: wave 5H, 613.7c stamps)
            delta = card.counters.get(kind, 0) - snap.counters.get(kind, 0)
            if delta:
                emit(state, "counters", object_id=oid, card=card_id, counter=kind, amount=delta,
                     **({"actor": actor} if actor and delta > 0 else {}), **({"group": group} if group else {}))  # (5H, 7C)
            if kind in KEYWORD_COUNTERS:  # -- counters (wave 5H) -- 613.7c
                if card.counters.get(kind, 0) <= 0:
                    rules.counter_stamps.get(card_id, {}).pop(kind, None)
                elif delta > 0:
                    rules.timestamp += 1
                    rules.counter_stamps.setdefault(card_id, {})[kind] = [rules.next_object, rules.timestamp]
        if card.tapped != snap.tapped:
            emit(state, "tapped" if card.tapped else "untapped", object_id=oid, card=card_id)
        # 613.7e: an attachment gets a new timestamp each time it becomes attached; 613.7f: a
        # permanent each time it turns face up or down; 613.7g: a double-faced permanent each
        # time it transforms (a face change on the battlefield)
        if _zone_name(card.zone) == "battlefield" and (
                (card.attached_to is not None and card.attached_to != snap.attached_to)
                or card.face != snap.face or card.face_down != snap.face_down):
            rules.next_object += 1
            rules.restamped[card_id] = rules.next_object
            if card.face != snap.face:
                rules.transformed[card_id] = rules.next_object
    for pid, old in before.resources.items():
        p = state.players.get(pid)
        if p is None:
            continue
        for kind in set(old) | set(p.resources):
            delta = p.resources.get(kind, 0) - old.get(kind, 0)
            if delta:
                emit(state, "player_counters", player=pid, counter=kind, amount=delta)
    # -- counters & designations (wave 3E) -- a player became the monarch (725.3) / took the initiative
    # (726.3), day became night or night day (731.1a): ``counter`` names the designation, ``from_zone``
    # what it was ("" for none)
    monarch, initiative, day_night = before.designations
    if state.table.monarch != monarch and state.table.monarch:
        emit(state, "designation", player=state.table.monarch, counter="monarch", from_zone=monarch or "")
    if state.table.initiative != initiative and state.table.initiative:
        emit(state, "designation", player=state.table.initiative, counter="initiative", from_zone=initiative or "")
    if state.table.day_night != day_night and state.table.day_night:
        emit(state, "designation", counter=state.table.day_night, from_zone=day_night or "")
    departures.clear()


# -- copy system (wave 2F) ---------------------------------------------------------------------
def copy_recipe_of(rules: RulesState, object_id: str) -> CopyRecipe | None:
    """The copy recipe applying to a rules object (613.2a, layer 1a): the latest copy effect by
    timestamp (613.7), or None. Pure data (app/rules/copying.py builds characteristics from it)."""
    best: ContinuousEffect | None = None
    for e in rules.effects:
        if e.layer == "1" and e.copy_recipe is not None and object_id in e.affected and (best is None or e.timestamp > best.timestamp):
            best = e
    return best.copy_recipe if best is not None else None
