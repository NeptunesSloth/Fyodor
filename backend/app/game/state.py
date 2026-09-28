"""Game state: a normalized, JSON-serializable description of the whole table.

Zones hold ordered lists of card-instance ids; the instances themselves live in
``GameState.cards``. Conventions:

* Zone keys are ``"<player_id>:<zone>"`` for per-player zones and ``"stack"``.
* Library index 0 is the **top** card. For every other ordered zone the **last** element is
  the top/newest (graveyard top, top of the stack, front-most battlefield card).
* Battlefield placement *is* control: a card in ``p2:battlefield`` is controlled by p2.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ALL = "*"  # marker in ``revealed_to`` meaning "every player"

PLAYER_ZONES = ("library", "hand", "battlefield", "graveyard", "exile", "command", "sideboard", "companion", "foretell")
PUBLIC_ZONES = frozenset({"battlefield", "graveyard", "exile", "command", "companion", "stack"})
HIDDEN_ZONES = frozenset({"library", "hand", "sideboard", "foretell"})
OWNER_VISIBLE_ZONES = frozenset({"hand", "sideboard", "foretell"})
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
    # --- tabletop object behaviour (see docs/3D_DIRECTION.md §5) ---
    rotation: float = 0.0  # free rotation in degrees, independent of tapping
    locked: bool = False  # cannot be moved until unlocked
    protected: bool = False  # cannot be deleted / stacked / merged without an explicit force
    attached_to: str | None = None  # host permanent (equipment, auras, cards tucked under)
    attach_offset: tuple[float, float] | None = None  # position relative to the host
    group: str | None = None  # temporary pile: dragging one member moves all
    quantity: int = 1  # logical token stack size ("Treasure ×17")


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
    city_blessing: bool = False
    mulligans: int = 0
    deck_id: str | None = None
    deck_name: str | None = None
    token_shortcuts: list[str] = Field(default_factory=list)  # card ids from the deck's Tokens section
    mana: dict[str, int] = Field(default_factory=dict)  # temporary mana pool: W U B R G C (and S for snow)


class TurnState(BaseModel):
    number: int = 1
    active_player: str
    phase: str = "untap"


class TableState(BaseModel):
    monarch: str | None = None
    initiative: str | None = None
    day_night: Literal["day", "night"] | None = None


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


class GameSettings(BaseModel):
    starting_life: int = 40
    auto_untap: bool = True  # "next turn" untaps the new active player's permanents
    auto_commander_tax: bool = True  # moving a commander from the command zone to the stack adds {2}
    clear_mana_on_step: bool = True  # empty mana pools when the step/phase changes
    undo_policy: Literal["everyone", "own", "host"] = "everyone"


REMINDER_TIMES = ("upkeep", "draw", "main1", "begin_combat", "end", "cleanup", "next_turn")


class Reminder(BaseModel):
    id: str
    owner: str
    text: str
    when: Literal["upkeep", "draw", "main1", "begin_combat", "end", "cleanup", "next_turn"]
    own_turn_only: bool = True  # "at the beginning of *your* next upkeep"
    card_id: str | None = None
    created_seq: int = 0
    due: bool = False  # the step has been reached; shown until dismissed


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
    reminders: list[Reminder] = Field(default_factory=list)
    log: list[LogEntry] = Field(default_factory=list)

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
