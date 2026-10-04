"""Game state: a normalized, JSON-serializable description of the whole table.

Zones hold ordered lists of card-instance ids; the instances themselves live in
``GameState.cards``. Conventions:

* Zone keys are ``"<player_id>:<zone>"`` for per-player zones and ``"stack"``.
* Library index 0 is the **top** card. For every other ordered zone the **last** element is
  the top/newest (graveyard top, top of the stack, front-most battlefield card).
* Battlefield placement *is* control: a card in ``p2:battlefield`` is controlled by p2.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr

from app.game.rules_state import AutomationLevel, AutomationOptions, RulesState

ALL = "*"  # marker in ``revealed_to`` meaning "every player"

PLAYER_ZONES = (
    "library", "hand", "battlefield", "graveyard", "exile", "command", "sideboard", "companion", "foretell", "setaside", "phased"
)
# "phased": phased-out permanents (702.26b, wave 13D) stay on the battlefield for the rules (no zone change, 702.26d) but sit in
# this controller-keyed zone so every battlefield query skips them; public like the battlefield.
PUBLIC_ZONES = frozenset({"battlefield", "phased", "graveyard", "exile", "command", "companion", "stack"})
# "setaside": cards put aside face down during the pregame (e.g. rejected mulligan hands), owner-only.
HIDDEN_ZONES = frozenset({"library", "hand", "sideboard", "foretell", "setaside"})
OWNER_VISIBLE_ZONES = frozenset({"hand", "sideboard", "foretell", "setaside"})
STACK = "stack"

PHASES = (
    "untap",
    "upkeep",
    "draw",
    "main1",
    "begin_combat",
    "declare_attackers",
    "declare_blockers",
    "combat_damage",
    "end_combat",
    "main2",
    "end",
    "cleanup",
)
COMBAT_PHASES = frozenset({"begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat"})

DEFAULT_RESOURCES = ("poison", "energy", "experience")

BATTLEFIELD_W = 1000.0
BATTLEFIELD_H = 600.0


def zone_key(player_id: str | None, zone: str) -> str:
    if zone == STACK:
        return STACK
    if player_id is None:
        raise ValueError(f"zone {zone!r} needs a player")
    return f"{player_id}:{zone}"


def split_zone(key: str) -> tuple[str | None, str]:
    if key == STACK:
        return None, STACK
    owner, _, zone = key.partition(":")
    return owner, zone


class TokenDef(BaseModel):
    """What a token is. ``card_id`` points at a database token when one was used."""

    name: str
    card_id: str | None = None
    power: str | None = None
    toughness: str | None = None
    colors: list[str] = Field(default_factory=list)
    type_line: str = "Token Creature"
    text: str = ""
    # -- keyword actions & face-down (wave 3F) -- a double-faced token's back face (111.10i: the Incubator's
    # "Phyrexian Token"); ``CardInstance.face`` 1 means it's transformed (701.27)
    back: TokenDef | None = None


class Effect(BaseModel):
    """A temporary effect marker on a card (+3/+3, Flying, Protection from red …).
    Players add and remove them; nothing expires on its own."""

    id: str
    name: str
    value: str | None = None  # e.g. "+3/+3", "2"
    text: str | None = None
    color: str | None = None  # "#rrggbb"


class StackInfo(BaseModel):
    """Annotations on a spell/ability on the stack: X, chosen modes, how it was cast."""

    x: int | None = None
    modes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)  # Kicked, Flashback, Cast from exile …


class TokenSource(BaseModel):
    source_id: str | None = None
    name: str


class Arrow(BaseModel):
    """A visual relationship everyone sees: targeting, attack, block or anything custom."""

    id: str
    owner: str
    source: str  # card id or player id
    targets: list[str]  # card ids and/or player ids
    kind: Literal["target", "attack", "block", "custom"] = "target"
    label: str = ""


class CopyInfo(BaseModel):
    source_id: str  # instance copied (may no longer exist)
    source_name: str
    modifications: str = ""


class AbilityDef(BaseModel):
    """A temporary stack object representing an activated/triggered ability."""

    text: str
    source_id: str | None = None
    source_card_id: str | None = None
    source_name: str | None = None
    kind: Literal["activated", "triggered", "other"] = "other"


class AttackTarget(BaseModel):
    kind: Literal["player", "card"]
    id: str


class CardInstance(BaseModel):
    id: str
    card_id: str | None = None  # printing id in the card DB; None for custom tokens / abilities
    name: str = ""  # cached display name (the engine has no DB access)
    owner: str
    controller: str
    zone: str
    x: float = 0.0
    y: float = 0.0
    tapped: bool = False
    face_down: bool = False
    # How it got face down (public: everyone saw it happen). Its identity stays with the controller.
    face_down_kind: Literal["generic", "morph", "disguise", "manifest", "cloak", "exile"] | None = None
    # -- hidden exile (wave 18A) -- 708.2a: what the effect that turned it face down made it ("2/2 Cyberman artifact creature"); public
    face_down_as: str | None = None
    # -- hidden exile (wave 18A) -- exiled face down by an effect that nobody looked at (406.3a): not even its controller may look
    # at it until an effect lets them (``revealed_to``); ends when it changes zones
    unseen: bool = False
    face: int = 0  # displayed face for DFC / adventure / split cards
    flipped: bool = False  # rotated 180° (Kamigawa flip cards)
    counters: dict[str, int] = Field(default_factory=dict)
    note: str = ""
    is_token: bool = False
    token: TokenDef | None = None
    copy_of: CopyInfo | None = None
    ability: AbilityDef | None = None
    commander_key: str | None = None
    categories: list[str] = Field(default_factory=list)  # deck-builder categories; only ever shown to the owner
    # Active reveal: who may currently see this card although its zone hides it ([ALL] = everyone).
    # Reveals are temporary: they end on "stop revealing", when the card changes zones, or on shuffle.
    # There is deliberately no memory of who saw a card earlier (see docs/SECURITY.md).
    revealed_to: list[str] = Field(default_factory=list)
    attacking: AttackTarget | None = None
    blocking: str | None = None  # attacker instance id
    blocking_more: list[str] = Field(default_factory=list)  # -- multiple blocks (wave 13B) -- 509.1a: the other attackers it blocks

    def blocks(self, attacker_id: str) -> bool:
        return self.blocking == attacker_id or attacker_id in self.blocking_more

    def unblock(self, attacker_id: str | None = None) -> None:
        """Stop blocking ``attacker_id`` (506.4: it left combat), or everything (None)."""
        rest = [] if attacker_id is None else [x for x in (self.blocking, *self.blocking_more) if x and x != attacker_id]
        self.blocking, self.blocking_more = (rest[0] if rest else None), rest[1:]
    # --- tabletop object behaviour (see docs/3D_DIRECTION.md §5) ---
    rotation: float = 0.0  # free rotation in degrees, independent of tapping
    locked: bool = False  # cannot be moved until unlocked
    protected: bool = False  # cannot be deleted / stacked / merged without an explicit force
    phased_indirect: bool = False  # -- phasing (wave 13D) -- 702.26g: phased out with its host; phases in only along with it
    attached_to: str | None = None  # host permanent (equipment, auras, cards tucked under)
    attached_player: str | None = None  # the player an Aura enchants ("Enchant player", 702.5d)
    attach_offset: tuple[float, float] | None = None  # position relative to the host
    group: str | None = None  # temporary pile: dragging one member moves all
    quantity: int = 1  # logical token stack size ("Treasure ×17")
    # --- manual tracking (nothing here is enforced or expires on its own) ---
    effects: list[Effect] = Field(default_factory=list)
    damage: int = 0
    choices: dict[str, str] = Field(default_factory=dict)  # "Chosen color" -> "Blue", "Named card" -> …
    stack_info: StackInfo | None = None
    exile_group: str | None = None  # "Prosper", "Oblivion Ring", "Foretell" … (organisational label)
    token_source: TokenSource | None = None
    # --- solo testing ---
    origin: Literal["library", "command", "sideboard", "companion"] = "library"  # where Reset deck puts it back
    test_object: bool = False  # spawned for testing: never part of the deck, removed by Reset deck


class LifeChange(BaseModel):
    turn: int
    before: int
    after: int
    seq: int = 0  # action number that last touched this entry


class PlayerState(BaseModel):
    id: str
    name: str
    color: str = "#d4a852"
    life: int = 40
    life_history: list[LifeChange] = Field(default_factory=list)
    resources: dict[str, int] = Field(default_factory=lambda: {k: 0 for k in DEFAULT_RESOURCES})
    commander_damage: dict[str, int] = Field(default_factory=dict)  # commander_key -> damage taken
    commander_tax: dict[str, int] = Field(default_factory=dict)  # own commander_key -> tax
    commander_casts: dict[str, int] = Field(default_factory=dict)  # own commander_key -> casts from the command zone
    city_blessing: bool = False
    mulligans: int = 0
    deck_id: str | None = None
    deck_name: str | None = None
    token_shortcuts: list[str] = Field(default_factory=list)  # card ids from the deck's Tokens section
    mana: dict[str, int] = Field(default_factory=dict)  # temporary mana pool: W U B R G C (and S for snow)
    left: bool = False  # removed from the table by the host (kept for names in the log)
    # Appearance (visual only; card identity stays server-controlled). Ids of managed assets.
    sleeve: str | None = Field(default=None, max_length=32, pattern=r"^[0-9a-f]{8,32}$")
    playmat: Playmat | None = None


class TurnState(BaseModel):
    number: int = 1
    active_player: str
    phase: str = "untap"


class Playmat(BaseModel):
    """A custom playmat image and how it sits on the table (non-destructive transforms)."""

    asset_id: str = Field(max_length=32, pattern=r"^[0-9a-f]{8,32}$")
    fit: Literal["cover", "contain", "stretch"] = "cover"
    scale: float = Field(default=1.0, ge=0.25, le=4.0)
    offset_x: float = Field(default=0.0, ge=-100.0, le=100.0)  # percent of the area
    offset_y: float = Field(default=0.0, ge=-100.0, le=100.0)
    rotation: Literal[0, 90, 180, 270] = 0
    opacity: float = Field(default=1.0, ge=0.1, le=1.0)
    show_zones: bool = True  # draw zone outlines/labels over the image


class TableState(BaseModel):
    monarch: str | None = None
    initiative: str | None = None
    day_night: Literal["day", "night"] | None = None
    playmat: Playmat | None = None  # one mat under the whole table (host)


class ViewContext(BaseModel):
    """A temporary private view: a library search, or looking at the top N cards.

    While open, ``viewer`` sees the listed cards (or the whole zone for a search) as long as
    they stay in ``zone``. Closing the view or shuffling the zone ends it.
    """

    id: str
    viewer: str
    zone: str
    kind: Literal["search", "look"]
    card_ids: list[str] = Field(default_factory=list)  # for "look": the cards being looked at


class MulliganPolicy(BaseModel):
    """How opening hands work at this table. See docs/MULLIGAN_RULES.md.

    Every field is explicit data, so a pod's house rule is configured, never guessed.
    """

    id: str = Field(default="london", max_length=40)
    display_name: str = Field(default="London", max_length=60)
    starting_hand_size: int = Field(default=7, ge=0, le=20)
    free_mulligans: int = Field(default=0, ge=0, le=10)  # mulligans that don't count toward cards to bottom
    draw_count: int = Field(default=7, ge=0, le=20)  # cards drawn for each new hand
    shuffle_between_mulligans: bool = True
    cards_to_bottom: int = Field(default=1, ge=0, le=10)  # per counted mulligan, chosen when keeping
    partial_hand_selection: bool = False  # choose which cards of the hand to send back (and draw that many)
    set_aside_rejected_hands: bool = False  # rejected cards go to a private set-aside zone, not the library
    final_shuffle: bool = False  # after keeping, set-aside cards are shuffled into the library
    minimum_hand_size: int = Field(default=0, ge=0, le=20)  # no mulligan may leave a smaller kept hand
    max_mulligans: int | None = Field(default=None, ge=0, le=20)
    needs_definition: bool = False  # a named slot (e.g. a pod's house rule) whose rules aren't filled in yet


class PregameSeat(BaseModel):
    status: Literal["deciding", "bottoming", "kept"] = "deciding"
    mulligans: int = 0
    to_bottom: int = 0  # while bottoming: exactly how many cards must go to the bottom
    kept: int | None = None  # final hand size


class Pregame(BaseModel):
    """Simultaneous opening-hand decisions. The game proper starts when everyone has kept."""

    seats: dict[str, PregameSeat] = Field(default_factory=dict)
    finished: bool = False


class ResponseWindow(BaseModel):
    """"Anything in response?" — a public, non-blocking check around the stack and phase changes.

    It never locks the table: the opener can proceed anyway and the host can force it closed.
    """

    id: str
    kind: Literal["stack", "resolve", "phase", "turn"]
    opener: str
    text: str
    waiting: list[str] = Field(default_factory=list)  # players who haven't passed yet
    passed: list[str] = Field(default_factory=list)
    responder: str | None = None  # someone pressed RESPOND and is about to act
    intent: dict[str, Any] | None = None  # resolved action applied when everyone has passed


class GameSettings(BaseModel):
    starting_life: int = 40
    auto_untap: bool = True  # "next turn" untaps the new active player's permanents
    auto_commander_tax: bool = True  # moving a commander from the command zone to the stack adds {2}
    clear_mana_on_step: bool = False  # optional: empty mana pools when the step/phase changes
    auto_clear_combat: bool = False  # optional: leaving combat / next turn clears combat markers
    allow_test_objects: bool = False  # Spawn card (solo tables allow it; the host can enable it on LAN)
    undo_policy: Literal["everyone", "own", "host"] = "everyone"
    # What opponents learn about a player's deck: nothing, the commander(s) and deck name, or the list.
    deck_privacy: Literal["private", "commander_only", "public"] = "commander_only"
    priority_helper: Literal["off", "simple"] = "off"
    # Rules automation (docs/AUTOMATION_UX.md): OFF is the sandbox (players decide everything),
    # ASSISTED prepares and asks, FULL automates like a digital card game. The sandbox tools stay
    # available at every level. Options start as the level's preset; any change makes it CUSTOM.
    automation: AutomationLevel = "off"
    automation_options: AutomationOptions = Field(default_factory=AutomationOptions)
    mulligan: MulliganPolicy | None = None  # None: mulligans are done by hand (sandbox)


class LogPart(BaseModel):
    """Text, a card reference, or a group of card references; rendered per viewer.

    A card reference shows its name only to viewers listed in ``visible_to`` (or everyone
    when it contains ``ALL``); other viewers see "a card".
    """

    t: str | None = None
    card_id: str | None = None  # printing id (for hover preview)
    name: str | None = None
    visible_to: list[str] = Field(default_factory=list)
    group: list[LogPart] | None = None  # rendered as "Sol Ring, Island and 2 cards"


class LogEntry(BaseModel):
    seq: int
    ts: float
    turn: int
    phase: str
    actor: str | None
    parts: list[LogPart]
    kind: str = "action"
    manual: bool = False  # a sandbox action taken while rules automation was on
    folded: bool = False  # shown collapsed under the following summary line (a repeated sequence)


class GameState(BaseModel):
    format_version: int = 1
    id: str
    name: str
    format: Literal["commander", "constructed", "sandbox"] = "commander"
    created_at: float
    seq: int = 0  # number of actions applied (== history position)
    settings: GameSettings = Field(default_factory=GameSettings)
    players: dict[str, PlayerState]
    seat_order: list[str]
    cards: dict[str, CardInstance] = Field(default_factory=dict)
    zones: dict[str, list[str]] = Field(default_factory=dict)
    turn: TurnState
    table: TableState = Field(default_factory=TableState)
    views: list[ViewContext] = Field(default_factory=list)
    # Secret per-game key that orders anonymous hidden cards in opponents' views; never sent to clients.
    hidden_salt: str = ""
    pregame: Pregame | None = None
    arrows: list[Arrow] = Field(default_factory=list)
    response: ResponseWindow | None = None
    auto_pass: dict[str, int] = Field(default_factory=dict)  # player -> turn number they auto-pass through
    passed_at: int | None = None  # seq at which everyone last passed (no need to ask again)
    log: list[LogEntry] = Field(default_factory=list)
    rules: RulesState | None = None  # rules bookkeeping; kept (dormant) when automation is turned off
    # Where cards that ceased to exist during the step being applied were headed (a token "dies":
    # it goes to the graveyard, then ceases to exist). In memory only; read by rules tracking.
    _departed: dict[str, str] = PrivateAttr(default_factory=dict)

    def departures(self) -> dict[str, str]:
        return self._departed

    # -- helpers ---------------------------------------------------------------------
    def zone(self, key: str) -> list[str]:
        return self.zones.setdefault(key, [])

    def player_ids(self) -> list[str]:
        return list(self.seat_order)

    def searching(self, viewer: str) -> str | None:
        """Zone key ``viewer`` is currently searching, if any."""
        return next((v.zone for v in self.views if v.viewer == viewer and v.kind == "search"), None)

    def commander_name(self, key: str) -> str:
        for card in self.cards.values():
            if card.commander_key == key:
                return card.name
        return key
