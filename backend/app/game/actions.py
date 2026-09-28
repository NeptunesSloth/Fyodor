"""Game actions (the only way game state changes).

Every action is a pydantic model discriminated by ``type``. Clients send *intents*: the
server fills ``actor`` from the connection and computes ``r`` (the resolved, deterministic
data such as shuffle orders, dice results and new object ids) in ``resolve.py``. Any
client-supplied ``actor``/``r`` is discarded. Applying a resolved action is deterministic, so
replaying the action list reproduces the game exactly (the basis of undo/redo).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from app.game.state import PHASES, PLAYER_ZONES, STACK, AttackTarget, TokenDef
from app.textutil import clean_text

Id = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9:_\-]+$")]
IdList = Annotated[list[Id], Field(min_length=1, max_length=250)]
ZoneName = Literal[
    "library", "hand", "battlefield", "graveyard", "exile", "command", "sideboard", "companion", "foretell", "setaside",
    "stack",
]
Coord = Annotated[float, Field(ge=-100000, le=100000)]
FaceDownKind = Literal["generic", "morph", "disguise", "manifest", "cloak", "exile"]
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
    face_down_kind: FaceDownKind | None = None  # morph / disguise / manifest / cloak …
    r: MoveData | None = None


class SetPosition(Base):
    type: Literal["set_position"] = "set_position"
    moves: list[tuple[Id, Coord, Coord]] = Field(min_length=1, max_length=250)
    with_attachments: bool = True  # attached cards follow their host (hold a modifier to move only the host)


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


class PutTopFaceDown(Base):
    """Manifest / cloak: the top N cards of a library onto the battlefield face down."""

    type: Literal["put_top_face_down"] = "put_top_face_down"
    player: Id | None = None  # whose library (default: yours); they enter under your control
    count: int = Field(default=1, ge=1, le=20)
    kind: Literal["manifest", "cloak", "generic"] = "manifest"
    r: MoveData | None = None


class MulliganTake(Base):
    """Pregame: reject the current hand and draw a new one under the table's mulligan policy."""

    type: Literal["mulligan_take"] = "mulligan_take"
    player: Id | None = None
    card_ids: list[Id] | None = Field(default=None, max_length=20)  # partial mulligan (if the policy allows it)
    r: ShuffleData | None = None


class MulliganKeep(Base):
    type: Literal["mulligan_keep"] = "mulligan_keep"
    player: Id | None = None
    r: ShuffleData | None = None  # final shuffle of set-aside cards (if the policy asks for one)


class MulliganBottom(Base):
    """Put exactly the required number of cards from the kept hand on the bottom, in this order."""

    type: Literal["mulligan_bottom"] = "mulligan_bottom"
    player: Id | None = None
    card_ids: Annotated[list[Id], Field(min_length=1, max_length=20)]
    r: ShuffleData | None = None


class MulliganFinish(Base):
    """Host override: end the opening-hand phase now (undecided players keep what they hold)."""

    type: Literal["mulligan_finish"] = "mulligan_finish"


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


class EndView(Base):
    """Stop looking at privately viewed cards (e.g. after "look at the top N")."""

    type: Literal["end_view"] = "end_view"
    zone: Literal["library", "hand", "graveyard", "exile", "sideboard", "foretell"] | None = None


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
    stacked: bool | None = None  # one logical stack instead of N objects (default: when count > 3)
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
    force: bool = False  # required for protected objects


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
    kind: FaceDownKind | None = None  # when turning face down


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


class ReturnToOwner(Base):
    """Give cards back to their owner: stolen permanents to the owner's battlefield, cards in
    another player's zone to the owner's zone of the same kind."""

    type: Literal["return_to_owner"] = "return_to_owner"
    card_ids: IdList


class RemovePlayer(Base):
    """Host tool: someone left the table. Their cards leave the game; permanents they controlled
    but don't own go back to their owners."""

    type: Literal["remove_player"] = "remove_player"
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
    force: bool = False  # skip the response check (proceed anyway)

    @field_validator("to")
    @classmethod
    def _valid(cls, v: str) -> str:
        if v not in ("next", "prev") and v not in PHASES:
            raise ValueError(f"unknown phase {v!r}")
        return v


class NextTurn(Base):
    type: Literal["next_turn"] = "next_turn"
    player: Id | None = None  # explicit next active player (default: next in seat order)
    force: bool = False


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
    force: bool = False


# --- response helper -----------------------------------------------------------------
class ResponseOpen(Base):
    """Created by the server (never accepted from clients): ask the table before ``intent``."""

    type: Literal["response_open"] = "response_open"
    kind: Literal["resolve", "phase", "turn"]
    text: str = Field(max_length=300)
    intent: dict[str, Any]


class ResponsePass(Base):
    type: Literal["response_pass"] = "response_pass"


class ResponseRespond(Base):
    type: Literal["response_respond"] = "response_respond"


class ResponseAutoPass(Base):
    """Pass every response check until the end of this turn (or stop doing so)."""

    type: Literal["response_auto"] = "response_auto"
    on: bool = True


class ResponseClose(Base):
    """The opener proceeds anyway / withdraws, or the host forces the window shut (API-checked)."""

    type: Literal["response_close"] = "response_close"
    apply_intent: bool = True
    as_host: bool = False  # host override (the API only accepts this from the host)


# --- tabletop object behaviour ------------------------------------------------------
class Rotate(Base):
    type: Literal["rotate"] = "rotate"
    card_ids: IdList
    degrees: float | None = Field(default=None, ge=-3600, le=3600)  # absolute rotation
    delta: float | None = Field(default=None, ge=-3600, le=3600)  # relative rotation


class SetLock(Base):
    type: Literal["set_lock"] = "set_lock"
    card_ids: IdList
    value: bool | None = None  # None = toggle


class SetProtect(Base):
    type: Literal["set_protect"] = "set_protect"
    card_ids: IdList
    value: bool | None = None


class Attach(Base):
    """Attach cards (equipment, auras, tucked cards) to a host permanent."""

    type: Literal["attach"] = "attach"
    card_ids: IdList
    to: Id
    offset: tuple[Coord, Coord] | None = None  # relative position; default tucks under the host


class Detach(Base):
    type: Literal["detach"] = "detach"
    card_ids: IdList


class Group(Base):
    type: Literal["group"] = "group"
    card_ids: Annotated[list[Id], Field(min_length=2, max_length=250)]
    r: NewIds | None = None


class Ungroup(Base):
    type: Literal["ungroup"] = "ungroup"
    card_ids: IdList


class StackAdjust(Base):
    """Change the size of a logical token stack (``Treasure ×17``)."""

    type: Literal["stack_adjust"] = "stack_adjust"
    card_id: Id
    delta: int = Field(ge=-1000, le=1000)


class SplitStack(Base):
    type: Literal["split_stack"] = "split_stack"
    card_id: Id
    count: int = Field(default=1, ge=1, le=999)  # how many to take off into a new stack
    r: NewIds | None = None


class ExpandStack(Base):
    """Turn a logical stack into individual objects."""

    type: Literal["expand_stack"] = "expand_stack"
    card_id: Id
    r: NewIds | None = None


class MergeTokens(Base):
    """Collapse identical tokens into one logical stack (explicit; never automatic)."""

    type: Literal["merge_tokens"] = "merge_tokens"
    card_ids: Annotated[list[Id], Field(min_length=2, max_length=250)]


class AddMana(Base):
    type: Literal["add_mana"] = "add_mana"
    player: Id | None = None
    mana: dict[Literal["W", "U", "B", "R", "G", "C", "S"], Annotated[int, Field(ge=-100, le=100)]]


class ClearMana(Base):
    type: Literal["clear_mana"] = "clear_mana"
    player: Id | None = None


class Configure(Base):
    """Table settings (host-only in LAN games; enforced by the API layer)."""

    type: Literal["configure"] = "configure"
    undo_policy: Literal["everyone", "own", "host"] | None = None
    clear_mana_on_step: bool | None = None
    auto_untap: bool | None = None
    auto_commander_tax: bool | None = None


Action = Annotated[
    Draw
    | Move
    | SetPosition
    | Shuffle
    | Mill
    | Mulligan
    | PutTopFaceDown
    | MulliganTake
    | MulliganKeep
    | MulliganBottom
    | MulliganFinish
    | Reveal
    | Hide
    | LookTop
    | RevealTop
    | SearchStart
    | SearchEnd
    | EndView
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
    | ReturnToOwner
    | RemovePlayer
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
    | ResolveTop
    | ResponseOpen
    | ResponsePass
    | ResponseRespond
    | ResponseAutoPass
    | ResponseClose
    | Rotate
    | SetLock
    | SetProtect
    | Attach
    | Detach
    | Group
    | Ungroup
    | StackAdjust
    | SplitStack
    | ExpandStack
    | MergeTokens
    | AddMana
    | ClearMana
    | Configure,
    Field(discriminator="type"),
]

ACTION_ADAPTER: TypeAdapter[Action] = TypeAdapter(Action)


def parse_action(data: object) -> Action:
    """Validate an untrusted action payload. Raises ``pydantic.ValidationError``."""
    return ACTION_ADAPTER.validate_python(data)
