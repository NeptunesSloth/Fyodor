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

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from app.game.mana_cost_templates import ForetellCostReceipt

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


# -- cancelling a cast (wave 24D) -- 601.2: the announcement choices (modes, targets) of a spell or ability that can still be taken back:
# the chooser's view says ``cancelable`` and the answer ["cancel"] is legal (app/rules/casting.py: ``cancelled``).
CANCELLABLE_STEPS = ("paid_x_number", "delegated_target_opponent", "cast_target", "cast_group", "cast_modes", "cast_slot_target", "phyrexian", "casualty_x", "flashback_choice", "spell_symbols")  # (wave 50B: the Phyrexian mana choice, 601.2b)


def cancelable(d: Any) -> bool:
    """Can this decision be answered ["cancel"]? (-- review (wave 24D) -- not a free cast begun as an effect resolves (608.2g): the
    resolution that offered it is over, so cancelling would strand the card and keep its grant; its own "no" is the way out.
    -- review (wave 29B) -- unless its end is recorded, ``abandon``: casting._announcing, permissions.free_cast_abandoned.)"""
    resume = getattr(d, "resume", None) or {}
    return resume.get("step") in CANCELLABLE_STEPS and (not (resume.get("intent") or {}).get("free") or bool(resume.get("abandon")))


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
    # -- controlling another player (wave 18H) -- 723.5: the player who makes this choice for ``player`` (None: they do)
    decider: str | None = None
    # -- declaration choosers (wave 110A) -- the decider only makes this choice: it sees nothing of ``player`` beyond the table (not 723.4)
    blind: bool = False


class PlayerControl(BaseModel):
    """-- controlling another player (wave 18H) -- 723.1: "You control target player during that player's next turn"
    (app/rules/player_control.py). "pending" until the controlled player's next turn begins, then "active" for that turn."""

    controlled: str
    controller: str
    status: Literal["pending", "active", "done"] = "pending"
    turn: int = 0  # the turn number it became active on (723.1: it ends with that turn)
    combat: bool = False  # -- wave 110A -- Secret of Bloodbending: only the controlled player's next combat phase (723.1 "phase"); "done" once it ended
    extra_after: int = 0  # Emrakul: "After that turn, that player takes an extra turn" (kept when 723.1a overwrites)
    label: str = ""
    # -- Word of Command (wave 110E) -- 723.1: control that lasts while the stack object ``obj`` resolves instead of a turn (pending until it starts to);
    # ``lands_only``: the controlled player may activate mana abilities of lands only
    obj: str = ""
    lands_only: bool = False


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
    # First turn this unknown-age control relationship was actually observed.
    observed_from_turn: int | None = None


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
    # -- graveyard order (wave 40C) -- 404.3: ask me to arrange every batch of two or more cards put into my graveyard together, not only
    # when a card on the table reads a graveyard's order (it covers a reader in my hand or library, app/rules/graveyard_order.py)
    ask_graveyard_order: bool = False
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
class CopyEntrySource(BaseModel):
    """The selected source when an entry copy replacement is applied, not copiable characteristics."""

    card: str
    object_id: str
    controller: str


class CopyExcept(BaseModel):
    """The exceptions of one copy effect (707.9): values it sets or adds as part of the copying
    process, which then belong to the copy's copiable values (707.9a-b). Applied in this order:
    name, power/toughness (707.9d: a characteristic-defining ability for P/T isn't copied), types
    added or supertypes removed ("it isn't legendary"), colors set (707.9d), abilities gained
    (707.9a: keyword lines like "Haste", or a quoted ability's text)."""

    name: str | None = Field(default=None, max_length=200)
    power: str | None = Field(default=None, max_length=8)
    toughness: str | None = Field(default=None, max_length=8)
    loyalty: int | None = Field(default=None, ge=0)  # 707.9: copiable starting loyalty (casualty X).
    add_types: list[str] = Field(default_factory=list)
    add_subtypes: list[str] = Field(default_factory=list)
    add_supertypes: list[str] = Field(default_factory=list)
    remove_supertypes: list[str] = Field(default_factory=list)
    set_colors: list[str] | None = None
    add_text: list[str] = Field(default_factory=list)
    remove_keywords: list[str] = Field(default_factory=list)  # Copiable exceptions such as losing soulbond.
    add_colors: list[str] = Field(default_factory=list)  # "in addition to its other colors"
    # -- token copies & attach on entry (wave 5J) -- "except it's a 4/4 black Zombie": its creature types are these
    # (205.1a: they replace the copied ones; other subtypes stay), changeling isn't copied (707.9d)
    set_creature_types: list[str] | None = None
    pt_self110a: bool = False  # -- wave 110A -- "its power and toughness are equal to this creature's power and toughness" (Hulking Metamorph): filled in as it enters
    no_mana_cost: bool = False  # -- keywords (wave 15E) -- "it has no mana cost" (embalm 702.128a, eternalize 702.129a): a copiable value
    # -- copy exceptions (wave 24A) -- 707.9b: "it's an artifact" / "it loses all other card types": the card types are exactly these;
    # 707.9a/f: abilities gained only if the result is that type ("if it's a creature, … has changeling"); 707.9c-d: "it doesn't copy
    # that creature's color" (``keep_color``: the object's own colors, filled in as the copy effect is made)
    set_types: list[str] | None = None
    text_if: dict[str, list[str]] = Field(default_factory=dict)
    keep_color: bool = False
    # 707.9e: "it enters with an additional +1/+1 counter on it": an additional effect of the replacement, NOT a copiable value — read
    # only while parsing (``copying.define_static`` moves these onto the definition). {"counter", "n": int | "X", "if_type", "if_control"}
    enter_counters: list[dict[str, Any]] = Field(default_factory=list)


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
    prototyped: bool = False  # -- casting extras (wave 18E) -- 718.2a / 718.3c-d: the alternative cost, power and toughness are copiable


# -- game objects, last known information, events -------------------------------------------
class EntryCharacteristics(BaseModel):
    """CR611.2e: noncopiable characteristics supplied as a nontoken permanent enters."""

    set_name: str | None = None
    set_types: list[str] | None = None
    add_types: list[str] = Field(default_factory=list)
    set_creature_types: list[str] | None = None
    set_artifact_types: list[str] | None = None  # -- (wave 110C) -- Vraska, the Silencer: "It's a Treasure artifact" as it enters (205.1a)
    add_subtypes: list[str] = Field(default_factory=list)
    set_colors: list[str] | None = None
    add_colors: list[str] = Field(default_factory=list)
    power: int | None = None
    toughness: int | None = None
    add_keywords: list[str] = Field(default_factory=list)
    remove_abilities: bool = False
    add_abilities: list[str] = Field(default_factory=list)
    timestamp: int = 0
    controller: str = ""
    source: str | None = None
    source_card: str | None = None
    label: str = ""


class AttachedObjectFact(BaseModel):
    object_id: str
    controller: str
    types: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)


class ObjectSnapshot(BaseModel):
    """An object as it last existed in a public zone (Last Known Information, rule 608.2h).
    Recorded *before* it left, never reconstructed from where it went."""

    object_id: str
    stickers101: list[dict[str, Any]] = Field(default_factory=list)  # Original public sticker markers at departure.
    choices: dict[str, str] = Field(default_factory=dict)  # exact public choices before this incarnation left
    ring_bearer: bool = False  # designation captured before zone-change reconciliation
    suspected: bool | None = None  # Pre-move designation; missing in legacy snapshots.
    card: str  # the physical card instance (may be gone: tokens cease to exist)
    printing: str | None = None
    name: str = ""
    owner: str
    controller: str
    zone: str
    turn: int = 0
    tapped: bool = False
    face_down: bool = False
    face_down_kind: Literal["generic", "morph", "disguise", "manifest", "cloak", "exile"] | None = None
    face_down_as: str | None = None
    face: int = 0
    is_token: bool = False
    token_source_id: str | None = None  # -- wave 110F -- the object that created this token (111.2), as it last existed (Dance of Many)
    token_power: str | None = None
    token_toughness: str | None = None
    token_type_line: str | None = None  # (a token's types and colors, for what it was: 608.2h)
    # Its power and toughness as it last existed (layers applied, counters included): recorded by
    # the rules engine as it moves the object (608.2h), None for moves made by hand
    power: int | None = None
    toughness: int | None = None
    base_power: int | None = None  # -- base power (wave 30J) -- 208.4b, as it last existed (608.2h): "with base power 0", "power greater than its base power"
    base_toughness: int | None = None
    token_colors: list[str] = Field(default_factory=list)
    token_mana_cost: str = ""  # (wave 49D) a token's mana cost, as it last existed (608.2h)
    commander_key: str | None = None
    counters: dict[str, int] = Field(default_factory=dict)
    damage: int = 0
    effects: list[str] = Field(default_factory=list)  # "+3/+3", "Flying" … (manual effect markers)
    attacking: bool = False
    attacking_without_target: str | None = None
    attack_defender_lost: bool = False
    entry_characteristics: EntryCharacteristics | None = None
    # -- trailing & intervening ifs (wave 38A) -- whom it was attacking as it last existed (508.1, 608.2h): "player:<id>" | "card:<id>"
    attack_on: str | None = None
    blocking: bool = False
    blocking_ids: list[str] = Field(default_factory=list)  # -- activated other (wave 52D) -- the attackers (card ids) it was blocking as it last existed (608.2h: "target creature it's blocking")
    blocked_by_ids: list[str] = Field(default_factory=list)  # -- block events (wave 53C) -- the creatures (card ids) blocking it as it last existed (608.2h: "each creature that was blocking it")
    banded_with_ids: list[str] = Field(default_factory=list)  # CR 608.2h: the other band members' object IDs as this object last existed.
    attached_to: str | None = None
    attached_object: str | None = None  # exact host as this Aura/Equipment last existed (608.2h); absent in older saves
    attached_player: str | None = None  # -- attached events (wave 4L) -- the player an Aura enchanted (a Curse)
    attachments_before: list[AttachedObjectFact] | None = None  # Native pre-departure types/controllers; None in older saves.
    # -- sagas & attached-object triggers (wave 3S) -- the permanents (card ids) attached to it as it
    # last existed: "When enchanted creature dies" looks back in time (603.10a)
    attached: list[str] = Field(default_factory=list)
    attached_objects: dict[str, str] = Field(default_factory=dict)  # exact attachment incarnations before departure
    attached_objects_known: bool = False  # legacy saves cannot reconstruct this receipt
    text: str = ""  # a custom token's rules text (it has no printing to look up)
    merged: list[dict[str, Any]] = Field(default_factory=list)  # -- merged permanents (wave 18D) -- its cards (MergedPart dumps; 730.3: it left as one object)
    melded: bool = False
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
    # -- goad (wave 48D) -- 701.15b, 608.2h: the players who had goaded it as it last existed ("Whenever a goaded creature dies"), recorded by the rules engine as it moves it
    goaded: list[str] = Field(default_factory=list)


EventKind = Literal[
    "fought",  # CR 701.14: actual fight participants, independent of damage.
    "player_lost_game",  # 603.10f: pre-loss battlefield watchers are captured on this event.
    "case_solved",  # The resolving controller reached a native To solve instruction (719.3).
    "library_shuffled",
    "zone_change",  # an object moved between zones (or ceased to exist: to_zone None)
    "damage_prevented",  # Actual committed prevention, distinct from damage dealt.
    "damage",  # damage dealt (to a creature, planeswalker or player): not the same as life loss
    "life_loss",
    "life_paid",  # life paid as a cost or payment (119.4), beside the life_loss it causes (wave 110D)
    "life_gain",
    "counters",  # counters put on / removed from an object (amount signed)
    "player_counters",  # poison, energy, experience, rad, tickets … (amount signed)
    "tapped",
    "untapped",
    "trained",  # -- trains (wave 110G) -- 702.149c: a resolving training ability put +1/+1 counters on ``card``
    "evolved",  # An evolve keyword ability actually put one or more +1/+1 counters.
    "exerted",  # 701.43: the player exerted this permanent
    "spell_cast",  # a player cast a spell (the object is the spell on the stack)
    "investigated",  # A completed investigate action, independent of replaced token count.
    "cycled",  # a player cycled a card (702.29: "when you cycle …")
    "plotted",  # -- (wave 110B) -- 702.170d: a card in exile became plotted (the plot special action or an effect)
    "foretold",  # A completed native foretell special action, not an effect making a card foretold.
    "milled",  # -- triggers (wave 17D) -- 701.17a: ``player`` milled ``card`` (read where it lies, in their graveyard)
    "land_played",  # -- entry forms (wave 5F) -- a player played a land (305.1: "when you play another land")
    "mana_added",  # a mana ability produced mana (106.3, 106.12a); convoke/improvise/delve never do
    "drew",  # a player drew a card (121.2: one event per card)
    "crewed",
    "crew_tapped",  # -- crew & saddle (wave 23D) -- 702.122b: a creature (``object_id``) tapped to pay the crew cost of ``by_card`` (``source``)
    "teamwork_tapped110j",  # -- (wave 110J) -- 702.194a: a creature (``object_id``) tapped to pay a teamwork cost (Agent Maria Hill)
    "saddle_tapped",  # 702.171c: likewise for a saddle ability
    "saddled",  # 702.171b: ``card`` became saddled
    "exploited",  # -- keyword triggers (wave 23D) -- 702.110b: ``card`` (object ``object_id``) was sacrificed to exploit ``by_card`` (``source``: its object)
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
    # -- attachment events (wave 30S) -- 603.2e, 701.3d: ``card`` (object ``object_id``) became attached to / unattached from the permanent
    # ``by_card`` (``source``: its object as it was; a player: ``player``); an attachment that left the battlefield was unattached (603.10c)
    "attached",
    "unattached",
]


class Event(BaseModel):
    """Something that happened. Events of one table step share a ``batch``: they happened
    simultaneously (destroy all creatures is one batch of zone changes, not N)."""

    non_discard: bool = False  # This native zone change was explicitly not a discard.
    mana_colors110i: list[str] = Field(default_factory=list)  # -- cards (wave 110I) -- a ``mana_added`` "tap" event: the colors (WUBRG) of the mana produced
    fighters90: list[ObjectSnapshot] = Field(default_factory=list)  # Exact native fight cohort before damage.
    crew_count80: int | None = None  # Native crew activation payment cardinality; unknown in old saves.
    loss_watchers: list[ObjectSnapshot] = Field(default_factory=list)
    attacking_player: str | None = None  # Combat damage-time attacking player; unknown in old saves.
    turn_start_life: int | None = None  # Losing player's actual life at this turn's native start.
    sticker101: dict[str, Any] | None = None  # Native placement receipt, absent in old saves.
    prevention: dict[str, Any] | None = None  # Native committed prevention receipt; absent in old saves.
    played_snapshot: ObjectSnapshot | None = None  # Public land face as played, even if entering was diverted.
    step_phase: str | None = None
    active_player: str | None = None
    counter_remaining: int | None = None  # after a counter change; remembers when a duration's last counter disappeared
    batch: int
    kind: EventKind
    turn: int = 0
    types: list[str] | None = None  # exerted: card types when the action happened
    object_id: str | None = None  # the object as it was (for zone changes: the old object, see ``lki``)
    new_object_id: str | None = None  # zone changes: the object it became
    card: str | None = None
    player: str | None = None  # the player affected (life, player counters, damage to a player)
    source: str | None = None  # the source object's id, when known
    cause110m: str | None = None  # (wave 110M) a life gain: the spell (card id) whose resolution or lifelink caused it
    from_zone: str | None = None
    to_zone: str | None = None
    amount: int = 0
    counter: str | None = None
    combat: bool = False
    manual: bool = False  # caused by a sandbox action, not by the rules engine
    # -- counters (wave 5H) -- counters put on an object: the player who put them (the step's actor: 122.6, 122.6a)
    actor: str | None = None
    looked: int = 0  # -- scry counts (wave 19C) -- a scry / surveil: how many cards it looked at (701.22d: fewer than N with a short library)
    group: int = 0  # -- counters (wave 7C) -- counters one instruction put in several steps share it (122.6); 0: alone
    by_card: str | None = None  # -- keyword triggers (wave 23D) -- "exploited": the creature with exploit (a card id)
    # -- dice (wave 24B) -- a ``designation`` event with counter "roll_die": one die rolled by ``player`` (706.2: ``amount`` its result after
    # modifiers, ``natural`` the number on the die, ``sides`` the die's size, ``nth`` how many dice they have rolled this turn, this one included)
    dice_total: int | None = None  # Sum of retained numeric roll results, after modifiers; absent in older saves.
    natural: int = 0
    nth: int = 0
    sides: int = 0
    source_targets: list[str] | None = None  # -- trigger damage (wave 110C) -- a ``damage`` event: the targets of the spell dealing it (115.9c), None for any other source
    pair110c: str | None = None  # -- soulbond (wave 110C) -- a ``damage`` event: the object paired with the damaged one when it was dealt (603.2: judged as the event happens)
    craft110b: bool = False  # -- wave 110B -- a zone change made while a craft ability's cost was paid (Market Gnome)
    cause110g: str | None = None  # -- wave 110G -- a zone change: controller of the resolving spell or ability that moved it (SBA and rules: None)
    excess: int = 0  # -- trigger damage (wave 39B) -- a ``damage`` event: the excess damage (120.10) the batch dealt to the permanent, on its first event


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
    new_object_id105: str | None = Field(default=None, max_length=80)  # Exact public successor; absent in legacy saves.
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
    # -- graveyard history (wave 36A) -- 400.7: "a card in your graveyard that was put there from the battlefield this turn" is read of the
    # object it is now: the object it became in the graveyard (``object_id``), the zone it came from (``from_zone``: "battlefield",
    # "library", "hand" …; None: an older save, not known) and the combat phase it happened in (``combat``: RulesState.combats, 0: not in combat)
    object_id: str | None = Field(default=None, max_length=80)
    from_zone: str | None = Field(default=None, max_length=20)
    combat: int = 0


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
    keywords83: list[str] | None = None  # As entered; absent old-save history is unknown, never current flying.
    colors: list[str] | None = None  # as entered; None is unknown in an older save, not its later color
    # -- entry forms (wave 5F) -- whether it entered tapped ("When this land enters untapped", "Whenever a permanent
    # you control enters tapped": part of the event, 603.2); None: not known (an older save)
    tapped: bool | None = None
    # -- history (wave 22E) -- the zone it entered from (a zone key, "<owner>:graveyard" / "<owner>:stack" …): "enters from your
    # graveyard", "if it entered from a graveyard" (603.2, 603.4); None: from nowhere (created) or an older save
    from_zone: str | None = Field(default=None, max_length=40)
    # -- trigger other (wave 51E) -- the object whose effect put it onto the battlefield (Kodama of the East Tree: "if it wasn't put onto the battlefield with
    # this ability"); None: nobody's, or an older save
    via: str | None = Field(default=None, max_length=80)
    token110e: bool = False  # -- history (wave 110E) -- a token (111.1): "put a nontoken permanent onto the battlefield" (Arboria)
    face_down110b: bool = False  # -- history (wave 110B) -- it entered face down (708.2: "entered the battlefield face down this turn", Oblivious Bookworm)
# -- end refused modal/conditional (wave 3R1) --


# -- this-turn history (wave 4D) --
class CastNote(BaseModel):
    """A spell cast this turn, as it became cast (601.2i; 608.2i: "if you've cast a noncreature spell this turn"
    reads the spell as it was then — whether it resolved, was countered or is still on the stack doesn't matter).
    Spells on the stack are public: a face-down spell is recorded with its face-down characteristics (708.2)."""

    kicked77: bool | None = None  # Actual paid kicker; excludes synthetic awaken/gift/bargain own-effect aliases.
    names: list[str] | None = None  # Public as-cast names; None means an older receipt lacks this fact.
    player: str = Field(max_length=64)
    object_id: str = Field(max_length=80)
    types: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)
    supertypes: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    mv: float = 0
    cast_from: str | None = Field(default=None, max_length=20)  # "hand", "graveyard", "exile", "command" …
    alt: str | None = Field(default=None, max_length=20)  # -- void (wave 19E) -- the alternative cost it was cast for ("warp": 702.185a)
    mana_tags: list[list[str]] = Field(default_factory=list)  # mana source traits as cast, retained after payment records leave
    became: str | None = Field(default=None, max_length=80)  # the permanent a permanent spell became (608.3)
    x_cost: bool = False  # -- history (wave 22E) -- its mana cost has {X} ("a spell with {X} in its mana cost", 107.3); older saves: False
    keywords: list[str] = Field(default_factory=list)  # -- cant restrictions (wave 46A) -- the keywords it had as cast ("the first creature spell with flying you cast", Momo)
    face_down: bool = False  # -- cant restrictions (wave 46A) -- it was cast face down ("the first face-down creature spell you cast each turn", Kadena); older saves: False


class TurnFact(BaseModel):
    """Something a player did, or that happened to a player, this turn (608.2i): ``kind`` "token" (111.2: ``player``
    created a token — its owner), "discard" (701.9a), "sacrifice" (701.21a), "damage" (``player`` was dealt
    ``amount`` damage, ``combat``; ``source_types`` / ``source_supertypes`` the source as it was then), "scry" /
    "surveil" (701.22, 701.25; nothing about the cards), "counters" (``amount`` ``counter`` counters were put on a
    permanent ``player`` controlled). ``types`` …: the object concerned, as it was then."""

    kind: str = Field(max_length=20)
    from_zone: str | None = Field(default=None, max_length=80)  # Actual origin of a land play; None in older receipts.
    player: str = Field(max_length=64)
    object_id: str | None = Field(default=None, max_length=80)
    types: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)
    supertypes: list[str] = Field(default_factory=list)
    token: bool = False
    amount: int = 1
    combat: bool = False
    counter: str | None = Field(default=None, max_length=40)
    mv110e: int = 0  # -- wave 110E -- an "exile" fact: the mana value of the card as it was put into exile (Bell Borca)
    source_types: list[str] = Field(default_factory=list)
    source_colors: list[str] = Field(default_factory=list)  # Colors as this source dealt damage (608.2i).
    source_supertypes: list[str] = Field(default_factory=list)
    # -- static_other sweep (wave 17C) -- prowl (702.76a): the damage source's creature types and its controller as it dealt the damage
    source_subtypes: list[str] = Field(default_factory=list)
    source_controller: str | None = Field(default=None, max_length=64)
    source_commander: bool = False  # -- cast keywords (wave 43D) -- freerunning (702.173a): the damage source was a commander (903.3) as it dealt the damage
    # -- damage history (wave 6B) -- "damaged" facts (a permanent was dealt ``amount`` damage; ``object_id`` the
    # permanent): the object that dealt it
    source: str | None = Field(default=None, max_length=80)
    actor: str | None = Field(default=None, max_length=64)  # -- long tail (wave 16D) -- "counters" facts: the player who put them (122.6)
    # -- trigger other (wave 36A) -- "discard" facts: the event batch it happened in (0: not known / an older save), for "for the first time each turn" (603.2)
    batch: int = 0
    discarded_results: list[ObjectRef] | None = None  # Exact public discard results; [] hidden, None legacy.
    # -- trigger damage (wave 39B) -- "damaged" facts: the excess damage (120.10) the batch dealt to the permanent, on its first fact ("was dealt excess
    # damage this turn"); "damage" / "damaged" / "counters" facts also keep their event batch (0: an older save), for "for the first time each turn"
    excess: int = 0
    source_spell: bool = False  # -- trigger damage (wave 39B) -- "damaged" facts: the source was a spell on the stack as it dealt the damage (120.1)
# -- end this-turn history (wave 4D) --


class CompletedOwnTurn(BaseModel):
    turn: int
    attackers: list[str] = Field(default_factory=list)
    attacked_players: list[str] = Field(default_factory=list)
    acted110e: bool = False  # -- (wave 110E) -- cast a spell or put a nontoken permanent onto the battlefield that turn (Arboria); an older save: False


class TurnLog(BaseModel):
    """What happened during one turn that later text can ask about (608.2i): who attacked (508.1),
    life gained and lost (damage included, 120.3a), cards drawn, permanents that left the
    battlefield, cards that left a graveyard or went into one. Recorded deterministically from the
    steps applied to the table (``track`` / ``emit``) and the declaration of attackers, so replays,
    saves and undo reproduce it exactly. Only this turn's and the previous turn's logs are kept."""

    turn: int = 0
    combat_damage95_known: bool | None = None  # Complete native current-turn damage history; None is legacy.
    fight_history90_known: bool | None = None  # Legacy missing current-turn fight history is unknown.
    fought90: list[str] = Field(default_factory=list)  # Original objects that actually fought this turn.
    adapt_free110b: list[str] = Field(default_factory=list)  # Objects whose next adapt this turn ignores their +1/+1 counters (Biomancer's Familiar).
    required110b: list[str] = Field(default_factory=list)  # "<attacker object>|<combat number>" of attackers that had to attack (508.1d; Firkraag, Cunning Instigator).
    mirror110b: list[str] = Field(default_factory=list)  # Chosen creatures of Mystic Reflection waiting for "the next time one or more creatures or planeswalkers enter this turn".
    mirror_open110b: str = ""  # "<rules.batch>|<chosen id>": the effect being used by the entry event of that batch (previews of each card see the same one).
    mirror_late110b: list[str] = Field(default_factory=list)  # "card id|chosen id": used up, applied after the card's own "may enter as a copy" declined.
    lose_shield110b: list[str] = Field(default_factory=list)  # "pid|card id" of "the next time you would lose the game this turn, instead ..." (Stunning Reversal).
    turned_up_by110b: list[str] = Field(default_factory=list)  # Players who turned a permanent face up this turn (Oblivious Bookworm).
    turned_up110f: list[str] = Field(default_factory=list)  # Objects turned face up this turn (708.8: the same object, "was turned face up this turn").
    search_history75_known: bool | None = None  # Legacy missing authority is unknown until the next native turn.
    searched_own_library75: list[str] = Field(default_factory=list)  # Actual own-library searches begun this turn, even no card found.
    starting_life: dict[str, int] | None = None
    active_player: str | None = None  # Named turn, never inferred from seat order.
    attacked: list[str] = Field(default_factory=list)  # players who declared one or more attackers
    gained: dict[str, int] = Field(default_factory=dict)  # player -> life gained
    lost: dict[str, int] = Field(default_factory=dict)  # player -> life lost
    energy_lost: dict[str, int] = Field(default_factory=dict)  # CR 107.14: payments also remove energy
    drew: dict[str, int] = Field(default_factory=dict)  # player -> cards drawn
    # -- drawn this turn (wave 18G) -- player -> the rules objects (as they are in that player's hand) they drew, in order. PRIVATE:
    # which cards in a hand were drawn this turn is the owner's information (never in a view, a log line or a prompt others see)
    drawn: dict[str, list[str]] = Field(default_factory=dict)
    # -- replaced draws (wave 29C) -- the part of ``drawn`` a replacement effect drew ("draw two cards instead", "that many plus one"): 614.11b,
    # 121.6c — an additional action on drawn cards ("… and reveal them") isn't done to them. PRIVATE like ``drawn``
    drawn_replaced: dict[str, list[str]] = Field(default_factory=dict)
    # -- replaced draws (review 29C) -- the part of ``drawn`` drawn by an instruction a replacement effect changed the number of ("that many
    # cards plus one", 121.2a / 616.1g: Quantum Riddler, Alms Collector): whether "… and reveal them" reaches those isn't settled (614.11b
    # against 121.2a) — the players resolve it. PRIVATE like ``drawn``
    drawn_counted: dict[str, list[str]] = Field(default_factory=dict)
    # PRIVATE exact replacement ancestry of each actual hand object, for scoped CR 121.6c follow-up instructions.
    # Like drawn, this receipt is deliberately absent from all public/player view and history projections.
    drawn_applied: dict[str, list[str]] = Field(default_factory=dict)
    left: list[Departure] = Field(default_factory=list)
    left_graveyard: list[str] = Field(default_factory=list)  # the owner of each card that left a graveyard
    left_graveyard_creature110o: list[str] = Field(default_factory=list)  # -- (wave 110O) -- the owner of each creature card that left a graveyard
    entered_graveyard: list[Arrival] = Field(default_factory=list)
    entered: list[Entry] = Field(default_factory=list)  # -- refused modal/conditional (wave 3R1) -- onto the battlefield
    # -- this-turn history (wave 4D; app/rules/history.py) --
    casts: list[CastNote] = Field(default_factory=list)  # spells cast, as they became cast (601.2i)
    _cast_ids: set[str] | None = PrivateAttr(default=None)  # cached ids of permanents that were cast this turn; history.py resets it

    def cast_ids(self) -> set[str]:
        if self._cast_ids is None:
            self._cast_ids = {n.became for n in self.casts if n.became}
        return self._cast_ids
    facts: list[TurnFact] = Field(default_factory=list)  # tokens created, discards, sacrifices, damage to players …
    attackers: dict[str, list[str]] = Field(default_factory=dict)  # player -> creatures (objects) declared as attackers
    blockers: list[str] = Field(default_factory=list)  # -- combat state (wave 27A) -- creatures (objects) declared as blockers this turn (509.1g)
    block_ctrl110f: dict[str, str] = Field(default_factory=dict)  # -- wave 110F -- "blocker>attacker" objects -> the attacker's controller the last time it became blocked by that blocker (Glyph of Reincarnation)
    blocks: dict[str, list[str]] = Field(default_factory=dict)  # -- combat history (wave 31D) -- blocker (object) -> the attackers (objects) it blocked this turn
    attacked_at110c: dict[str, list[str]] = Field(default_factory=dict)  # -- wave 110C -- defending player (or a planeswalker's controller) -> players who attacked them this turn
    attacked_who: dict[str, list[str]] = Field(default_factory=dict)  # -- static_other sweep (wave 19A) -- attacker object -> players it attacked
    counters_removed110j: list[str] = Field(default_factory=list)  # -- (wave 110J) -- "<controller>:<kind>" per counter kind removed from a permanent this turn (122.1)
    gy_counters110j: list[str] = Field(default_factory=list)  # -- (wave 110J) -- counter kinds on permanents as they were put into a graveyard this turn (603.10a)
    attacked_battle110j: list[str] = Field(default_factory=list)  # -- (wave 110J) -- attacker objects declared against a battle this turn (310.5)
    attack_counts: dict[str, int] = Field(default_factory=dict)  # -- commander sweep (wave 49B) -- attacker object -> the combats it was declared an attacker in this turn (Moraug)
    # -- trailing & intervening ifs (wave 38A) -- 508.1, 500.8: attacker object -> the combat phase (RulesState.combats) it was last declared as an
    # attacker in ("~ attacked this combat"); attacker object -> the combat phase it enlisted a creature in (702.154a: "it enlisted a creature this combat")
    declared: dict[str, int] = Field(default_factory=dict)
    declared_blockers: dict[str, int] = Field(default_factory=dict)  # exact blocker object -> latest combat phase it blocked in
    enlisted: dict[str, int] = Field(default_factory=dict)
    # "<source object>:<ability index>" -> how many times that ability resolved this turn (copies included)
    resolved: dict[str, int] = Field(default_factory=dict)
    rolled: dict[str, int] = Field(default_factory=dict)  # -- dice (wave 24B) -- player -> dice rolled this turn (706.6: an ignored roll never happened)
    # -- end this-turn history (wave 4D) --


class HandLimitModifier(BaseModel):
    """A player rule modification carried by a native duration/timestamp record."""

    player: str
    kind: Literal["set", "delta", "none"]
    value: int = 0


class ColorWordEntry71(BaseModel):
    card: str
    acquisition: str | None = None
    word: Literal['white', 'blue', 'black', 'red', 'green'] | None
    provenance: Literal['native_entry', 'native_no_choice', 'manual_restore']
    chosen_by: str | None = None
    restored_by: str | None = None


class SpliceText71(BaseModel):
    name: str
    global_change: bool = False
    abilities: list[dict[str, Any]] = Field(default_factory=list)


class TextChange71(BaseModel):
    category: Literal['color', 'basic_land', 'creature']
    old: str
    new: str
    all_colors: bool = False


class ContinuousEffect(BaseModel):
    """A continuous effect from a resolved spell or ability (CR 611.2c): the objects it affects are
    fixed when it begins. See ``app.rules.layers``."""

    id: str
    affected: list[str] = Field(default_factory=list)  # rules object ids
    ability_zone: Literal['exile', 'graveyard'] | None = None  # Exact-object layer-6 ability grants explicitly functioning in exile.
    declaration_window: Literal["next_turn", "next_combat"] | None = None
    declaration_player: str | None = None  # fixed when a resolved requirement names its controller’s next phase/turn
    entry_counters: dict[str, int] = Field(default_factory=dict)  # Rule-modifying additional entry counters, including future entrants.
    entry_once110e: bool = False  # (wave 110E) used up by the first entry event it applies to (wave110e_once)
    hand_limit: HandLimitModifier | None = None  # 402.2/613.10: player rule, independent of card layers
    layer: Literal["1", "2", "3", "4", "5", "6", "7a", "7b", "7c", "7d"]
    source: str | None = None  # source object id
    controller: str
    set_name: str | None = None  # Noncopiable layer-3 name change (613.1c).
    text_change71: TextChange71 | None = None
    text_box110a: dict[str, dict[str, Any]] | None = None  # 612.5 (wave 110A): the rules text each affected object (by id) has instead of its own
    power: int | None = None
    toughness: int | None = None
    dyn_power110e: dict[str, Any] | None = None  # (wave 110E) layer 7b base power read now (611.3a): a values.evaluate amount, e.g. {'hand': 'you'}
    add_keywords: list[str] = Field(default_factory=list)
    remove_keywords: list[str] = Field(default_factory=list)
    blocked_keywords: dict[str, list[str]] = Field(default_factory=dict)  # prohibited grants at creation, per object
    add_types: list[str] = Field(default_factory=list)  # layer 4: "becomes an artifact creature"
    remove_types: list[str] = Field(default_factory=list)
    remove_subtypes: list[str] = Field(default_factory=list)
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
    # -- end of next turn (wave 32C) -- "end_of_next_turn": "until the end of your next turn" ends in the cleanup step (514.2) of
    # ``until_player``'s next turn (a later turn than ``turn``, even when it began in one of their own turns: delayed.end_of_next_turn)
    counter_since_batch: int = 0  # while-counter durations ignore earlier zero-counter events
    duration: Literal["end_of_turn", "permanent", "next_turn", "end_of_next_turn", "source_on_battlefield", "source_controlled",
                      "source_tapped", "source_controlled_tapped", "while_counter", "end_of_combat", "until_cast", "while_enchanted",
                      "next_upkeep", "monarch_player", "end_of_next_upkeep110g", "attached110n", "two_turns110f", "source_tapped_power110k", "while_attached110l", "creature_cast110m", "roll1_110f", "object_tapped110m", "next_end_step110d"] = "end_of_turn"  # (next_upkeep: wave 100A, "until your next upkeep" — delayed.at_step)
    created_step110d: int = 0  # -- (wave 110D) -- next_end_step110d: the step counter when it began (an end step already begun does not end it)
    until_object: str | None = None  # -- as long as (wave 37A) -- until_cast: the object (in exile) whose being cast ends the effect (delayed.spell_cast)
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
    remove_supertypes: list[str] = Field(default_factory=list)  # -- activated (wave 100I) -- "is no longer snow" (205.4; Arcum's Weathervane)
    set_creature_types: list[str] | None = None
    all_creature_types: bool = False
    # -- land types set (wave 12D) -- 305.7: "target land becomes an Island": its land types are replaced by these basic
    # land types, it loses the abilities of its rules text (and any copiable effects) and gains the types' mana abilities.
    set_land_types: list[str] | None = None
    set_artifact_types: list[str] | None = None  # replaces only artifact subtypes (205.1a)
    # Layer 5 (613.1e, 105.3): ``set_colors`` replaces its colors ([]: colorless) — None: unchanged;
    # ``add_colors``: "in addition to its other colors".
    set_colors: list[str] | None = None
    add_colors: list[str] = Field(default_factory=list)
    # Layer 6 (613.1f): "loses all abilities" (its printed abilities and everything granted before
    # this effect's timestamp; later grants apply again) and quoted abilities it gains (their text).
    remove_abilities: bool = False
    add_abilities: list[str] = Field(default_factory=list)
    activation_player: str | None = None  # None retains the normal controller permission (602.2).
    # -- licids (wave 50A) -- 613.1f: "loses this ability" (one printed ability, by its index); 116.2c: "You may pay {W} to end this effect" - the
    # special action's cost (``end_cost``, for ``controller``) ends every effect of the same resolution (``end_group``: the first one's timestamp)
    lose_index: list[int] = Field(default_factory=list)
    lose_quoted_ability: Literal["prevent_all_damage_to_self"] | None = None
    end_cost: str | None = None
    end_group: int = 0
    # -- copy system (wave 2F): layer 1a (613.2a) — a copy effect: the affected objects' copiable
    # values become this recipe's (707.2-707.5); the latest (by timestamp) applies (613.7)
    copy_recipe: CopyRecipe | None = None
    copy_entry_source: CopyEntrySource | None = None
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


class CounterPlacement(BaseModel):
    """One committed positive placement, retained independently of later board state."""

    destination: ObjectRef
    kind: str
    amount: int


class ResolvedManaColorReplacement(BaseModel):
    """One resolved white-to-colorless effect on an exact permanent, indefinitely."""

    id: str
    target: ObjectRef
    op: Literal['white_to_colorless'] = 'white_to_colorless'
    source_object: str | None = None


class PhaseLifetime(BaseModel):
    """Direct phasing recipients held until one original source actually leaves (610.3)."""

    source: ObjectRef
    recipients: list[ObjectRef] = Field(default_factory=list)
    tap_on_return: bool = False  # Oubliette: tapped as it phases in
    control: str | None = None  # -- wave 110D -- "for as long as you control this Saga": the player who must control the source
    while_tapped: bool = False  # -- wave 110I -- The Pandorica: held only while the source remains tapped
    roll_max110f: int | None = None  # -- wave 110F -- Ferris Wheel: held until ``roller110f`` rolls this or less while rolling to visit (the source does not matter)
    roller110f: str | None = None


class PhaseHold110K(BaseModel):
    """-- wave 110K -- Teferi, Timeless Voyager: these objects can't phase in until the cleanup step of ``player``'s next turn (a later turn than ``turn``)."""

    objects: list[str] = Field(default_factory=list)
    player: str
    turn: int


class CostReveal(BaseModel):
    object: ObjectRef
    prior: list[str] = Field(default_factory=list)


class ActivationCostFacts(BaseModel):
    """The cost of one actual nonmana activation, frozen before its trigger resolves."""

    mana: dict[str, int] | None = None
    life: int | None = None
    sacrificed: int = 0
    has_x: bool = False


class TriggerEvent(BaseModel):
    """What a triggered ability triggered on (603.2), captured as it triggered and carried with it
    to the stack and through resolution (603.3, 608.2k): the resolving ability reads this, never the
    board as it is later. One event for a "one or more" trigger holds every object of the batch
    (603.2c)."""

    actor: str | None = Field(default=None, max_length=64)  # Actual event actor/source controller, frozen before later changes.
    dice_total: int | None = None  # Immutable sum of the triggering retained die results.
    attacking_player: str | None = None  # Frozen combat damage actor, independent of source controller.
    turn_start_life: int | None = None
    activation_cost: ActivationCostFacts | None = None
    mana_spent: dict[str,int] | None = None  # Actual cast payment, retained when its spell leaves before a trigger resolves.
    kind: str = Field(max_length=40)  # the condition's event: "die", "draw", "gain_life", …
    batch: int = 0
    objects: list[ObjectRef] = Field(default_factory=list)  # the object(s) the event happened to
    counter_placements: list[CounterPlacement] = Field(default_factory=list)
    cast_targets: list[ObjectRef] = Field(default_factory=list)  # exact card targets as a spell was cast; optional for old saves
    # For a zone change: the object each became where it went (400.7e: a "dies" ability can find
    # it in the graveyard, and only there)
    new_objects: list[ObjectRef] = Field(default_factory=list)
    players: list[str] = Field(default_factory=list)  # the player it was about (who drew / gained / was dealt damage)
    source: ObjectRef | None = None  # the source of damage dealt
    amount: int = 0  # life gained or lost, damage dealt (summed over a "one or more" batch)
    count: int = 0  # how many objects / events the batch had
    sacrificed: bool | None = None  # one departure event: was this object sacrificed (701.21)?
    attacked_players: list[str] = Field(default_factory=list)  # Direct players attacked by this declaration (508.1); frozen for resolution.
    defended: str | None = None  # -- combat (wave 5C) -- "Whenever you attack a player": the player attacked (508.3e)
    # -- damage wordings (wave 6B) -- "Whenever ~ blocks or becomes blocked by a creature, …": that creature (509.3c-d)
    other: ObjectRef | None = None
    # -- X from the triggering object (wave 34C) -- 107.3a: the X a cycling cost was announced with ("When you cycle this card, create an X/X
    # …"); None for any other event (a cast trigger reads its spell's payment record: triggers.cast_x)
    x: int | None = None
    # -- trigger multipliers (wave 43A) -- 120.2: damage events: whether the damage was combat damage (None: not a damage event / not recorded); read by the
    # "dealing combat damage to a player" multiplier (trigger_multipliers.py)
    combat: bool | None = None
    # -- attacked object (wave 45A) -- 508.5: the planeswalker or battle an attacking creature's event is about, as it triggered ("deals 1 damage to the player or
    # planeswalker it's attacking"); None when it attacks a player (``defended``)
    attacked: ObjectRef | None = None
    # -- voting (wave 48D) -- 701.38: "Whenever players finish voting": the [voter, choice] of every vote of the voting that finished, as cast
    ballots: list[list[str]] = Field(default_factory=list)
    sticker: str | None = None  # -- cards (wave 110I) -- the kind of a placed sticker ("art", "name", …): Wee Champion's "if it's an art sticker"
    combat_alone110g: str | None = None  # -- wave 110G -- a permanent that left: "attacking" / "blocking" when it was the only creature doing so (506.5), else None


class RegenerationShield(BaseModel):
    """One distinguishable CR 614.8 shield and its creating effect's bindings."""

    id: str
    object_id: str
    controller: str
    source_card: str
    source_object: str
    name: str
    effects: list[dict[str, Any]] = Field(default_factory=list)
    refs: dict[str, Any] = Field(default_factory=dict)
    immediate: bool = False


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


class DeferredPaymentWindow(BaseModel):
    """116.2c: one early-payment special action suppresses its exact delayed trigger."""

    id: str
    payer: str
    cost: str
    delayed: str
    name: str
    source_card: str | None = None


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
    created_step: int | None = None  # Saved chronological step; phase names can repeat in one turn.
    once: bool = True  # 603.7b: it triggers only once (an "each" duration would say otherwise)
    until_turn: int | None = None  # "this turn": it stops watching at that turn's cleanup (514.2)
    until_end_next_player: str | None = None  # Through the cleanup of this player's next actual turn.
    until_combat: bool = False  # -- block events (wave 53C) -- "this combat": it stops watching as the combat phase ends (combat.end_combat)
    until_player: str | None = None  # -- turn-long triggers (wave 50G) -- "until your next turn": it stops watching as that player's next turn begins (500.4)
    # -- if you do (wave 25C) -- a turn watch's deferred ability that has a target of its own ("Whenever you cast a spell this turn, put a +1/+1
    # counter on target creature you control"): the selector its controller chooses a target for each time it triggers (603.3d)
    target: dict[str, Any] | None = None
    targets: list[dict[str, Any]] | None = None  # Multiple groups chosen only when this delayed ability triggers.


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
    x_from_event_spell: bool = False  # CR107.3: an exact cast spell's current/LKI X, not the amount paid.
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
    kicked_mask: int = 0  # -- keywords (wave 50H) -- 702.33f: of two kicker costs, which were paid (1: the first, 2: the second)
    # A triggered ability: what it triggered on (603.2), for "it", "that player", "that much"
    event: TriggerEvent | None = None
    # -- copy system (wave 2F): a copy of a spell or ability (707.10): the object id of what it
    # copies. A copy isn't cast (or activated); its cost-paying objects are the original's.
    copy_of: str | None = None
    chooser110i: str | None = None  # -- cards (wave 110I) -- 608.2b: a target chosen by this player (Necrotic Plague) must still be a creature they don't control


class StackMemory(BaseModel):
    """-- spell copies (wave 31D) -- a spell as it last existed on the stack (608.2h): what a copy of it needs once it has left (countered, returned
    to its owner's hand …). "Copy it" in a cast trigger copies the spell even if it is gone by then (707.10, the Storm cycle / Krark rulings)."""

    card: str = Field(max_length=64)
    turn: int = 0
    entry: StackEntry | None = None  # Permanent spells resolve without a scripted entry.
    info: dict[str, Any] = Field(default_factory=dict)  # its StackInfo (X, modes, tags: Kicked, Evoked …)
    evoked: bool = False
    dashed: bool = False
    ability_card: dict[str, Any] | None = None  # A ceased ability retains its copiable stack values (608.2h).
    aura_target102: TargetRef | None = None  # Original Aura-spell target, including after the spell leaves.


class CostContribution(BaseModel):
    """One mana symbol of a spell's total cost paid by something that isn't mana (CR 702.51a
    convoke, 702.126a improvise, 702.66a delve): which object, and which symbol it paid."""

    kind: Literal["convoke", "improvise", "delve", "waterbend"]
    card: str = Field(max_length=64)
    object_id: str = Field(default="", max_length=80)  # the object as it was when used
    name: str = Field(default="", max_length=200)
    pays: str = Field(max_length=8)  # "1" (one generic), "G", "W/U", "2/G", "G/P"
    card_types: list[str] | None = None  # Characteristics of the paid object; None in legacy saves.
    exiled_object_id: str | None = None  # Exact new exile incarnation for delve; absent in legacy saves.
    keywords: list[str] | None = None  # -- (wave 110N) -- the exiled card's keywords as it was exiled (Soulflayer); None in older saves


class MadnessFollowup(BaseModel):
    """702.35c: a discarded exile object declined into a public zone."""

    original: ObjectRef
    result: ObjectRef | None = None
    pending: bool = True


class PaidCardFact(BaseModel):
    """A directly paid card in its specified result zone, retained after departure."""

    card: str = Field(max_length=64)
    object_id: str = Field(max_length=80)
    zone: str = Field(max_length=100)
    mana_value: float = Field(ge=0)
    mana_cost: str | None = None  # Unknown in older receipts; printed symbols of this exact paid object.
    colors: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    subtypes: list[str] = Field(default_factory=list)


class NotedMana(BaseModel):
    """Linked information actually noted by a resolving activation (607.2e)."""

    mana: dict[str, int] | None = None  # None: old unknown receipt; {}: actual zero payment.
    last_exiled: list[ObjectRef] | None = None  # Last actual packet; None: unknown old history.


class OpponentGainCostReceipt(BaseModel):
    recipient: str = Field(max_length=64)
    nominal_amount: int = Field(ge=0)


class NumericRollCostReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal[1] = 1
    source_object: str
    ability_object: str
    roller: str
    results: list[int] = Field(min_length=1, max_length=1)

    @property
    def result(self) -> int:
        return self.results[0]


class PaymentRecord(BaseModel):
    """How a spell's total cost was paid (601.2f-h), kept for "mana spent to cast it", "if its
    kicker/alternative cost was paid", "the creatures that convoked it" … Contributions are NOT
    mana spent (702.51a: "rather than pay that mana")."""

    card: str = Field(max_length=64)
    controller: str = Field(max_length=64)
    total_cost: str = ""  # Exact locked-in cost, including repeated additional colored costs.
    resolved_x: int | None = None  # Actual permanent spell X at resolution; paid/announced x stays separate.
    cast_greatest_power: int | None = None  # Server-captured as-cast value; unknown in old payment records.
    activation_cost_has_x: bool | None = None  # Original activation cost before reductions/X substitution.
    activation_cost_has_tap: bool | None = None  # Actual selected activation cost includes literal {T}; None is legacy unknown.
    activation_life_paid: int | None = Field(default=None, ge=0)  # Direct activation costs, excluding mana sources.
    x_black_spent: int | None = Field(default=None, ge=0)  # Actual black mana assigned to X; None for old saves.
    mana_spent: dict[str, int] = Field(default_factory=dict)  # actual mana, by type (W U B R G C)
    # -- mana provenance (wave 18B) -- 106.3/107.4h: what each mana spent came from (the source's supertypes, types and subtypes; mana
    # from the plain pool has no entry) and the riders it carried ("when that mana is spent ...", 106.6): app/rules/mana_units.py
    mana_tags: list[list[str]] = Field(default_factory=list)
    snow_spent: dict[str, int] | None = None  # Actual snow-source mana by type; None in older saves.
    mana_sources: list[str] = Field(default_factory=list)  # source object per mana actually spent (106.3)
    mana_riders: list[dict[str, Any]] = Field(default_factory=list)
    contributions: list[CostContribution] = Field(default_factory=list)
    life: int = 0  # life paid (Phyrexian mana, …)
    opponent_gain_costs: list[OpponentGainCostReceipt] = Field(default_factory=list)
    phyrexian: int = 0  # -- cast keywords (wave 43D) -- the Phyrexian mana symbols of its cost paid with life (2 life each): compleated, 702.150a
    tapped: list[str] = Field(default_factory=list)  # permanents tapped for mana while paying (engine-paid)
    sacrificed: list[str] = Field(default_factory=list)
    sacrificed_objects: list[str] = Field(default_factory=list)  # (wave 3D) the object ids they were: last known information
    sacrificed_now110h: list[str] = Field(default_factory=list)  # (wave 110H) the graveyard objects they became (400.7): "exile those cards" finds exactly these
    discarded: list[str] = Field(default_factory=list)
    discarded_objects: list[str] = Field(default_factory=list)  # Exact objects the discard cost produced (400.7).
    discarded_mana_values: dict[str, int] = Field(default_factory=dict)  # Last known values if those exact discarded objects leave.
    discarded_facts: list[PaidCardFact] | None = None  # None in older receipts; [] records a genuine zero-card payment.
    revealed_facts: list[PaidCardFact] | None = None
    exiled_facts: list[PaidCardFact] | None = None
    milled_facts: list[PaidCardFact] | None = None
    cast_controlled_subtypes: list[str] = Field(default_factory=list)  # Permanent subtype snapshot as casting finishes.
    cast_controlled_modified: bool = False  # -- xdamage (wave 100E) -- a modified creature (700.9) controlled as casting finished (Flame Discharge)
    cast_modified_n110e: int = 0  # -- wave 110E -- how many modified creatures (700.9) the caster controlled as casting finished (Lethal Exploit)
    cast_revealed_subtypes: list[str] = Field(default_factory=list)  # Subtypes of cards revealed for this spell's cost.
    revealed: list[str] = Field(default_factory=list)  # -- static_other sweep (wave 17C) -- cards revealed from the hand to pay ("the revealed card's …")
    unattached_ninja110j: bool = False  # -- wave 110J -- an Equipment the cost unattached was attached to a Ninja (Shuriken)
    beheld110a: dict[str, str] = Field(default_factory=dict)  # -- behold (wave 110A) -- card id -> object id of what the cost beheld (701.4a)
    exiled: list[str] = Field(default_factory=list)  # cards exiled to pay (from a graveyard, or the source)
    exiled_objects: list[str] = Field(default_factory=list)  # -- as long as (wave 37A) -- the objects they became in exile (400.7j: "this card" finds that one)
    exiled_was: list[str] = Field(default_factory=list)  # (wave 48B: and the objects they were, "the number of cards exiled this way" of an activation cost)
    splice_text71: SpliceText71 | None = None
    spliced_names: list[str] | None = None  # Public names spliced onto this spell; None is unknown in legacy saves.
    moved_exile_names: list[str] | None = None  # Public names of cards put from linked exile to a graveyard to pay.
    returned: list[str] = Field(default_factory=list)  # permanents returned to hand to pay
    returned_objects: list[str] | None = None  # Original battlefield incarnations paid directly; None in legacy saves.
    # -- keywords (wave 15E) -- ninjutsu 702.49c: what each returned attacking creature was attacking (player or permanent id)
    returned_attacking: dict[str, str] = Field(default_factory=dict)
    tapped_for_cost: list[str] = Field(default_factory=list)  # "Tap an untapped creature you control" (not for mana)
    tapped_objects: list[str] = Field(default_factory=list)  # (review 26C) the object ids they were: "the creature tapped this way" (608.2h)
    kicked: int = 0  # 702.33d: times its kicker cost was paid
    kicked_mask: int = 0  # -- keywords (wave 50H) -- 702.33f: of two kicker costs, which were paid (1: the first, 2: the second)
    pick110e: str | None = Field(default=None, max_length=64)  # -- cast-time choice (wave 110E) -- the creature type chosen as the spell was cast
    gift_to: str | None = Field(default=None, max_length=64)  # -- gift (wave 23D) -- 702.174a: the opponent the gift was promised to
    alternative: str | None = None  # "evoke", "dash", "flashback", "madness", "face_down", "free", …
    granted_offspring110a: bool = False  # -- grants (wave 110A) -- Zinnia: offspring was given to the spell as it was cast (the permanent keeps it)
    prototyped: bool = False  # -- casting extras (wave 18E) -- 718.3: cast prototyped (the spell and the permanent have the alternative values)
    additional: list[str] = Field(default_factory=list)  # "buyback", "kicker", …
    waterbend_paid102: bool | None = None  # Actual paid action; None is unknown legacy data, copied independently of mana spent.
    x: int | None = None
    numeric_roll_cost: NumericRollCostReceipt | None = None
    # -- refused modal/conditional (wave 3R1) -- how the spell was cast, for "if you cast it [from your hand]",
    # "if this spell was cast from a graveyard" and addendum ("if you cast this spell during your main phase"):
    # the zone it was cast from (None: not cast — a copy, 707.10 — or an ability's record, or an older save);
    # whether it was cast during its caster's own main phase; ``mana_known`` False for a card moved onto the
    # stack by hand (cast by hand: what paid for it is unknown, so no "mana was spent" condition can hold)
    cast_from: str | None = Field(default=None, max_length=20)
    cast_from_player: str | None = Field(default=None, max_length=64)  # Physical owner of the origin zone, immutable across spell-control changes.
    cast_main: bool = False
    mana_known: bool = True
    flash_sac: bool = False  # -- flash auras (wave 46B) -- cast with its own "as though it had flash" when a sorcery couldn't have been cast: sacrificed at the next cleanup step


class PermissionUseTrigger(BaseModel):
    """Original source of a trigger attached to one selected casting/play authority."""

    kind: Literal["replenish_top", "owner_loses_mv", "create_food69", "native"]
    definition: dict[str, Any] | None = None
    source: ObjectRef
    controller: str
    name: str
    index: int


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
    zone_owner: Literal["you", "any"] = "you"  # A broad graveyard permission may include other players' cards.
    hand_of110m: str | None = None  # (wave 110M) zone "hand": the cards of THIS player's hand (Sen Triplets: "from that player's hand"), not the holder's own
    # A specific object ("you may play that card this turn"): the permission follows the object,
    # not the card (400.7h/i): once it changes zones it is a new object and the permission is spent
    object_id: str | None = None
    card: str | None = None
    library_of: str | None = None  # (wave 110C) zone library_top of this player's library instead of the holder's (Xanathar)
    look_top: bool = False  # Source-independent private top look for this stored library-top authority.
    top110j: bool = False  # -- wave 110J -- Temporal Aperture: only while ``card`` stays on top of its library, which is then revealed to everyone (401.5)
    stop_on_linked_exile: str | None = None  # Source-object/link scope: expires when this permission holder next exiles a card with it.
    filter: str | None = None  # a selector key the spell must match ("creature spells")
    card_filter: str | None = None  # Current card eligibility, applied to both land plays and spell casts.
    free: bool = False  # "without paying its mana cost": an alternative cost of {0} (118.9)
    life_mv: bool = False  # Required alternative cost: pay life equal to the chosen spell's mana value.
    use_trigger: PermissionUseTrigger | None = None
    spell_keywords: list[Literal['affinity for artifacts', 'undaunted']] = Field(default_factory=list)
    flash: bool = False  # "as though it had flash" (601.3b)
    once: bool = False  # "once during each of your turns"
    used_turn: int = 0  # (once) the turn it was used
    # (-- durations (wave 30M) -- "next_turn": "Until your next turn, you may …" ends as that player's next turn begins (500.4, delayed.turn_began);
    # "source_controlled" / "source_on_battlefield": "for as long as you control ~ / ~ remains on the battlefield" ends the moment that stops
    # being true, 611.2b (delayed.expire), the granting object being ``source``)
    until: Literal["end_of_turn", "end_of_next_turn", "next_end_step", "permanent", "next_turn", "source_controlled",
                   "source_on_battlefield", "next_upkeep", "next_combat_end"] = "end_of_turn"
    until_player: str | None = None  # Duration's player when distinct from the permission's beneficiary.
    granted_step: int | None = None
    turn: int = 0  # the turn it was granted (for end_of_next_turn, next_turn)
    source: str | None = None  # the granting object
    label: str = Field(default="", max_length=120)
    # -- as long as (wave 9B) -- "mana of any type can be spent to cast that spell" ("type") / "you may spend mana as though it
    # were mana of any color to cast it" ("color"): applies only to mana spent casting with this permission (118.14, 609.4b)
    spend: Literal["", "type", "color", "colorless_color"] = ""
    # -- keywords (wave 15E) -- warp 702.185a ("after the current turn has ended": not before turn ``after_turn`` is over) and plot
    # 702.170d ("during your main phase while the stack is empty", ``sorcery``, even for an instant)
    after_turn: int = 0
    # -- if you do (wave 25C) -- 614.1a: "If that spell would be put into a graveyard, exile it instead." for the spell cast with this
    # permission ("is": instants and sorceries only); ``exile_own``: "your graveyard" (a card another player owns goes to theirs)
    exile_gy: Literal["", "all", "is"] = ""
    exile_own: bool = False
    graveyard_destination: Literal["", "library_bottom"] = ""
    sorcery: bool = False
    enters: dict[str, Any] | None = None  # -- if you do (wave 51D) -- "You may play target … card from your graveyard this turn. If you do, it enters tapped." (the Grant's ``enters``, 614.1c)
    # -- trigger other (wave 25B) -- airbend 701.65a: the card may be cast only by paying this rather than its mana cost (an alternative
    # cost, 118.9), for as long as it remains exiled (the permission follows the object, 400.7h)
    alt_mana: str = ""
    generic_extra: int = 0  # Generic mana increase for casting with this permission.
    generic_less: int = 0  # (wave 110G) generic mana reduction for casting with it (Urianger Augurelt)
    extra: str = ""  # Mandatory additional nonmana cost of this permission.
    # -- cost reductions paid with objects (wave 47C) -- "You may play up to two of those cards": the permissions of one instruction share ``group``, and ``left`` more
    # of them may be used (consume ends the others when the last is)
    group: str = ""
    left: int = 0
    # -- trigger other (wave 51E) -- "During any turn you attacked with a token, you may play that card.": a condition (conditions grammar) the turn must meet, read
    # whenever the card is played or cast; ``source`` is the object whose ability granted it
    when: dict[str, Any] | None = None
    # -- chosen filters (wave 53B) -- "The next spell of the chosen type you cast this turn can be cast as though it had flash.": the spells of ``filter`` cast this turn when it was granted;
    # it applies only while no more have been cast (the next one uses it up, 601.2i)
    nth: int | None = None


class CostModifier(BaseModel):
    """A cost increase or reduction that applies to spells as their total cost is determined
    (601.2f): generic mana only (118.7a), never below {0}. Static ones ("Creature spells you cast
    cost {1} less to cast.") are read from the table; effects with a duration are stored here."""

    id: str
    controller: str  # whose "you" (the source's controller)
    delta: int  # +N: costs {N} more; −N: costs {N} less
    caster: Literal["you", "opponent", "any"] = "you"
    from_zones: list[str] = Field(default_factory=list)  # Original announcement zones; [] preserves older unrestricted effects.
    filter: str | None = None  # a selector key the spell must match, or None for every spell
    # "permanent" (a static, read from the table), "end_of_turn" ("… you cast this turn cost …": ends in
    # cleanup, 514.2) or "next_turn" ("Until your next turn, …": ends as its controller's next turn begins)
    until: Literal["end_of_turn", "permanent", "next_turn"] = "end_of_turn"
    card_id: str | None = None  # (wave 110M) applies only to this one spell card (Kefnet: "that copy costs {2} less to cast")
    until_player: str | None = None  # Captured duration owner when different from the beneficiary.
    turn: int = 0  # the turn it was created
    source: str | None = None
    label: str = Field(default="", max_length=120)
    mana: str = Field(default="", max_length=8)  # -- cost changers (wave 4I) -- a colored change ("{W} more"): its color (wave 46A: several, "!" first: only colored)


class NextSpellGrant(BaseModel):
    """-- spell grants (wave 28C) -- "The next spell you cast this turn has improvise." / "The next noncreature spell you cast this turn has
    cascade.": a keyword the next spell its caster casts this turn (that matches ``filter``) has as it is cast (601.2, 702.51, 702.126,
    702.85), used up by that cast and ended in cleanup (514.2). One grant per instance (two grants of cascade: two cascades, 702.85c)."""

    id: str
    player: str
    keyword: str  # "convoke" | "improvise" | "affinity" | "cascade" | "storm"
    what: str = ""  # affinity: "artifacts"
    filter: str | None = None  # a spell selector key ("noncreature"), or None: the next spell, whatever it is
    turn: int = 0
    source: str | None = None
    label: str = Field(default="", max_length=120)
    amount: int = 0  # -- cant restrictions (wave 46A) -- keyword "cost": the generic mana it takes off ("The next spell you cast this turn costs {1} less to cast.", 601.2f, 118.7a)


class SourceHandReveal79(BaseModel):
    """A resolved reveal fixes its player and original source object for its duration."""

    player: str
    source_card: str
    source_object: str


class TopReveal(BaseModel):
    """"Play with the top card of your library revealed." / "You may look at the top card of your
    library any time." — while ``source`` is on the battlefield under ``player``'s control, that
    player's top library card is visible to everyone or to its owner (401.5). Refreshed by the
    engine from the table; ``app.game.visibility`` checks the source is still there."""

    source: str  # the permanent's card id
    player: str
    to: Literal["all", "owner", "none"]  # (-- hidden exile (wave 18A) -- "none": only the face-down looking below)
    face_down: bool = False  # 708.5 exception: ``player`` may also look at the face-down creatures others control
    # -- revealed zones (wave 25A) -- "Players play with the top card of their libraries revealed." (``whose`` "players"), "Your opponents play with
    # their hands revealed." / "Players play with their hands revealed." / "Play with your hand revealed." (``zone`` "hand": shown to every player, 701.20a)
    zone: Literal["library", "hand"] = "library"
    whose: Literal["you", "opponents", "players"] = "you"


class HideawayLook(BaseModel):
    """-- hideaway (wave 29D) -- 702.75a / 406.3: the face-down exiled card (its object id is the key in ``RulesState.hideaway``) that the
    controller of the permanent that exiled it (``source``, an object id) may look at, and the players who have been allowed to look and
    may go on looking until it leaves exile (``lookers``). App/rules/hideaway.py."""

    source: str
    lookers: list[str] = Field(default_factory=list)


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


class DeclarationCostReservation(BaseModel):
    payer: str
    objects: dict[str, str] = Field(default_factory=dict)


class UntapOperation(BaseModel):
    """A nontriggered operation during a fixed player's next actual untap step."""
    card: str = Field(max_length=64)
    object_id: str = Field(max_length=80)
    player: str = Field(max_length=64)
    kind: Literal['return_hand'] = 'return_hand'


class CombatHistoryNotice(BaseModel):
    """Missing historical trigger qualification; explicit manual handling this turn."""

    source_object: str = Field(max_length=80)
    ability: int
    controller: str = Field(max_length=64)
    turn: int
    name: str = Field(default='', max_length=500)
    notified: bool = False


class FirstEventHistoryNotice78(CombatHistoryNotice):
    """An unresolved first-action qualification from a legacy midturn save."""


class CombatReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')

    player: str
    turn: int = Field(ge=1)
    combat: int = Field(ge=1)
    players_attacked: dict[str, list[str]] = Field(default_factory=dict)


class CombatMemory(BaseModel):
    model_config = ConfigDict(extra='forbid')

    version: Literal[1] = 1
    known_empty: list[str] = Field(default_factory=list)
    previous: dict[str, CombatReceipt] = Field(default_factory=dict)
    current: CombatReceipt | None = None


class ChosenColorPairReceipt(BaseModel):
    """Colors chosen by one native linked ability acquisition as its object entered."""

    card: str
    colors: tuple[str, str]
    acquisition: str | None = None

    @model_validator(mode='after')
    def distinct_colors(self) -> ChosenColorPairReceipt:
        if len(set(self.colors)) != 2 or not set(self.colors) <= set('WUBRG'):
            raise ValueError('Choose two distinct colors')
        return self


class WorldInterval80(BaseModel):
    """An uninterrupted native World interval, or explicitly unknown legacy history."""

    card: str
    since: int | None = None
    observed_before: int
    event_batch: int | None = None


class RulesState(BaseModel):
    pin_collection110i: bool = False  # (wave 110I) a Pin Collection has had a sticker put on it: stickers101.continuous then looks for equipped creatures
    began_untapped110j: list[str] = Field(default_factory=list)  # (wave 110J) objects untapped on the battlefield as the turn began (Rasputin Dreamweaver)
    hand_reveal_turn110m: dict[str, int] = Field(default_factory=dict)  # (wave 110M) player -> the turn through which they play with their hand revealed
    reveal_ask110m: list[list[str]] = Field(default_factory=list)  # (wave 110M) [player, card, object] first draws of a turn whose "you may reveal" is still to be asked
    turn_reversed110m: bool = False  # (wave 110M) Aeon Engine: the turn order runs against the seat order
    coffin_counters110m: dict[str, dict[str, int]] = Field(default_factory=dict)  # (wave 110M) Tawnos's Coffin: exiled creature rules object -> the counters noted on it
    alaundo110m: list[str] = Field(default_factory=list)  # (wave 110M) rules objects of exiled cards carrying Alaundo's granted "last time counter" trigger
    eot_haste110m: list[str] = Field(default_factory=list)  # (wave 110M) creature spells cast from exile that gain haste until end of turn as they enter
    bat_links110m: dict[str, str] = Field(default_factory=dict)  # (wave 110M) Timothar: a Bat token's rules object -> the exiled card's rules object it returns
    stack_seen110m: list[str] = Field(default_factory=list)  # (wave 110M) stack objects already looked at for "whenever a spell or ability is put onto the stack"
    stored_dice110m: dict[str, list[int]] = Field(default_factory=dict)  # (wave 110M) object id -> the d6 results stored on it (706.8a: Centaur of Attention)
    tap_paid110n: list[list[str]] = Field(default_factory=list)  # (wave 110N) [turn, ability source object, creature tapped for its cost] this turn (Vodalian War Machine)
    began_lands110c: dict[str, int] = Field(default_factory=dict)  # (wave 110C) player -> untapped lands they controlled as their turn began (Power Surge)
    sticker_splits101: dict[str, str] = Field(default_factory=dict)  # Original permanent OID -> chosen physical component.

    world_epoch80: int = 0
    world_intervals80: dict[str, WorldInterval80] = Field(default_factory=dict)
    combat_memory: CombatMemory | None = None  # None: unknown legacy previous combat.
    untap_operations: list[UntapOperation] = Field(default_factory=list)
    paused: bool = False  # the host paused automation: intents are refused, the sandbox works
    declaration_cost_reserved: DeclarationCostReservation | None = None
    step: str = ""  # "<turn>:<phase>" the engine last acted in; a mismatch means a manual step change
    priority: str | None = None  # player who may act
    passed: list[str] = Field(default_factory=list)  # players who passed in succession
    # -- core review -- the player the engine passes for once, Arena-style, right after they cast a spell or activated an
    # ability: consumed by engine.advance once the triggers that cast caused are on the stack (117.3c, 603.3)
    auto_pass: str | None = None
    decision: Decision | None = None
    # -- nested payment choices (wave 28D) -- 605.3a: the "tap your mana" / pay-or-sacrifice prompt a mana ability's own chosen cost
    # (Ashnod's Altar's creature, Phyrexian Altar's color) is nested in; it comes back once that choice is made or cancelled
    payment_outer: Decision | None = None
    prefs: dict[str, PlayerPrefs] = Field(default_factory=dict)  # per-player automation preferences
    # Per-card automation override (right-click → Automation): "manual" cards are never automated;
    # the engine asks their controller to resolve them by hand and doesn't enforce their timing.
    card_modes: dict[str, Literal["manual", "assisted"]] = Field(default_factory=dict)
    lands_played: dict[str, TurnCount] = Field(default_factory=dict)
    extra_land_plays: dict[str, TurnCount] = Field(default_factory=dict)  # -- wave 8A -- "You may play an additional land this turn."
    spells_cast: dict[str, TurnCount] = Field(default_factory=dict)
    mana_cast: dict[str, TurnCount] = Field(default_factory=dict)  # -- wave 15B -- mana spent to cast spells this turn (700.14 expend)
    loyalty_used: dict[str, int] = Field(default_factory=dict)  # planeswalker -> turn it last used a loyalty ability
    dealt_to110g: dict[str, list[str]] = Field(default_factory=dict)  # -- wave 110G -- source object id -> players / objects it dealt damage to this game (The Fallen)
    monarch_began110b: str | None = None  # -- wave 110B -- the monarch as the current turn began (Knights of the Black Rose)
    loyalty_extra110a: dict[str, list[int]] = Field(default_factory=dict)  # -- wave 110A -- Comet: planeswalker object -> [turn, activations still allowed beyond the first] (606.3)
    loyalty_second: dict[str, int] = Field(default_factory=dict)  # -- static_other sweep (wave 19A) -- planeswalker -> turn of its second use
    # -- activation costs (wave 4H) -- exerted permanents (701.43a): object id -> the player who exerted it; it doesn't
    # untap during that player's next untap step (app/rules/engine.start_next_turn)
    exerted: dict[str, str] = Field(default_factory=dict)
    exerted_turn: dict[str, int] = Field(default_factory=dict)  # -- most-played cards (wave 43B) -- object id -> the turn it was last exerted ("hasn't been exerted this turn", Combat Celebrant)
    # -- next untap step (wave 6A) -- "doesn't untap during its controller's / your next untap step" (502.3;
    # app/rules/next_untap.py): {"oid": object id, "player": a player id, or "controller" (read at the untap step)}
    stay_tapped: list[dict[str, str]] = Field(default_factory=list)
    once_per_turn: dict[str, int] = Field(default_factory=dict)  # "<card>:<ability>" -> turn it was activated
    # Activation restrictions and trigger limits (app/rules/restrictions.py): how many times an
    # object's ability was activated / triggered — "<object id>:<ability index>:t<turn>" -> count this
    # turn, "<object id>:<ability index>:game" -> count this game (602.5b, 400.7: per object).
    ability_uses: dict[str, int] = Field(default_factory=dict)
    # -- soulbond (wave 24B) -- 702.95b: paired creatures, both directions: object id -> (partner's object id, the pairing's controller)
    pairs: dict[str, tuple[str, str]] = Field(default_factory=dict)
    dread_gy110c: list[str] = Field(default_factory=list)  # -- manifest dread (wave 110C) -- 701.62a: the card each finished manifest dread put into the graveyard ("" none), read by its "Whenever you manifest dread" triggers
    # -- modal triggered/activated abilities (wave 1A) --
    # "Choose one that hasn't been chosen [this turn]": the modes already chosen for that ability of
    # that object (app/rules/modal_abilities.py) — "<object id>:<ability index>:game" (the game) or
    # "<object id>:<ability index>:t<turn>" (that turn) -> mode numbers. Kept per object (400.7: a new
    # object has no memory) and not per controller; a mode counts once it was chosen, whether or not
    # the ability resolved.
    modes_chosen: dict[str, list[int]] = Field(default_factory=dict)
    coin_flipped: dict[str, int] = Field(default_factory=dict)  # Last actual coin turn, including ignored physical flips.
    coin_history_from_turn: int | None = None  # None in legacy saves; no absence is invented.
    graveyard_history_from_turn: int | None = None  # Complete physical-card arrival history; None is legacy unknown.
    turn_seen: int = 0  # last turn number the bookkeeping saw
    target_activation_history_turn: int | None = None  # Unknown on legacy midturn saves; complete after a native turn boundary.
    crew_saddle_history_turn80: int | None = None  # Independent versioned history for resolved crew/saddle events.
    first_event_history_turn78: int | None = None
    first_event_notices78: list[FirstEventHistoryNotice78] = Field(default_factory=list)
    turn_started: dict[str, int] = Field(default_factory=dict)  # player -> number of their latest turn
    controlled_since: dict[str, ControlMark] = Field(default_factory=dict)
    # -- control (wave 3K) -- the cards whose controller a layer-2 effect set (so that when the effect ends
    # they revert to their previous controller, 613.1b), not one a player moved by hand
    control_changed: list[str] = Field(default_factory=list)
    control_baselines: dict[str, str] = Field(default_factory=dict)  # exact object -> controller before layer 2
    named_combat_damage: dict[str, list[str]] = Field(default_factory=dict)
    named_combat_history_known: bool = False
    named_combat_history_notice: bool = False
    conceded: list[str] = Field(default_factory=list)
    lost: dict[str, str] = Field(default_factory=dict)  # player -> why (0 life, poison, …)
    winner: str | None = None
    draw_reason: str | None = None  # 104.4: explicit draw; old saves default to unfinished
    # -- casting extras (wave 18E) -- miracle (app/rules/miracle.py): the cards whose owner may reveal them now (never sent to anyone else),
    # the last turn each player drew (for "the first card you've drawn this turn"), and the free casts that are miracle casts
    # (melee, 702.121a: the opponents each attacking player attacked directly — not through a planeswalker or battle, 506.3 — in the
    # latest declaration of attackers: "for each opponent you attacked with a creature this combat")
    attacked_players: dict[str, list[str]] = Field(default_factory=dict)
    # -- trigger other (wave 25B) -- player -> the total power of the creatures declared as attackers in their latest declaration, as they
    # were declared ("you attacked with creatures with total power 6 or greater this combat": pack tactics; review 25B: a snapshot)
    attack_power: dict[str, int] = Field(default_factory=dict)
    miracle: list[str] = Field(default_factory=list)
    miracle_turn: dict[str, int] = Field(default_factory=dict)
    miracled: list[str] = Field(default_factory=list)
    drew_from_empty: list[str] = Field(default_factory=list)  # loses at the next state-based check
    escape_grants110m: list[dict[str, Any]] = Field(default_factory=list)  # -- (wave 110M) -- "gains escape until end of turn" (Desdemona): the card's object id, its owner and the turn
    lose_shields110m: list[dict[str, Any]] = Field(default_factory=list)  # -- (wave 110M) -- "the next time you would lose the game this turn, instead ...": player, turn, source card and name
    deathtouched: list[str] = Field(default_factory=list)  # creatures dealt damage by a deathtouch source
    prevention: dict[str, int] = Field(default_factory=dict)  # player / object id -> damage to prevent this turn
    # (wave 17A) "<key>#<id>" -> a shield that has an additional effect (615.5): its rider and who made it
    prevention_riders: dict[str, dict[str, Any]] = Field(default_factory=dict)
    regen_shields: dict[str, int] = Field(default_factory=dict)  # object id -> regeneration shields this turn
    regeneration_riders: list[RegenerationShield] = Field(default_factory=list)
    destruction_replacements: dict[str, Any] | None = None  # frozen CR 616 choices before a destruction batch commits
    no_regen: list[str] = Field(default_factory=list)  # -- can't regenerate (wave 19E) -- objects that can't be regenerated this turn
    linked_exile: dict[str, list[str]] = Field(default_factory=dict)  # source object -> cards exiled "until it leaves"
    # -- exiled with (wave 6D) -- source object -> the objects its abilities exiled (607.2a: "the exiled card",
    # "cards exiled with ~"; app/rules/exiled_with.py)
    exiled_with: dict[str, list[str]] = Field(default_factory=dict)
    linked_exile_turns71: dict[str, dict[str, int]] = Field(default_factory=dict)  # Native link scope -> exact exile OID -> actual exile turn.

    created_with: dict[str, list[str]] = Field(default_factory=dict)  # exact created-token incarnations per source/borrowed scope
    hideaway: dict[str, HideawayLook] = Field(default_factory=dict)  # -- hideaway (wave 29D) -- exiled object id -> who may look at it (702.75a)
    # -- can't lose life (wave 29D) -- 119.7-119.8: resolved "your life total can't change" effects (app/rules/life_lock.py): {id, player, controller,
    # gain, lose, until ("turn" | "next_turn"), turn, label}
    life_locks: list[dict[str, Any]] = Field(default_factory=list)
    # -- resolution memory (wave 22D) -- 610.3: an object exiled "until ~ leaves" from a hand returns there (its previous zone):
    # exiled object id -> "hand" (absent: the battlefield)
    linked_exile_from: dict[str, str] = Field(default_factory=dict)
    vote_control: list[list[Any]] = Field(default_factory=list)  # -- voting (wave 18C) -- [turn, chooser]: "You choose how each player votes this turn"
    # -- group choices (wave 53D) -- the spells and abilities that had players guess or group cards or permanents into a pile this turn: [turn, object id] (The Celestial
    # Toymaker counts them); and the numbers an object has chosen so far, by object id (The Toymaker's Trap: "a number … that hasn't been chosen"; a new object has none, 400.7)
    grouped: list[list[Any]] = Field(default_factory=list)
    chosen_numbers: dict[str, list[int]] = Field(default_factory=dict)
    # -- group choices (wave 53D) -- "secretly choose an opponent" / "a creature type" (Stalking Leonin, A Killer Among Us): [the chooser, the value] by rules object id, kept
    # server-side only (the views never carry it) until "Reveal the player you chose" shows it as a cost is paid; a new object has none (400.7)
    secret_choices: dict[str, list[str]] = Field(default_factory=dict)
    attach_asks110e: list[str] = Field(default_factory=list)  # -- becomes attached, choose (wave 110E) -- Equipment ids owing their color choice
    # -- piles (wave 53D) -- "Only creatures in the pile of their choice can attack this turn" (Fight or Flight): [turn, the attacking player, [object ids that may]]; every entry of
    # the turn binds (ruling 2008-08-01: with two, a creature must be in both chosen piles), and a creature that entered later is no object in any pile
    attack_piles: list[list[Any]] = Field(default_factory=list)
    block_piles110f: list[list[Any]] = Field(default_factory=list)  # -- wave 110F -- Stand or Fall: [turn, the player, the objects of the chosen pile] (only they can block, 700.3)
    commander_color110f: dict[str, str] = Field(default_factory=dict)  # -- wave 110F -- Faceless One: card id -> chosen color letter (607.2p)
    opening_revealed: list[str] = Field(default_factory=list)  # -- opening hand (wave 18C) -- cards revealed until the first turn (103.6b)
    deferred_payments: list[DeferredPaymentWindow] = Field(default_factory=list)
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
    player_control: list[PlayerControl] = Field(default_factory=list)  # -- controlling another player (wave 18H) --
    turn_base: str | None = None
    # -- most-played cards (wave 43B) -- 500.1: the turns each player has begun (extra turns too; empty until the game's first turn ends: that is the first
    # player's first turn); read by "your first, second, or third turn of the game" (values "turns_taken", engine.start_next_turn)
    turns_taken: dict[str, int] = Field(default_factory=dict)
    no_power_up_turns: list[int] = Field(default_factory=list)  # -- power-up (wave 50J) -- the turn numbers power-up abilities can't be activated in (Kang the Conqueror's extra turn)
    extra_turn: bool = False  # -- static_other (wave 42A) -- 500.7: the turn in progress is an extra turn ("can't attack during extra turns", Medomai; engine.start_next_turn)
    # … and "can't gain life this turn / for the rest of the game" (614.17; app/rules/cant_gain.py):
    # {"id", "player", "controller", "turn" (None: the rest of the game), "label"}
    cant_gain: list[dict[str, Any]] = Field(default_factory=list)
    # -- prohibitions (wave 22B) -- "You can't lose the game this turn …" (104.2b, 104.3; app/rules/game_result.py):
    # {"player", "what": "lose"|"win", "turn"}
    results: list[dict[str, Any]] = Field(default_factory=list)
    # -- ability words (wave 20C) -- "You have no maximum hand size for the rest of the game." (app/rules/hand_size.py): the players
    no_max_hand: list[str] = Field(default_factory=list)
    no_max_hand_at: dict[str, tuple[int, int]] = Field(default_factory=dict)  # exact [object sequence, effect timestamp]
    no_max_hand_legacy_bound: dict[str, int] = Field(default_factory=dict)  # known upper bound, not an invented original timestamp
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
    resolved_mana_replacements: list[ResolvedManaColorReplacement] = Field(default_factory=list)
    # 903.9b: commanders just put into their owner's hand / library (card id -> "hand" | "library")
    # whose owner hasn't yet said whether it goes to the command zone instead (asked before priority)
    pending_903_9b: dict[str, str] = Field(default_factory=dict)
    # -- zone replacements (wave 22C) -- 616.1: a card that would go to a graveyard where two replacement effects with
    # different results apply (Blightsteel's shuffle vs Rest in Peace) stays where it is until its controller (owner if
    # it has none) picks the one that applies: card id -> {"oid", "dest", "options": {outcome: source label}}
    pending_616: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # -- graveyard order (wave 40C) -- 404.3: batches of two or more cards that were put into one graveyard together, whose owner is to
    # arrange them before anyone gets priority: {"owner", "cards" (bottom to top)} (app/rules/graveyard_order.py)
    pending_gy_order: list[dict[str, Any]] = Field(default_factory=list)
    # 903.9b asked *before* the move, as a resolving effect is about to put a commander into its
    # owner's hand or library: "<object id>><hand|library>" -> "yes" (command zone) / "no",
    # consumed by that move (app/rules/replacements.ask_903_9b_first)
    answers_903_9b: dict[str, str] = Field(default_factory=dict)
    # "As ~ enters, choose …" answers given while a permanent spell / land is about to enter (card
    # id -> {"color": "Blue"}), consumed by the entry (614.12a)
    entry_choices: dict[str, dict[str, str]] = Field(default_factory=dict)
    devoured: dict[str, int] = Field(default_factory=dict)  # -- keyword mechanics (wave 9D) -- object -> permanents it devoured (702.82b)
    paradigm_seen: list[str] = Field(default_factory=list)  # -- keywords (wave 50H) -- "player:name" of the paradigm spells that have resolved (702.192a: the first time)
    paradigm: list[dict[str, str]] = Field(default_factory=list)  # (and the cards they exiled, to copy at each of the player's precombat main phases)
    haunting: dict[str, str] = Field(default_factory=dict)  # -- keywords (wave 50H) -- a haunt card's object in exile -> the object it haunts (702.55b)
    tribute_paid: list[str] = Field(default_factory=list)  # -- keywords (wave 50H) -- objects that entered with their tribute paid (702.104b)
    devoured_ids: dict[str, list[str]] = Field(default_factory=dict)  # (wave 48B: and the objects they were, for "the Goblins it devoured": their last known information, 608.2h)
    buyback: list[str] = Field(default_factory=list)  # stack objects cast with buyback
    dashed: list[str] = Field(default_factory=list)
    bestowed: list[str] = Field(default_factory=list)  # -- keywords (wave 15E) -- bestowed Aura spells / permanents (702.103b)
    mutating: list[str] = Field(default_factory=list)  # -- merged permanents (wave 18D) -- mutating creature spells on the stack (702.140a)
    evoked: list[str] = Field(default_factory=list)  # evoked spells: sacrificed as they enter (702.74)
    rebound_cast: list[str] = Field(default_factory=list)  # rebound spells cast from a hand (on the stack)
    rebounding: list[str] = Field(default_factory=list)  # exiled by rebound: cast at the owner's next upkeep  # dashed spells: haste + back to hand at end step
    rebound_objects: dict[str, str] = Field(default_factory=dict)  # Exact exile objects pending their next upkeep.
    rebound_controllers: dict[str, str] = Field(default_factory=dict)  # Controller when the rebound replacement applied, not necessarily owner.
    suspended: list[str] = Field(default_factory=list)  # cards exiled with suspend (702.62)
    # -- hidden exile (wave 18A) -- 702.143d: a foretell cost an effect gave a foretold card ("its mana cost reduced by {2}")
    foretell_costs: dict[str, str] = Field(default_factory=dict)
    foretell_templates: dict[str, ForetellCostReceipt] = Field(default_factory=dict)
    foretold: dict[str, int] = Field(default_factory=dict)  # -- hidden exile (wave 18A) -- 702.143d: card -> the turn it became foretold
    free_casts: list[str] = Field(default_factory=list)
    madness_declined: dict[str, MadnessFollowup] = Field(default_factory=dict)
    alt_costs: dict[str, str] = Field(default_factory=dict)  # card -> the cost to pay instead (madness)  # cards the engine lets be cast without paying (suspend)
    suspend_haste: list[str] = Field(default_factory=list)  # suspended creature spells: haste when they enter
    renowned: list[str] = Field(default_factory=list)  # rules objects that became renowned (702.112)
    monstrous: list[str] = Field(default_factory=list)  # rules objects that became monstrous (701.37b)
    monstrous_x: dict[str, int] = Field(default_factory=dict)  # -- X sized by a count (wave 19F) -- 701.37c: its X "as that permanent became monstrous"
    levels: dict[str, int] = Field(default_factory=dict)  # -- Class (wave 16A) -- 716.2b: rules object -> class level (none: level 1, 716.2d)
    unlocked: dict[str, list[int]] = Field(default_factory=dict)  # -- Rooms (wave 18G) -- 709.5c: rules object -> its unlocked doors (1 left, 2 right)
    suspected: list[str] = Field(default_factory=list)  # rules objects that are suspected (701.60: -- suspect (wave 12A) --)
    # -- as long as (wave 35D) -- what an object has done since it became that object (400.7), dropped as it leaves the battlefield:
    # "hasn't dealt damage yet" (120.3: a source that dealt more than 0 damage: its oid, and "<oid>+combat" for combat damage)
    dealt_damage: list[str] = Field(default_factory=list)
    prepared: dict[str, str] = Field(default_factory=dict)  # -- prepared (wave 13C, 722.3) -- permanent's rules object -> its copy in exile
    tomb110o: dict[str, dict[str, list[str]]] = Field(default_factory=dict)  # -- (wave 110O) -- Cyclopean Tomb's object id -> {"put": lands (object ids) it put a mire counter onto, "removed": those it removed from}
    notes110o: dict[str, list[str]] = Field(default_factory=dict)  # -- (wave 110O) -- object id -> the creature types noted for it (Volo's Journal)
    collection110o: dict[str, str] = Field(default_factory=dict)  # -- (wave 110O) -- object id of a card exiled with a collection counter -> the controller of the ability that exiled it (Evelyn)
    wipe_shields110o: dict[str, int] = Field(default_factory=dict)  # -- (wave 110O) -- 614.1a: object id -> "next time it would be destroyed this turn, remove all damage marked on it instead" (Pyramids)
    prepare_spells110o: list[str] = Field(default_factory=list)  # -- (wave 110O) -- 722.3d: the exiled copies that were cast ("a prepared spell")
    phase_lifetimes: list[PhaseLifetime] = Field(default_factory=list)
    camouflage_turn110f: int = 0  # -- wave 110F -- the turn Camouflage resolved (blockers are replaced by piles)
    camouflage110f: dict[str, list[list[str]]] = Field(default_factory=dict)  # -- wave 110F -- defending player -> their piles (creature ids), until every player has divided
    ferris110f: dict[str, list[str]] = Field(default_factory=dict)  # -- wave 110F -- Ferris Wheel (rules object) -> the creatures (rules objects) it has phased out
    put_with110f: dict[str, list[str]] = Field(default_factory=dict)  # -- wave 110F -- 607.2c: source (rules object) -> the objects its ability put onto the battlefield (Diabolic Servitude)
    specimens110f: list[list[Any]] = Field(default_factory=list)  # -- wave 110F -- Gather Specimens: [its controller, the turn] for each one that resolved
    entry_actor110f: str = ""  # -- wave 110F -- the player putting the permanent being planned onto the battlefield (Land Equilibrium), set around ``entry_plan`` (never saved meaningfully: reset after)
    phase_holds110k: list[PhaseHold110K] = Field(default_factory=list)  # -- wave 110K --
    no_regen_sources110k: list[str] = Field(default_factory=list)  # -- wave 110K -- Runesword: the objects whose damage this turn makes a creature unable to regenerate
    damaged_players110k: dict[str, list[str]] = Field(default_factory=dict)  # -- wave 110K -- source object -> the players it has dealt damage to (Diseased Vermin)
    guile110g: list[str] = Field(default_factory=list)  # (wave 110G) Guile: spells exiled instead of countered, whose controller's cast offer is still to be made
    roll_shields110g: list[dict[str, Any]] = Field(default_factory=list)  # (wave 110G) Bamboozling Beeble: {"player", "by", "turn"} one-shot roll replacements
    poison_once110g: dict[str, int] = Field(default_factory=dict)  # player -> turn they got a poison counter under Melira (wave 110G): no more that turn
    damaged: dict[str, int] = Field(default_factory=dict)  # player -> last turn they were dealt damage (bloodthirst)
    echo_done: list[str] = Field(default_factory=list)  # "<object>:<controller>" whose echo upkeep came
    flashback: list[str] = Field(default_factory=list)  # stack objects cast with flashback (exiled as they leave)
    # Combat bookkeeping; the attack/block markers on the table are the visible truth.
    blocked: list[str] = Field(default_factory=list)  # attackers that became blocked (stay blocked)
    attacking_bands: list[list[str]] = Field(default_factory=list)  # CR 702.22: object IDs, fixed on declaration; pruned on leaving combat.
    could_attack110g: list[str] = Field(default_factory=list)  # -- wave 110G -- objects that could be declared as attackers this turn (Season of the Witch), with the turn below
    could_attack_turn110g: int = 0
    no_attackers: bool = False  # nobody attacked: skip blockers and damage (rule 508.8)
    blockers_pending: list[str] = Field(default_factory=list)  # defending players still to declare
    combat_round: Literal["", "first", "done"] = ""
    # -- multiple blocks (wave 13B, 14A) -- 510.1c-d: how a creature divides its combat damage among the creatures it is
    # blocked by / blocks (creature card -> target card or player -> damage), answered before the round is dealt and dropped once it is
    block_split: dict[str, dict[str, int]] = Field(default_factory=dict)
    assign_unblocked: dict[str, bool] = Field(default_factory=dict)  # -- static_other sweep (wave 19A) -- attacker -> "as though it weren't blocked"
    declare_choosers: dict[str, dict[str, Any]] = Field(default_factory=dict)  # -- declaration choosers (wave 110A) -- "attack"/"block" -> {player, turn, combat}: who declares them, until end of turn/combat
    assign_unblocked_turn: dict[str, int] = Field(default_factory=dict)  # -- wave 110A -- player -> turn number: "creatures you control assign combat damage as though they weren't blocked" this turn (510.1c)
    assign_forced110h: dict[str, int] = Field(default_factory=dict)  # -- wave 110H -- creature card -> turn number: it assigns its combat damage as though it weren't blocked (Outmaneuver)
    block_caps: dict[str, int] = Field(default_factory=dict)  # -- commander sweep (wave 49B) -- 509.1b: player -> "can't block with more than N creatures this combat" (Mirri), dropped at end of combat
    # -- combat (wave 5C) -- 500.8: the phases still to come after the current one when effects added some (the
    # last is the phase that would have come next), and how many combat phases began this turn
    step_serial: int = 0
    step_counts: dict[str, int] = Field(default_factory=dict)
    step_count_turn: int = 0
    previous_turn: tuple[str, int] | None = None
    extra_steps: list[str] = Field(default_factory=list)
    upkeep_only: bool = False
    extra_beginning: bool = False
    extra_phases: list[str] = Field(default_factory=list)  # (wave 49B: a combat phase added with a delayed trigger of its own is "begin_combat@<trigger id>")
    combat_tag: str = ""  # -- commander sweep (wave 49B) -- the delayed trigger id of the combat phase now beginning, if it was added with one ("at the beginning of that combat")
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
    next_life_operation: int = 0  # Reserved before a life vector can pause for replacements.
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
    stack_lki: dict[str, StackMemory] = Field(default_factory=dict)  # -- spell copies (wave 31D) -- object id of a spell that left the stack -> how it was there
    # -- trigger lines (wave 100A) -- object id -> the players its enters ability targeted as it went on the stack (Soul Scourge's "that player")
    linked_players100a: dict[str, list[str]] = Field(default_factory=dict)
    batch: int = 0  # last event batch number
    exploited110j: list[tuple[str, str]] = Field(default_factory=list)  # -- wave 110J -- (exploiter object, creature it exploited), 702.110b: "if it exploited that creature"
    events: list[Event] = Field(default_factory=list)  # events since the engine last acted (this intent's, or manual ones)
    events_dropped: bool = False  # manual play produced more events than are kept
    actions: int = 0  # player actions (not passes) taken, for "pass until next action"
    last_actor: str | None = None
    engine_version: int = 0  # RULES_ENGINE_VERSION that last acted on this table
    effects: list[ContinuousEffect] = Field(default_factory=list)
    timestamp: int = 0  # last timestamp handed out (613.7)
    pending_triggers: list[PendingTrigger] = Field(default_factory=list)
    combat_history_notices: list[CombatHistoryNotice] = Field(default_factory=list)
    trigger_batch: int = 0  # last event batch the trigger collector looked at
    stack: dict[str, StackEntry] = Field(default_factory=dict)  # stack card id -> what it does
    draws_this_turn: dict[str, int] = Field(default_factory=dict)  # player -> cards drawn (for "your second card")
    draws_turn: int = 0
    # Aura spells on the stack -> what they target (303.4a); they enter attached to it (303.4f).
    aura_targets: dict[str, TargetRef] = Field(default_factory=dict)
    # Exact last enchanted/equipped object, retained after detachment and source
    # departure for instructions that need the last enchanted permanent (608.2h).
    last_attached_hosts: dict[str, ObjectRef] = Field(default_factory=dict)
    # Original activation object -> exact hand cards revealed until it leaves the stack.
    revealed_activation_costs: dict[str, list[CostReveal]] = Field(default_factory=dict)
    pending_crafts: dict[str, list[ObjectRef]] = Field(default_factory=dict)
    crafted_materials: dict[str, list[ObjectRef]] = Field(default_factory=dict)
    noted_mana: dict[str, NotedMana | None] = Field(default_factory=dict)  # Missing: old/unknown; None: known never noted.
    # -- reanimation Auras (wave 51F) -- Aura object id -> the objects it is tied to: the creature card in a graveyard it enchants (303.4a: not a permanent, so not
    # ``attached_to``), then the creature it put onto the battlefield (Animate Dead, Dance of the Dead, Necromancy; app/rules/reanimate_auras.py)
    aura_links: dict[str, list[str]] = Field(default_factory=dict)
    # Battles on the battlefield (object id) -> their protector (310.9; app/rules/battles.py).
    protectors: dict[str, str] = Field(default_factory=dict)
    # -- chosen player (wave 4J) -- "As ~ enters, choose an opponent / a player": object id -> the chosen player's id
    # (the permanent's "Chosen opponent: <name>" entry is only the display; app/rules/chosen.py). Older saves have
    # only the display name: chosen.player_of resolves it when exactly one player has that name.
    color_words71: dict[str, list[ColorWordEntry71]] = Field(default_factory=dict)
    chosen_color_pairs: dict[str, ChosenColorPairReceipt] = Field(default_factory=dict)
    chosen_players: dict[str, str] = Field(default_factory=dict)
    modes110f: dict[str, list[int]] = Field(default_factory=dict)  # (wave 110F) card id -> the modes an opponent chose for the spell being cast (700.2e)
    # -- wave 110A -- player -> ``next_object`` when their last turn ended ("entered since your last turn ended", selectors)
    noted110e: dict[str, list[int]] = Field(default_factory=dict)  # -- wave 110E -- Bell Borca: rules object -> [turn, event batch] it arrived at (wave110e_note)
    circled110g: dict[str, str] = Field(default_factory=dict)  # -- wave 110G -- Cryptic Spires: card id -> the two colors circled before the game (wave110g_spires)
    commander_color110e: dict[str, str] = Field(default_factory=dict)  # -- wave 110E -- Clara Oswald: commander card id -> the color chosen before the game (wave110e_clara)
    chosen_objects: dict[str, str] = Field(default_factory=dict)  # -- wave 110A -- source card id -> the object it chose as it entered (wave110a_pick)
    turn_end_objects: dict[str, int] = Field(default_factory=dict)
    hit110b: list[str] = Field(default_factory=list)  # -- wave 110B -- players dealt combat damage since their last turn ended (Marchesa, Resolute Monarch)
    # -- linked words (wave 33B) -- 607.2f: "As this enchantment enters, choose Khans or Dragons.": object id -> the word it chose (app/rules/chosen.py)
    chosen_words: dict[str, str] = Field(default_factory=dict)
    # How each spell was paid for (stack object id -> record); follows the spell onto the battlefield.
    payments: dict[str, PaymentRecord] = Field(default_factory=dict)
    # Each player's intents this turn, for REPEAT LAST VALIDATED SEQUENCE (payloads, newest last).
    recent: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    recent_turn: int = 0
    # Cast / play permissions granted by effects, cost modifiers with a duration, and which top
    # library cards are revealed by permanents on the table (app/rules/permissions.py).
    permissions: list[Permission] = Field(default_factory=list)
    cost_modifiers: list[CostModifier] = Field(default_factory=list)
    next_spell_grants: list[NextSpellGrant] = Field(default_factory=list)  # -- spell grants (wave 28C) --
    source_hand_reveals79: list[SourceHandReveal79] = Field(default_factory=list)
    top_reveals: list[TopReveal] = Field(default_factory=list)
    face_down_looks110l: list[dict[str, Any]] = Field(default_factory=list)  # -- (wave 110L) -- {"player", "turn"}: "Until end of turn, you may look at face-down creatures you don't control any time" (Lumbering Laundry)
    # -- conditional / instead clauses (wave 1B) --  this turn's and last turn's history (TurnLog)
    turn_log: TurnLog = Field(default_factory=TurnLog)
    last_turn_log: TurnLog | None = None
    completed_own_turns: dict[str, CompletedOwnTurn] = Field(default_factory=dict)
    own_turn_history_known: list[str] = Field(default_factory=list)
    own_turn_history_notice: bool = False
    cast_history_complete: bool | None = None  # True only when automation observed the trusted fresh-game boundary.
    named_casts_game: dict[str, dict[str, int]] = Field(default_factory=dict)  # public names when actually cast, per player, across turns
    entry_life_losses: dict[str, int] = Field(default_factory=dict)  # exact source incarnation / entry ability -> actual life lost
    craft110b: bool = False  # transient: a craft ability's cost is being paid (Plan.do sets it)
    cause110g: str | None = None  # transient: the controller of the effect whose step is being applied (Plan.do sets it)
    entry_life_origins: list[str] = Field(default_factory=list)  # automatic entries observed with entry-life bookkeeping available
    entry_life_notices: list[str] = Field(default_factory=list)  # legacy source/ability keys already reported as unknown
    # -- replacement effects stage 2 (wave 2E; app/rules/replace.py) --
    # Cards each player actually drew in the step ``replace_step_key`` ("<turn>:<phase>"), counted as
    # they're drawn (for "except the first one they draw in each of their draw steps", 504.1).
    replace_step_key: str = ""
    replace_step_draws: dict[str, int] = Field(default_factory=dict)
    # -- draws (wave 110C) -- "The first time you would draw a card each turn": draw events seen per player in the turn ``would_draw_turn`` (121.6, 614.11)
    proctor_links110c: dict[str, str] = Field(default_factory=dict)  # (wave 110C) Strict Proctor: a trigger's id (as it triggered) -> its stack object, once put
    named_cycles110c: dict[str, dict[str, int]] = Field(default_factory=dict)  # (wave 110C) Yidaro: cards cycled this game, by player and normalized name
    would_draw_turn: int = -1
    would_draw: dict[str, int] = Field(default_factory=dict)
    # -- counters & designations (wave 3E; app/rules/designations.py) --
    # 309.2a / 309.4: each player's dungeon card in the command zone and the room their venture marker is on
    dungeons: dict[str, DungeonMark] = Field(default_factory=dict)
    completed_dungeons: dict[str, list[str]] = Field(default_factory=dict)  # 309.7: player -> dungeons completed, in order
    enduring_story: list[str] = Field(default_factory=list)  # -- storied (wave 45D) -- 702.195b: players with the designation, for the rest of the game
    ring_tempted: dict[str, int] = Field(default_factory=dict)  # 701.54c: player -> times the Ring tempted them (their emblem)
    ring_bearers: dict[str, str] = Field(default_factory=dict)  # 701.54a: player -> their Ring-bearer (rules object id)
    # -- keyword actions & face-down (wave 3F) -- firebending (702.189a): the {R} each player added that
    # they don't lose as steps end until end of combat (player -> how much of the red in their pool)
    combat_mana: dict[str, int] = Field(default_factory=dict)
    # -- refused copy/mana (wave 3R3; app/rules/kept_mana.py) -- "Until end of turn, you don't lose this mana as
    # steps and phases end" (500.4, 106.4): {"player", "mana": {sym: n}, "until": "end_of_turn" | "end_of_combat",
    # "turn"}; never more than that player's pool holds (spending uses the other mana first)
    kept_mana: list[dict[str, Any]] = Field(default_factory=list)
    # -- review 34 -- 514.3a: players got priority in this cleanup step (a state-based action or a trigger), so another cleanup step follows it
    cleanup_again: bool = False
    # -- mana provenance (wave 18B) -- does any card in this game ask where mana came from (mana_units.tracking)? Decided once, from
    # the cards of the game; None until the first mana is added
    provenance: bool | None = None
    # -- refused look/cast-free (wave 3R5) -- a free cast made while a spell or ability resolves (608.2g):
    # {"card", "ctx", "e"} — the resolution to continue once that cast is done or abandoned
    # (app/rules/permissions.free_cast_done); and the stack objects cast "without paying" whose
    # "If that spell would be put into your graveyard, exile it instead" applies (614.1a)
    free_cast_then: dict[str, Any] | None = None
    # -- granted casts (wave 29B) -- card -> the half / face (1) its "cast it?" answer named ("yes@1"): the only one casting.cast_free accepts
    free_cast_faces: dict[str, int] = Field(default_factory=dict)
    exile_if_graveyard: list[str] = Field(default_factory=list)
    bottom_if_graveyard: list[str] = Field(default_factory=list)  # Exact cast spell OIDs only; never follows a permanent.
    # -- cast permissions (wave 30Q) -- stack object -> what a permission's "If you cast a spell this way, that artifact enters tapped / with a finality
    # counter on it / it gains "…"" does as it enters ({"tapped": True, "counters": {"finality": 1}, "abilities": [text]}); the new object a card becomes
    # when it leaves the stack (400.7) never matches a stale entry
    cast_enters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # -- cast riders (wave 38C) -- 614.1a: stack object (an instant or sorcery spell) -> "exile it instead of putting it into your graveyard as it resolves" and
    # what follows when it was ({"bind", "then", "controller", "source_card", "source_object", "name"}); a countered spell never uses it (it doesn't resolve),
    # and the new object a card becomes (400.7) never matches a stale entry
    exile_resolves: dict[str, dict[str, Any]] = Field(default_factory=dict)
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

    def last_known(self, card_id: str) -> ObjectSnapshot | None:
        """The newest last known information of a card (608.2h). ``lki`` gains an entry as each object leaves, so the last one is its latest
        incarnation, even when it left the battlefield twice this turn (blinked, then sacrificed)."""
        return next((x for x in reversed(self.lki.values()) if x.card == card_id), None)

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
        crew_saddle_history_turn80=(state.turn.number if state.rules is None and state.seq <= 1 and state.turn.number == 1 else None),
        first_event_history_turn78=(state.turn.number if state.rules is None and state.seq <= 1 and state.turn.number == 1 else None),
        cast_history_complete=True if state.rules is None and state.seq <= 1 and state.turn.number == 1 else None,
        target_activation_history_turn=state.turn.number if state.rules is None and state.seq <= 1 and state.turn.number == 1 else None,
        coin_history_from_turn=state.turn.number if state.seq <= 1 else state.turn.number + 1,
        graveyard_history_from_turn=state.turn.number if state.seq <= 1 else state.turn.number + 1,
        combat_memory=CombatMemory(known_empty=list(state.seat_order) if state.seq <= 1 else []),
        turn_started={state.turn.active_player: state.turn.number},
        controlled_since={
            cid: ControlMark(controller=c.controller, turn=0, observed_from_turn=state.turn.number)
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
        owner=c.owner, controller=c.controller, zone=c.zone, turn=state.turn.number, tapped=c.tapped, choices=dict(c.choices),
        stickers101=[p.model_dump() for p in c.stickers101],
        face_down=c.face_down, face_down_kind=c.face_down_kind, face_down_as=c.face_down_as, face=c.face, is_token=c.is_token,
        token_source_id=c.token_source.source_id if c.token_source else None,
        token_power=token.power if token else None, token_toughness=token.toughness if token else None,
        token_type_line=token.type_line if token else None, token_colors=list(token.colors) if token else [],
        token_mana_cost=token.mana_cost if token else "",
        commander_key=c.commander_key, counters=dict(c.counters), damage=c.damage,
        ring_bearer=bool(rules and c.zone.endswith(":battlefield") and rules.ring_bearers.get(c.controller) == rules.object_id(c.id)),
        suspected=bool(rules and rules.object_id(card_id) in rules.suspected),
        effects=[e.value or e.name for e in c.effects], attacking=c.is_attacking, attacking_without_target=c.attacking_without_target, attack_defender_lost=c.attack_defender_lost, entry_characteristics=c.entry_characteristics,
        attack_on=f"{c.attacking.kind}:{c.attacking.id}" if c.attacking is not None else None,  # (wave 38A)
        blocking=c.is_blocking, blocking_ids=[x for x in (c.blocking, *c.blocking_more) if x], attached_to=c.attached_to,
        attached_object=rules.object_id(c.attached_to) if rules is not None and c.attached_to is not None and c.attached_to in state.cards else None,
        text=token.text if token else "",
        blocked_by_ids=[o.id for o in state.cards.values() if o.id != card_id and o.blocks(card_id)],  # (wave 53C)
        banded_with_ids=[oid for band in rules.attacking_bands if rules.object_id(card_id) in band for oid in band
                         if oid != rules.object_id(card_id)] if rules and c.is_attacking else [],
        attached_objects={a.id: rules.object_id(a.id) for a in state.cards.values() if a.attached_to == c.id} if rules else {},
        attached_objects_known=rules is not None,
        attached_player=c.attached_player,  # -- attached events (wave 4L) --
        merged=[p.model_dump() for p in c.merged], melded=c.melded,  # (wave 18D)
        x=c.stack_info.x if c.zone == "stack" and c.stack_info is not None else None,  # (wave 5B)
    )


def remember_stack(state: GameState, card_id: str, info: Any = None, *, was_stack: bool = False) -> None:
    """-- spell copies (wave 31D) -- a spell is leaving the stack: keep how it was there (its entry — targets, modes, X, kicker — and its
    annotations) under its object id, for a copy of it made after it left (608.2h, 707.10). Abilities cease to exist, so retain their
    ability object alongside its rules entry; one remembered already (by whoever removed its entry first) stays."""
    rules = state.rules
    card = state.cards.get(card_id)
    entry = rules.stack.get(card_id) if rules is not None else None
    if rules is None or card is None or (card.ability is None and ((entry is not None and entry.kind != "spell") or card.is_token)):
        return
    if entry is None and card.zone != "stack" and not was_stack:
        return
    oid = rules.object_id(card_id)
    if oid in rules.stack_lki:
        return
    info = info if info is not None else card.stack_info
    rules.stack_lki[oid] = StackMemory(card=card_id, turn=state.turn.number, entry=entry.model_copy(deep=True) if entry is not None else None,
                                       info=info.model_dump() if info is not None else {},
                                       aura_target102=rules.aura_targets.get(card_id),
                                       evoked=card_id in rules.evoked, dashed=card_id in rules.dashed,
                                       ability_card=card.model_dump(mode="json") if card.ability is not None else None)


class Capture:
    """The table just before one step is applied (in memory only, never saved): what ``track``
    compares against to find zone changes, counters and taps, and the objects' last known
    information for anything that leaves the battlefield or the stack."""

    __slots__ = ("zones", "snaps", "resources", "types", "designations", "stack_info")

    def __init__(self, state: GameState) -> None:
        self.zones = {cid: c.zone for cid, c in state.cards.items()}
        # CR 608.2h: a copy instruction may need a card exiled as a cost after
        # it leaves exile. Capture those public objects while they are there.
        # CR 603.10a: graveyard-leave events retain their public old object even
        # when a later library shuffle deliberately destroys its physical id.
        paid_exile = {oid for payment in state.rules.payments.values() for oid in payment.exiled_objects} if state.rules else set()
        self.snaps = {
            cid: snapshot(state, cid) for cid, c in state.cards.items() if _zone_name(c.zone) in TRACKED_ZONES or _zone_name(c.zone) == "graveyard"
            or (_zone_name(c.zone) == "exile" and not c.face_down and state.rules is not None
                and (state.rules.object_id(cid) in paid_exile or bool(c.counters) or cid in state.rules.suspended))
        }
        self.resources = {pid: dict(p.resources) for pid, p in state.players.items()}
        # -- spell copies (wave 31D) -- the annotations of the spells on the stack (X, modes, kicker), reset when one leaves it
        self.stack_info = {cid: c.stack_info.model_copy(deep=True) for cid, c in state.cards.items() if c.zone == "stack" and c.stack_info is not None}
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
    if kind in ("tapped", "untapped"):
        fields.setdefault("step_phase", state.turn.phase)
        fields.setdefault("active_player", state.turn.active_player)
    rules = state.rules
    if rules is None:
        return
    if kind == "zone_change" and rules.cause110g is not None:
        fields.setdefault("cause110g", rules.cause110g)
    if kind == "zone_change" and rules.craft110b:
        fields.setdefault("craft110b", True)
    rules.events.append(Event(batch=rules.batch + 1, kind=kind, turn=state.turn.number, **fields))
    if kind == "turned_face_up" and (up_log110f := turn_log_now(state)) is not None and fields.get("object_id"):
        up_log110f.turned_up110f = list(dict.fromkeys([*up_log110f.turned_up110f, fields["object_id"]]))
        up_log110f.turned_up_by110b = list(dict.fromkeys([*up_log110f.turned_up_by110b, fields.get("actor") or ""]))
    if kind == "turned_face_up" and (up_log110l := turn_log_now(state)) is not None and fields.get("actor"):  # -- (wave 110L) -- who turned it face up (702.37e)
        up_log110l.facts.append(TurnFact(kind="turned_up110l", player=fields["actor"], object_id=fields.get("object_id")))
    if kind == "designation" and str(fields.get("counter") or "").startswith("bend110b:") and (bend_log := turn_log_now(state)) is not None:
        bend_log.facts.append(TurnFact(kind=fields["counter"].replace(":", "_"), player=fields["player"]))  # -- (wave 110B) -- wave110b_bend.py
    if kind == "fought" and (fight_log90 := turn_log_now(state)) is not None:
        fight_log90.fought90 = list(dict.fromkeys([*fight_log90.fought90, *(snap.object_id for snap in fields.get("fighters90", []))]))
    # CR 107.14, 608.2i: count removals during this turn, including costs; gains never offset them.
    if kind == "player_counters" and fields.get("counter") == "energy" and int(fields.get("amount") or 0) < 0 \
            and (log := turn_log_now(state)) is not None and (player := fields.get("player")):
        log.energy_lost[player] = log.energy_lost.get(player, 0) - int(fields["amount"])
    if kind in ("life_gain", "life_loss", "drew"):  # -- conditional / instead clauses (wave 1B) --
        _note_player_fact(state, kind, fields.get("player"), int(fields.get("amount") or 1))


# -- this turn's history (conditional / instead clauses, wave 1B) --------------------------------------
def initialize_own_turn_history(state: GameState) -> None:
    rules = state.rules
    if rules is not None and state.turn.number == 1:
        rules.own_turn_history_known = list(dict.fromkeys([*rules.own_turn_history_known, *state.players]))


def complete_own_turn(state: GameState) -> None:
    """Idempotent public summary; also called before the impending turn's untap is computed."""
    rules = state.rules
    if rules is None:
        return
    log = rules.turn_log
    player = log.active_player
    if player is None and log.turn == state.turn.number:
        player = log.active_player = state.turn.active_player
    if player is None or log.turn <= 0 or player not in state.players or state.players[player].left:
        return
    objects = list(dict.fromkeys(o for ids in log.attackers.values() for o in ids))
    targets = list(dict.fromkeys(p for o in log.attackers.get(player, ()) for p in log.attacked_who.get(o, ())))
    acted = any(c.player == player for c in log.casts) or any(e.controller == player and not e.token110e for e in log.entered)
    rules.completed_own_turns[player] = CompletedOwnTurn(turn=log.turn, attackers=objects, attacked_players=targets, acted110e=acted)
    if player not in rules.own_turn_history_known:
        rules.own_turn_history_known.append(player)


def turn_log_now(state: GameState) -> TurnLog | None:
    """This turn's log, for writing: a new turn starts a fresh one, and the one just ended is kept
    as ``last_turn_log`` — only if it really was the turn before, so "last turn" never reads an
    older one."""
    rules = state.rules
    if rules is None:
        return None
    initialize_own_turn_history(state)
    n = state.turn.number
    log = rules.turn_log
    if log.turn != n:
        if log.turn == n - 1:
            complete_own_turn(state)
        elif log.turn > 0:
            rules.completed_own_turns.clear()
            rules.own_turn_history_known.clear()
        rules.last_turn_log = log if log.turn == n - 1 else None
        log = rules.turn_log = TurnLog(turn=n, active_player=state.turn.active_player, search_history75_known=True, fight_history90_known=True, combat_damage95_known=True,
                                      starting_life=dict(state.turn.starting_life) if state.turn.starting_life is not None else None)
    elif log.active_player is None:
        log.active_player = state.turn.active_player
    return log


def _note_player_fact(state: GameState, kind: str, player: str | None, amount: int) -> None:
    log = turn_log_now(state)
    if log is None or not player:
        return
    book = {"life_gain": log.gained, "life_loss": log.lost, "drew": log.drew}[kind]
    book[player] = book.get(player, 0) + amount


def note_attack(state: GameState, player: str, attackers: list[str] | None = None, targets: list[str] | None = None) -> None:
    """508.1: ``player`` declared one or more attackers this turn ("if you attacked this turn"); ``attackers``: the
    objects declared (wave 4D: "if you attacked with two or more creatures this turn" — every combat of the turn)."""
    log = turn_log_now(state)
    if log is not None and player not in log.attacked:
        log.attacked.append(player)
    if log is not None and attackers:  # -- this-turn history (wave 4D) --
        seen = log.attackers.setdefault(player, [])
        seen += [a for a in attackers if a not in seen]
        for a in attackers:  # (wave 49B) 508.1: each declaration is one attack
            log.attack_counts[a] = log.attack_counts.get(a, 0) + 1
        if state.rules is not None:  # (wave 38A: this combat phase, 506.1)
            log.declared.update({a: state.rules.combats for a in attackers})
        for a, t in zip(attackers, targets or (), strict=True):  # -- static_other sweep (wave 19A) -- 508.1c: "a player it has already attacked"
            if t in state.players and t not in log.attacked_who.setdefault(a, []):
                log.attacked_who[a].append(t)

    for t in targets or ():  # -- wave 110C -- 506.3: a player, or the controller of a planeswalker attacked (Midnight Crusader Shuttle); a battle's protector is not "you"
        if t in state.players:
            owner: str | None = t
        else:
            from app.rules import battles

            owner = state.cards[t].controller if t in state.cards and battles.protector(state, state.cards[t]) is None else None
        if log is not None and owner is not None and player not in log.attacked_at110c.setdefault(owner, []):
            log.attacked_at110c[owner].append(player)

    if state.rules is not None and state.rules.combat_memory is not None:
        from app.rules import last_combat_receipts44

        last_combat_receipts44.declared(state.rules.combat_memory, player, state.turn.number,
                                       state.rules.combats, attackers or [], targets or [], set(state.players))


def note_block(state: GameState, blockers: list[str], pairs: list[tuple[str, str]] | None = None) -> None:
    """509.1g: these objects were declared as blockers this turn ("creature that blocked this turn"); ``pairs``: (wave 31D) which attacker
    (object) each blocked ("creatures it blocked this turn", "creature that was blocked this turn")."""
    log = turn_log_now(state)
    if log is not None:
        log.blockers += [b for b in blockers if b not in log.blockers]
        if state.rules is not None:
            log.declared_blockers.update({b: state.rules.combats for b in blockers})
        for blocker, attacker in pairs or ():
            seen = log.blocks.setdefault(blocker, [])
            if attacker not in seen:
                seen.append(attacker)
            if state.rules is not None and (att := next((c for c in state.cards.values() if state.rules.object_id(c.id) == attacker), None)) is not None:
                log.block_ctrl110f[f"{blocker}>{attacker}"] = att.controller  # -- wave 110F -- the controller each time it becomes blocked: the last one stays


def wither_put_by(action: Any) -> dict[tuple[str, str], dict[str, int]] | None:
    """-- triggers (wave 17D) -- 120.3d: who puts the -1/-1 counters a damage step gives each creature (its source's controller)."""
    by = getattr(action, "wither_by", None)
    out = {(cid, "-1/-1"): who for cid, who in (by or {}).items()}
    out.update({(pid, "poison"): who for pid, who in getattr(action, "poison_by", {}).items()})
    return out or None


def track(state: GameState, before: Capture | None = None, *, manual: bool = False, actor: str | None = None,
          group: int = 0, put_by: dict[tuple[str, str], dict[str, int]] | None = None, declared: bool = False, non_discard: bool = False) -> None:
    """Deterministic bookkeeping after every applied step (sandbox or rules): whose turn started
    when, when each permanent came under its controller's control, which physical card is which
    rules object, last known information, and the step's events as one simultaneous batch.
    Pure: it reads only the table (and the step's ``emit``s), so replay reproduces it exactly."""
    rules = state.rules
    if rules is None:
        return
    if rules.turn_seen != state.turn.number:
        rules.turn_seen = state.turn.number
        rules.target_activation_history_turn = state.turn.number
        rules.crew_saddle_history_turn80 = state.turn.number
        rules.first_event_history_turn78 = state.turn.number
        rules.turn_started[state.turn.active_player] = state.turn.number
    turn_log_now(state)  # Initialize even empty turns; completed-own-turn summaries must not skip them.
    on_battlefield: set[str] = set()
    for card_id, card in state.cards.items():
        if not card.zone.endswith((":battlefield", ":phased")):
            continue
        on_battlefield.add(card_id)
        mark = rules.controlled_since.get(card_id)
        if mark is None or mark.controller != card.controller:
            rules.controlled_since[card_id] = ControlMark(controller=card.controller, turn=state.turn.number,
                                                          changed=mark is not None)
        elif mark.turn == 0 and mark.observed_from_turn is None:
            mark.observed_from_turn = state.turn.number
    for card_id in [c for c in rules.controlled_since if c not in on_battlefield]:
        del rules.controlled_since[card_id]
    if before is not None:
        _diff(state, rules, before, manual, actor, group, put_by, declared, non_discard)  # (actor: wave 5H, group: wave 7C)
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
    for oid in [o for o, mem in rules.stack_lki.items() if mem.turn < oldest]:
        del rules.stack_lki[oid]


def _entry_order(state: GameState, before: Capture) -> list[tuple[str, str]]:
    """The step's cards in the order they get their new object numbers (613.7d: a timestamp as
    they enter a zone). 613.7m: objects entering the battlefield simultaneously are timestamped in
    APNAP order — the active player's first (among them, in the order the step lists them), then
    each other player's in turn order; everything else keeps the table's order."""
    seats = state.turn_order()
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
# keywords and complete keyword-trigger instances carried out in layers._layer6.
KEYWORD_COUNTERS = frozenset({"flying", "first strike", "double strike", "deathtouch", "haste", "hexproof",
                              "indestructible", "lifelink", "menace", "reach", "shadow", "trample", "vigilance", "exalted", "decayed"})


def _attach_event(state: GameState, kind: EventKind, card_id: str, oid: str, host: str | None, player: str | None,
                  snaps: dict[str, ObjectSnapshot]) -> None:
    """-- attachment events (wave 30S) -- ``card_id`` became attached to / unattached from the permanent ``host`` (its object as it was in
    the step's capture: it may have left too) or the player (the event's ``by_card`` / ``source`` / ``player``)."""
    rules = state.rules
    assert rules is not None
    was = snaps.get(host or "")
    if host:
        current = state.cards.get(host)
        host_oid = was.object_id if kind == 'unattached' and was is not None else rules.object_id(host)
        zone = was.zone if kind == 'unattached' and was is not None else (current.zone if current is not None else "")
        rules.last_attached_hosts[oid] = ObjectRef(card=host, object_id=host_oid, zone=zone)
    emit(state, kind, object_id=oid, card=card_id, by_card=host, player=player,
         source=(was.object_id if was is not None else rules.object_id(host)) if host else None)


def _combat_now(state: GameState, rules: RulesState) -> int:
    """-- graveyard history (wave 36A) -- 506.1: which combat phase of the turn this is (RulesState.combats), 0 outside combat."""
    from app.game.state import COMBAT_PHASES

    return rules.combats if state.turn.phase in COMBAT_PHASES else 0


def _diff(state: GameState, rules: RulesState, before: Capture, manual: bool, actor: str | None = None,
          group: int = 0, put_by: dict[tuple[str, str], dict[str, int]] | None = None, declared: bool = False, non_discard: bool = False) -> None:
    departures = state.departures()
    if state.renames():  # -- review (face-down ids) -- a card renumbered in this step is the same card: follow it
        names = state.renames()
        from app.game.ops import rewrite  # (ops imports this module's state)

        before.zones = {names.get(k, k): v for k, v in before.zones.items()}
        before.snaps = rewrite(dict(before.snaps), names)  # (its last known information too: no old id left in the rules state)
        before.types = {names.get(k, k): v for k, v in before.types.items()}
    for card_id, old_zone in _entry_order(state, before):
        card = state.cards.get(card_id)
        new_zone = card.zone if card is not None else departures.get(card_id)
        if card is not None and new_zone == old_zone:
            continue
        old_name = _zone_name(old_zone)
        new_name = _zone_name(new_zone) if new_zone else None
        if card is not None and old_name == new_name and old_name != "battlefield":
            continue  # e.g. a hand passed between players' libraries is still a library card
        if old_name == "exile" and new_name != "exile":
            rules.suspended = [cid for cid in rules.suspended if cid != card_id]
        if {old_name, new_name} == {"battlefield", "phased"}:
            if new_name == "phased" and card is not None:  # -- phase out (wave 110B) -- "Whenever ~ phases out" (702.26d: no leave trigger, but this one)
                emit(state, "designation", counter="phase_out", card=card_id, object_id=rules.object_id(card_id), player=card.controller)
            continue  # -- phasing (wave 13D) -- 702.26d: phasing is no zone change: same object, no leave / enter triggers
        if old_name == new_name == "battlefield":
            if card is not None:  # -- control events (wave 45C) -- 613.1b, 603.10d: its controller changed (``from_zone``: the player who lost control)
                emit(state, "designation", counter="control", card=card_id, object_id=rules.object_id(card_id), player=card.controller,
                     from_zone=old_zone.split(":")[0])
            continue  # a control change is not a zone change: same object (rule 400.7 doesn't apply)
        old_oid = rules.object_id(card_id)
        if old_name == "stack":  # -- spell copies (wave 31D) -- a spell leaving with its entry still there (returned to hand, exiled …)
            remember_stack(state, card_id, before.stack_info.get(card_id), was_stack=True)
        snap = before.snaps.get(card_id)
        if snap is not None:
            rules.lki[old_oid] = snap.model_copy(update={"turn": state.turn.number})
            rules.lki[old_oid].copy_recipe = copy_recipe_of(rules, old_oid)  # -- copy system (wave 2F) --
            # -- sagas & attached-object triggers (wave 3S): what was attached to it (603.10a) --
            rules.lki[old_oid].attached = [c for c, s in before.snaps.items() if s.attached_to == card_id]
            rules.lki[old_oid].attached_objects = {c: s.object_id for c, s in before.snaps.items() if s.attached_to == card_id}
            rules.lki[old_oid].attached_objects_known = True
        if old_name == 'stack' and new_name == 'battlefield' and snap is not None \
                and (payment := rules.payments.get(old_oid)) is not None:
            payment.resolved_x = snap.x
        new_oid = None
        rules.restamped.pop(card_id, None)  # a new object gets its own timestamp as it enters (613.7d)
        rules.transformed.pop(card_id, None)
        rules.counter_stamps.pop(card_id, None)  # (wave 5H: its counters are gone, 122.2)
        if card is not None:
            rules.next_object += 1
            rules.objects[card_id] = rules.next_object
            new_oid = rules.object_id(card_id)
            if new_name == 'battlefield':
                rules.crafted_materials[new_oid] = []  # New incarnation: known to have no craft materials unless this return supplies them.
                rules.noted_mana[new_oid] = None
            materials = rules.pending_crafts.pop(old_oid, None)
            if materials is not None and old_name == 'exile' and new_name == 'battlefield':
                rules.crafted_materials[new_oid] = materials
            if new_name == "battlefield" and old_name == "stack":  # -- refused grants/replacements (wave 3R2) --
                for rec in rules.replacements:  # 609.7a: a shield on a permanent spell covers the permanent it became
                    oids = ((rec.get("match") or {}).get("source") or {}).get("oids")
                    if isinstance(oids, list) and "becomes:" + old_oid in oids:
                        oids.append(new_oid)
            if new_name == "battlefield":  # 707.5: the copy effect it is entering with is the new object's
                for eff in rules.effects:
                    if eff.layer == "1" and eff.source == ENTERING_COPY + card_id and old_oid in eff.affected:
                        eff.affected.append(new_oid)
            if new_name == "battlefield" and old_name == "stack":  # -- color lace (wave 46B) -- 400.7a: what a spell or ability did to a permanent spell goes on
                for eff in rules.effects:  # applying to the permanent it becomes (a color, a type, a keyword, a control change), for the rest of its duration
                    if old_oid in eff.affected and new_oid not in eff.affected:
                        eff.affected.append(new_oid)
        else:
            rules.objects.pop(card_id, None)
        if old_name == "library" and new_name == "hand" and card is not None and new_oid is not None \
                and any(e.kind == "drew" and e.card == card_id and e.batch > rules.batch for e in rules.events) \
                and (log := turn_log_now(state)) is not None:  # -- drawn this turn (wave 18G) -- the card it drew is this object now
            log.drawn.setdefault(card.owner, []).append(new_oid)
        if old_name in ("library", "hand") and new_name in ("library", "hand", None) and snap is None:
            continue  # private shuffling around: new objects, but nothing public happened
        if old_name == "battlefield":  # -- as long as (wave 35D) -- 400.7: what the old object did or was is no part of the new one
            rules.dealt_damage = [x for x in rules.dealt_damage if x.removesuffix("+combat") != old_oid]
        if old_name == "battlefield" and snap is not None:  # -- conditional / instead clauses (wave 1B) --
            log = turn_log_now(state)
            if log is not None:
                log.left.append(Departure(card=card_id, object_id=old_oid, controller=snap.controller, to=new_name or "", new_object_id105=new_oid if new_name == "graveyard" else None,
                                          types=before.types.get(card_id)))
        elif old_name == "graveyard" and (log := turn_log_now(state)) is not None:
            log.left_graveyard.append(old_zone.split(":")[0])  # (a zone key is "<owner>:graveyard")
            if "Creature" in (before.types.get(card_id) or ()):  # -- (wave 110O) -- Plan.do records the types of a graveyard card it moves
                log.left_graveyard_creature110o.append(old_zone.split(":")[0])
        if old_name == "battlefield" and new_name == "graveyard" and snap is not None and snap.counters and (log := turn_log_now(state)) is not None:
            log.gy_counters110j.extend(k for k, n in snap.counters.items() if n > 0)  # -- (wave 110J) -- "a permanent with an oil counter on it was put into a graveyard"
        if new_name == "graveyard" and new_zone and card is not None and card.card_id is not None \
                and (log := turn_log_now(state)) is not None:  # (a token is no card: it never "descends")
            log.entered_graveyard.append(Arrival(card=card_id, owner=new_zone.split(":")[0], object_id=new_oid, from_zone=old_name,
                                                 combat=_combat_now(state, rules)))  # (-- graveyard history (wave 36A) --)
        if new_name == "battlefield" and card is not None and new_oid is not None \
                and (log := turn_log_now(state)) is not None:  # -- refused modal/conditional (wave 3R1) --
            if not manual:
                rules.entry_life_origins.append(new_oid)
            log.entered.append(Entry(card=card_id, object_id=new_oid, controller=card.controller,
                                     tapped=card.tapped, from_zone=old_zone, face_down110b=bool(card.face_down), token110e=card.is_token))  # (-- entry forms (wave 5F) --; wave 22E: from_zone)
        if old_name == "battlefield" and snap is not None and (snap.attached_to or snap.attached_player):
            _attach_event(state, "unattached", card_id, old_oid, snap.attached_to, snap.attached_player, before.snaps)  # -- attachment events (wave 30S) -- 701.3d
        emit(state, "zone_change", object_id=old_oid, new_object_id=new_oid, card=card_id,
             player=(card.controller if card is not None else snap.controller if snap else None),
             from_zone=old_zone, to_zone=new_zone, actor=actor, non_discard=non_discard)  # (wave 23D: who moved it: a discard an opponent's effect caused, 701.9)
    # -- review (wave 18D) -- 730.3 / 712.21: the cards of a merged permanent that left (other than the one its instance became) were
    # never objects of their own: each is put into the zone from the battlefield, a new object there (not one more permanent leaving)
    pile = {p["id"]: snap for snap in before.snaps.values() for p in snap.merged}
    for card_id, card in state.cards.items():
        if card_id not in before.zones and (_zone_name(card.zone) in TRACKED_ZONES or card_id in pile):
            shell = pile.get(card_id)
            if card_id not in rules.objects or shell is not None:  # a created object is numbered like one that entered (613.7d)
                rules.next_object += 1
                rules.objects[card_id] = rules.next_object
            emit(state, "zone_change", new_object_id=rules.object_id(card_id), card=card_id, player=card.controller,
                 to_zone=card.zone, **({"from_zone": shell.zone} if shell is not None else {}))  # created: a token, a copy, an ability on the stack
            if shell is not None and _zone_name(card.zone) == "graveyard" and (log := turn_log_now(state)) is not None:
                log.entered_graveyard.append(Arrival(card=card_id, owner=card.owner, object_id=rules.object_id(card_id), from_zone="battlefield",
                                                     combat=_combat_now(state, rules)))  # (-- graveyard history (wave 36A) --)
            if _zone_name(card.zone) == "battlefield" and (log := turn_log_now(state)) is not None:  # (wave 3R1)
                if not manual:
                    rules.entry_life_origins.append(rules.object_id(card_id))
                log.entered.append(Entry(card=card_id, object_id=rules.object_id(card_id), controller=card.controller,
                                         tapped=card.tapped, face_down110b=bool(card.face_down), token110e=card.is_token))  # (-- entry forms (wave 5F) --)
    for card_id, snap in before.snaps.items():
        card = state.cards.get(card_id)
        if card is None or card.zone != snap.zone:
            continue
        oid = rules.object_id(card_id)
        for kind in sorted(set(snap.counters) | set(card.counters)):  # (sorted: wave 5H, 613.7c stamps)
            delta = card.counters.get(kind, 0) - snap.counters.get(kind, 0)
            by = (put_by or {}).get((card_id, kind))
            if by and delta > 0 and sum(by.values()) == delta:  # -- triggers (wave 17D) -- 120.3d: each source's controller puts its own
                for pid, n in by.items():
                    emit(state, "counters", object_id=oid, card=card_id, counter=kind, amount=n, actor=pid,
                         counter_remaining=card.counters.get(kind, 0))
            elif delta:
                if delta < 0 and _zone_name(card.zone) == "battlefield" and (log := turn_log_now(state)) is not None:  # -- (wave 110J) --
                    log.counters_removed110j.append(f"{card.controller}:{kind}")
                emit(state, "counters", object_id=oid, card=card_id, counter=kind, amount=delta,
                     counter_remaining=card.counters.get(kind, 0), **({"actor": actor} if actor else {}), **({"group": group} if group else {}))  # (5H, 7C)
            if kind in KEYWORD_COUNTERS:  # -- counters (wave 5H) -- 613.7c
                if card.counters.get(kind, 0) <= 0:
                    rules.counter_stamps.get(card_id, {}).pop(kind, None)
                elif delta > 0:
                    rules.timestamp += 1
                    rules.counter_stamps.setdefault(card_id, {})[kind] = [rules.next_object, rules.timestamp]
        if card.tapped != snap.tapped:
            # -- tap events (wave 45C) -- 701.26a: who tapped it (the step's actor: "whenever you tap …"), and (``combat``) whether it became tapped as it was
            # declared an attacker (508.1f, the declaration's tap step: "if it isn't being declared as an attacker")
            emit(state, "tapped" if card.tapped else "untapped", object_id=oid, card=card_id, actor=actor, combat=declared and card.tapped)
        # -- attachment events (wave 30S) -- 603.2e, 701.3d: it became attached to a (different) object or player, and let go of the one it was
        # attached to (a host that left cleared it, ops.move; an Aura attached to another host lets go of the first)
        if _zone_name(card.zone) == "battlefield" and (card.attached_to, card.attached_player) != (snap.attached_to, snap.attached_player):
            if snap.attached_to or snap.attached_player:
                _attach_event(state, "unattached", card_id, oid, snap.attached_to, snap.attached_player, before.snaps)
            if card.attached_to or card.attached_player:
                _attach_event(state, "attached", card_id, oid, card.attached_to, card.attached_player, before.snaps)
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
            putters = (put_by or {}).get((pid, kind))
            if putters and delta > 0 and sum(putters.values()) == delta:
                for putter, n in putters.items():
                    emit(state, "player_counters", player=pid, counter=kind, amount=n, actor=putter)
            elif delta:
                emit(state, "player_counters", player=pid, counter=kind, amount=delta,
                     **({"actor": actor} if actor and delta > 0 else {}), **({"group": group} if group else {}))
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
