"""Game actions (the only way game state changes).

Every action is a pydantic model discriminated by ``type``. Clients send *intents*: the
server fills ``actor`` from the connection and computes ``r`` (the resolved, deterministic
data such as shuffle orders, dice results and new object ids) in ``resolve.py``. Any
client-supplied ``actor``/``r`` is discarded. Applying a resolved action is deterministic, so
replaying the action list reproduces the game exactly (the basis of undo/redo).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from app.game.state import PHASES, PLAYER_ZONES, STACK, AttackTarget, TokenDef
from app.textutil import clean_text

Id = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9:_\-]+$")]
IdList = Annotated[list[Id], Field(min_length=1, max_length=250)]
ZoneName = Literal[
    "library", "hand", "battlefield", "graveyard", "exile", "command", "sideboard", "companion", "foretell", "stack"
]
Coord = Annotated[float, Field(ge=-100000, le=100000)]
assert set(PLAYER_ZONES) | {STACK} == set(ZoneName.__args__)  # type: ignore[attr-defined]


class ZoneRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player: Id | None = None  # defaults to the card owner / actor where sensible
    zone: ZoneName


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str = ""  # set by the server
    ts: float = 0.0  # set by the server


# --- resolved payloads --------------------------------------------------------------
class ShuffleData(BaseModel):
    perm: list[int]  # new_order[i] = old_order[perm[i]]
    new_ids: list[str]  # fresh ids for the shuffled cards, in new order


class NewIds(BaseModel):
    ids: list[str]


class MoveData(BaseModel):
    positions: dict[str, tuple[float, float]] = Field(default_factory=dict)  # card id -> battlefield x, y
    destinations: dict[str, str] = Field(default_factory=dict)  # card id -> zone key or "delete" (resolve_top)


class DiceData(BaseModel):
    results: list[int]


# --- zone / library actions --------------------------------------------------------
class Draw(Base):
    type: Literal["draw"] = "draw"
    player: Id | None = None
    count: int = Field(default=1, ge=1, le=100)


class Move(Base):
    type: Literal["move"] = "move"
    card_ids: IdList
    to: ZoneRef
    position: Literal["top", "bottom"] | None = None  # for ordered zones; default: top (library: top)
    index: int | None = Field(default=None, ge=0, le=10000)  # explicit position (library: from top)
    x: Coord | None = None
    y: Coord | None = None
    face_down: bool | None = None
    r: MoveData | None = None


class SetPosition(Base):
    type: Literal["set_position"] = "set_position"
    moves: list[tuple[Id, Coord, Coord]] = Field(min_length=1, max_length=250)


class Shuffle(Base):
    type: Literal["shuffle"] = "shuffle"
    player: Id | None = None
    zone: Literal["library", "hand", "graveyard", "exile"] = "library"
    r: ShuffleData | None = None


class Mill(Base):
    type: Literal["mill"] = "mill"
    player: Id | None = None
    count: int = Field(default=1, ge=1, le=500)
    to: Literal["graveyard", "exile"] = "graveyard"
    face_down: bool = False


class Mulligan(Base):
    type: Literal["mulligan"] = "mulligan"
    player: Id | None = None
    draw: int = Field(default=7, ge=0, le=20)
    r: ShuffleData | None = None


class Reveal(Base):
    type: Literal["reveal"] = "reveal"
    card_ids: IdList
    to: list[Id] | None = None  # None = everyone


class Hide(Base):
    type: Literal["hide"] = "hide"
    card_ids: IdList


class LookTop(Base):
    """Actor privately looks at the top N cards of a library."""

    type: Literal["look_top"] = "look_top"
    player: Id | None = None
    count: int = Field(default=1, ge=1, le=100)


class RevealTop(Base):
    type: Literal["reveal_top"] = "reveal_top"
    player: Id | None = None
    count: int = Field(default=1, ge=1, le=100)


class SearchStart(Base):
    type: Literal["search_start"] = "search_start"
    zone: ZoneRef


class SearchEnd(Base):
    type: Literal["search_end"] = "search_end"
    shuffle: bool = False
    r: ShuffleData | None = None


# --- card state ---------------------------------------------------------------------
class Tap(Base):
    type: Literal["tap"] = "tap"
    card_ids: IdList
    tapped: bool | None = None  # None = toggle each


class UntapAll(Base):
    type: Literal["untap_all"] = "untap_all"
    player: Id | None = None


class Counter(Base):
    type: Literal["counter"] = "counter"
    card_ids: IdList
    kind: str = Field(min_length=1, max_length=40)
    delta: int = Field(default=1, ge=-1000, le=1000)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        return clean_text(v, 40)


class SetCounter(Base):
    type: Literal["set_counter"] = "set_counter"
    card_id: Id
    kind: str = Field(min_length=1, max_length=40)
    value: int = Field(ge=0, le=100000)
    rename_from: str | None = Field(default=None, max_length=40)  # change counter type

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        return clean_text(v, 40)


class TokenSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_id: Id | None = None  # database token/card printing
    name: str = Field(default="Token", max_length=80)
    power: str | None = Field(default=None, max_length=8)
    toughness: str | None = Field(default=None, max_length=8)
    colors: list[Literal["W", "U", "B", "R", "G"]] = Field(default_factory=list)
    type_line: str = Field(default="Token Creature", max_length=120)
    text: str = Field(default="", max_length=1000)

    @field_validator("name", "type_line")
    @classmethod
    def _clean(cls, v: str) -> str:
        return clean_text(v, 120)

    @field_validator("text")
    @classmethod
    def _clean_text(cls, v: str) -> str:
        return clean_text(v, 1000, multiline=True)


class CreateToken(Base):
    type: Literal["create_token"] = "create_token"
    player: Id | None = None  # controller
    token: TokenSpec
    count: int = Field(default=1, ge=1, le=100)
    x: Coord | None = None
    y: Coord | None = None
    tapped: bool = False
    r: NewIds | None = None
    # filled by resolve from the card DB when token.card_id is given:
    resolved_token: TokenDef | None = None


class CopyCard(Base):
    type: Literal["copy_card"] = "copy_card"
    card_id: Id
    player: Id | None = None  # controller of the copy (default: actor)
    count: int = Field(default=1, ge=1, le=50)
    modifications: str = Field(default="", max_length=300)
    x: Coord | None = None
    y: Coord | None = None
    r: NewIds | None = None


class DeleteCard(Base):
    """Remove tokens, copies and ability objects from the game."""

    type: Literal["delete_card"] = "delete_card"
    card_ids: IdList


class SetFace(Base):
    type: Literal["set_face"] = "set_face"
    card_id: Id
    face: int | None = Field(default=None, ge=0, le=3)  # None = next face
    faces: int = Field(default=2, ge=1, le=4)  # number of faces (from the card DB, set by resolve)


class Flip(Base):
    """Rotate 180° (Kamigawa flip cards)."""

    type: Literal["flip"] = "flip"
    card_id: Id


class FaceDown(Base):
    type: Literal["face_down"] = "face_down"
    card_ids: IdList
    face_down: bool | None = None  # None = toggle


class Note(Base):
    type: Literal["note"] = "note"
    card_id: Id
    text: str = Field(default="", max_length=500)

    @field_validator("text")
    @classmethod
    def _clean(cls, v: str) -> str:
        return clean_text(v, 500, multiline=True)


class SetController(Base):
    type: Literal["set_controller"] = "set_controller"
    card_ids: IdList
    player: Id


class SetCommander(Base):
    type: Literal["set_commander"] = "set_commander"
    card_id: Id
    value: bool = True


# --- players / table -------------------------------------------------------------------
class Life(Base):
    type: Literal["life"] = "life"
    player: Id | None = None
    delta: int = Field(ge=-100000, le=100000)


class SetLife(Base):
    type: Literal["set_life"] = "set_life"
    player: Id | None = None
    value: int = Field(ge=-100000, le=100000)


class Resource(Base):
    type: Literal["resource"] = "resource"
    player: Id | None = None
    key: str = Field(min_length=1, max_length=30)
    delta: int = Field(default=1, ge=-100000, le=100000)

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        return clean_text(v, 30).lower()


class SetResource(Base):
    type: Literal["set_resource"] = "set_resource"
    player: Id | None = None
    key: str = Field(min_length=1, max_length=30)
    value: int | None = Field(default=None, ge=-100000, le=100000)  # None removes a custom resource

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        return clean_text(v, 30).lower()


class CommanderDamage(Base):
    type: Literal["commander_damage"] = "commander_damage"
    player: Id  # player taking the damage
    commander: Id  # commander_key
    delta: int = Field(ge=-1000, le=1000)
    affect_life: bool = True


class CommanderTax(Base):
    type: Literal["commander_tax"] = "commander_tax"
    commander: Id  # commander_key
    delta: int | None = Field(default=None, ge=-100, le=100)
    value: int | None = Field(default=None, ge=0, le=1000)


class SetMonarch(Base):
    type: Literal["set_monarch"] = "set_monarch"
    player: Id | None = None


class SetInitiative(Base):
    type: Literal["set_initiative"] = "set_initiative"
    player: Id | None = None


class SetDayNight(Base):
    type: Literal["set_day_night"] = "set_day_night"
    value: Literal["day", "night"] | None = None


class CityBlessing(Base):
    type: Literal["city_blessing"] = "city_blessing"
    player: Id | None = None
    value: bool = True


class RenamePlayer(Base):
    type: Literal["rename_player"] = "rename_player"
    player: Id | None = None
    name: str = Field(min_length=1, max_length=40)

    @field_validator("name")
    @classmethod
    def _clean(cls, v: str) -> str:
        cleaned = clean_text(v, 40)
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned


class Roll(Base):
    type: Literal["roll"] = "roll"
    sides: int = Field(default=20, ge=2, le=1000)
    count: int = Field(default=1, ge=1, le=100)
    r: DiceData | None = None


class Coin(Base):
    type: Literal["coin"] = "coin"
    count: int = Field(default=1, ge=1, le=100)
    r: DiceData | None = None


class Chat(Base):
    type: Literal["chat"] = "chat"
    text: str = Field(min_length=1, max_length=500)

    @field_validator("text")
    @classmethod
    def _clean(cls, v: str) -> str:
        return clean_text(v, 500)


# --- turn / combat / stack -----------------------------------------------------------
class Phase(Base):
    type: Literal["phase"] = "phase"
    to: Literal["next", "prev"] | str = "next"

    @field_validator("to")
    @classmethod
    def _valid(cls, v: str) -> str:
        if v not in ("next", "prev") and v not in PHASES:
            raise ValueError(f"unknown phase {v!r}")
        return v


class NextTurn(Base):
    type: Literal["next_turn"] = "next_turn"
    player: Id | None = None  # explicit next active player (default: next in seat order)


class Attack(Base):
    type: Literal["attack"] = "attack"
    card_ids: IdList
    target: AttackTarget | None = None  # None = stop attacking


class Block(Base):
    type: Literal["block"] = "block"
    card_id: Id
    attacker_id: Id | None = None  # None = stop blocking


class ClearCombat(Base):
    type: Literal["clear_combat"] = "clear_combat"


class CreateAbility(Base):
    type: Literal["create_ability"] = "create_ability"
    text: str = Field(min_length=1, max_length=500)
    source_id: Id | None = None
    kind: Literal["activated", "triggered", "other"] = "other"
    r: NewIds | None = None

    @field_validator("text")
    @classmethod
    def _clean(cls, v: str) -> str:
        return clean_text(v, 500, multiline=True)


class ResolveTop(Base):
    type: Literal["resolve_top"] = "resolve_top"
    r: MoveData | None = None


Action = Annotated[
    Draw
    | Move
    | SetPosition
    | Shuffle
    | Mill
    | Mulligan
    | Reveal
    | Hide
    | LookTop
    | RevealTop
    | SearchStart
    | SearchEnd
    | Tap
    | UntapAll
    | Counter
    | SetCounter
    | CreateToken
    | CopyCard
    | DeleteCard
    | SetFace
    | Flip
    | FaceDown
    | Note
    | SetController
    | SetCommander
    | Life
    | SetLife
    | Resource
    | SetResource
    | CommanderDamage
    | CommanderTax
    | SetMonarch
    | SetInitiative
    | SetDayNight
    | CityBlessing
    | RenamePlayer
    | Roll
    | Coin
    | Chat
    | Phase
    | NextTurn
    | Attack
    | Block
    | ClearCombat
    | CreateAbility
    | ResolveTop,
    Field(discriminator="type"),
]

ACTION_ADAPTER: TypeAdapter[Action] = TypeAdapter(Action)


def parse_action(data: object) -> Action:
    """Validate an untrusted action payload. Raises ``pydantic.ValidationError``."""
    return ACTION_ADAPTER.validate_python(data)
