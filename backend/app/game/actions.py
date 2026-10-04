"""Game actions (the only way game state changes).

Every action is a pydantic model discriminated by ``type``. Clients send *intents*: the
server fills ``actor`` from the connection and computes ``r`` (the resolved, deterministic
data such as shuffle orders, dice results and new object ids) in ``resolve.py``. Any
client-supplied ``actor``/``r`` is discarded. Applying a resolved action is deterministic, so
replaying the action list reproduces the game exactly (the basis of undo/redo).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from app.game.macros import MacroDef
from app.game.state import PHASES, PLAYER_ZONES, STACK, AttackTarget, Playmat, TokenDef
from app.textutil import clean_text

Id = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9:_\-]+$")]
IdList = Annotated[list[Id], Field(min_length=1, max_length=250)]
ZoneName = Literal[
    "library", "hand", "battlefield", "graveyard", "exile", "command", "sideboard", "companion", "foretell", "setaside", "phased",
    "stack",
]
Coord = Annotated[float, Field(ge=-100000, le=100000)]
# Target groups (601.2c): how many of ``targets`` belong to each group, in printed order; and the
# division (601.2d) of each divided group with two or more targets, amount per target in order.
TargetCounts = Annotated[list[Annotated[int, Field(ge=0, le=20)]], Field(max_length=10)]
Division = Annotated[list[Annotated[int, Field(ge=1, le=10000)]], Field(max_length=20)]
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
    tapped: bool = False  # enters the battlefield tapped (a replacement effect, not a tap afterwards)
    # Permanents entering the battlefield at once (one event, 603.6a / 614.12) whose replacements
    # differ: the ones among them that enter tapped, and whose battlefield each enters (default: ``to``)
    tapped_ids: list[Id] | None = Field(default=None, max_length=250)
    controllers: dict[Id, Id] | None = None
    # -- transform (wave 11A) -- 712.14a: the double-faced cards among them that enter the battlefield transformed (back face up)
    back_ids: list[Id] | None = Field(default=None, max_length=250)
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
    keep_tapped: list[Id] = Field(default_factory=list, max_length=250)  # see NextTurn


class PhaseShift(Base):
    """-- phasing (wave 13D) -- 702.26: permanents phase out (``out``) or in; attachments follow their host (702.26g)."""

    type: Literal["phase_shift"] = "phase_shift"
    card_ids: IdList
    out: bool = True


class Counter(Base):
    type: Literal["counter"] = "counter"
    card_ids: IdList
    kind: str = Field(min_length=1, max_length=40)
    delta: int = Field(default=1, ge=-1000, le=1000)
    group: int = Field(default=0, ge=0)  # -- counters (wave 7C) -- the steps of one instruction's counters (Event.group)

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
    back: TokenSpec | None = None  # -- wave 3F -- a double-faced token's back face (111.10i)

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
    source_id: Id | None = None  # optional provenance: the permanent that made these tokens
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
    # -- cast a copy (wave 13C) -- 707.12: the copy is made in the card's own zone (exile / graveyard); 722.3c: a prepared
    # permanent's copy is made in exile with the face of its prepare spell
    zone: Literal["exile", "graveyard"] | None = None
    face: int | None = None
    printing: str | None = Field(default=None, max_length=64)  # the copied card's printing when the source is itself a copy (722.2b)
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


Label = Annotated[str, Field(min_length=1, max_length=60)]
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class _Clean(Base):
    """Sanitises every free-text field (and lists of text) after validation."""

    @model_validator(mode="after")
    def _clean_strings(self) -> _Clean:
        for name in type(self).model_fields:
            if name in ("type", "actor", "card_id", "card_ids", "source", "targets", "source_id"):
                continue
            v = getattr(self, name)
            if isinstance(v, str):
                object.__setattr__(self, name, clean_text(v, 300))
            elif isinstance(v, list) and all(isinstance(x, str) for x in v):
                object.__setattr__(self, name, [clean_text(x, 120) for x in v])
        return self


class AddEffect(_Clean):
    """A temporary effect marker (+3/+3, Flying, Protection from red, or anything custom)."""

    type: Literal["add_effect"] = "add_effect"
    card_ids: IdList
    name: Label
    value: str | None = Field(default=None, max_length=20)
    text: str | None = Field(default=None, max_length=200)
    color: Color | None = None
    r: NewIds | None = None


class RemoveEffect(Base):
    type: Literal["remove_effect"] = "remove_effect"
    card_ids: IdList
    effect_id: Id | None = None  # None = all effects on these cards


class SetDamage(Base):
    type: Literal["set_damage"] = "set_damage"
    card_ids: IdList
    delta: int | None = Field(default=None, ge=-1000, le=1000)
    value: int | None = Field(default=None, ge=0, le=10000)


class SetChoice(_Clean):
    """Structured choice metadata: Chosen color, Chosen creature type, Named card, …"""

    type: Literal["set_choice"] = "set_choice"
    card_id: Id
    key: Label
    value: str | None = Field(default=None, max_length=120)  # None removes it


class SetStackInfo(_Clean):
    """Annotate a spell/ability on the stack: X, chosen modes, cast labels. Tracking only."""

    type: Literal["set_stack_info"] = "set_stack_info"
    card_id: Id
    x: int | None = Field(default=None, ge=0, le=100000)
    clear_x: bool = False
    modes: list[str] | None = Field(default=None, max_length=20)
    tags: list[str] | None = Field(default=None, max_length=20)


class SetExileGroup(_Clean):
    type: Literal["set_exile_group"] = "set_exile_group"
    card_ids: IdList
    group: str | None = Field(default=None, max_length=60)


class CreateArrow(_Clean):
    type: Literal["create_arrow"] = "create_arrow"
    source: Id
    targets: Annotated[list[Id], Field(min_length=1, max_length=20)]
    kind: Literal["target", "attack", "block", "custom"] = "target"
    label: str = Field(default="", max_length=60)
    r: NewIds | None = None


class RemoveArrow(Base):
    type: Literal["remove_arrow"] = "remove_arrow"
    arrow_id: Id


class SetCopySource(Base):
    """Change what a copy is copying (Change Copy Target)."""

    type: Literal["set_copy_source"] = "set_copy_source"
    card_id: Id
    source_id: Id


CleanupWhat = Literal["combat", "damage", "effects", "arrows", "mana", "tokens", "response", "exile_groups"]


class Cleanup(Base):
    """Manual table cleanup. Nothing here runs on its own."""

    type: Literal["cleanup"] = "cleanup"
    what: Annotated[list[CleanupWhat], Field(min_length=1, max_length=8)]
    card_ids: list[Id] | None = Field(default=None, max_length=250)  # limit to these cards (effects/damage)


class SetAppearance(Base):
    """Your sleeves (card back) and playmat. Visual only; asset ids are checked by the API."""

    type: Literal["set_appearance"] = "set_appearance"
    sleeve: Annotated[str, Field(pattern=r"^[0-9a-f]{8,32}$")] | None = None
    clear_sleeve: bool = False
    playmat: Playmat | None = None
    clear_playmat: bool = False


class SetTablePlaymat(Base):
    """One playmat under the whole table (host only on LAN; checked by the API)."""

    type: Literal["set_table_playmat"] = "set_table_playmat"
    playmat: Playmat | None = None


class RunMacro(Base):
    """Run a declarative macro (see game/macros.py) as one undoable action."""

    type: Literal["run_macro"] = "run_macro"
    macro: MacroDef
    card_id: Id | None = None  # "this"
    selected: list[Id] = Field(default_factory=list, max_length=100)
    r: list[dict[str, Any]] | None = None  # the resolved step actions (server-filled)


class SpawnCard(Base):
    """Solo / debug: put any card from the card database onto the table as a TEST OBJECT."""

    type: Literal["spawn_card"] = "spawn_card"
    card_id: Id  # printing id
    player: Id | None = None
    zone: Literal["battlefield", "hand", "library"] = "battlefield"
    x: Coord | None = None
    y: Coord | None = None
    r: NewIds | None = None
    resolved_name: str | None = None  # filled by resolve from the card database


class ResetDeck(Base):
    """Gather a player's own cards back into their deck (library, command zone, sideboard …),
    remove their tokens, copies and test objects, shuffle, and optionally reset life and draw."""

    type: Literal["reset_deck"] = "reset_deck"
    player: Id | None = None
    reset_life: bool = True
    draw: int = Field(default=0, ge=0, le=20)
    r: ShuffleData | None = None


class RestartGame(Base):
    """Everyone resets their deck (as above) and play goes back to turn 1 (host on LAN)."""

    type: Literal["restart_game"] = "restart_game"
    draw: int = Field(default=7, ge=0, le=20)
    r: dict[str, ShuffleData] | None = None


class RestoreState(Base):
    """Put the whole table back to an earlier state (a named snapshot or a point in history).

    Built by the server only (the state comes from its own records, never from a client);
    applying it is an ordinary action, so it can be undone and replays exactly.
    """

    type: Literal["restore_state"] = "restore_state"
    label: str = Field(max_length=120)
    state: dict[str, Any]


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
    # Permanents that don't untap in this untap step (502.3: "doesn't untap during …"; set by the rules engine).
    keep_tapped: list[Id] = Field(default_factory=list, max_length=250)


class Attack(Base):
    type: Literal["attack"] = "attack"
    card_ids: IdList
    target: AttackTarget | None = None  # None = stop attacking


class Block(Base):
    type: Literal["block"] = "block"
    card_id: Id
    attacker_id: Id | None = None  # None = stop blocking
    also: bool = False  # -- multiple blocks (wave 13B) -- 509.1a: block this attacker as well as the ones already blocked


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
    tapped: bool = False  # a permanent spell that enters tapped
    # -- refused look/cast-free (wave 3R5) -- the resolving object when spells cast during its
    # resolution (608.2g) are above it on the stack; None: the topmost object
    card_id: Id | None = None


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
    auto_clear_combat: bool | None = None
    allow_test_objects: bool | None = None
    # OFF / ASSISTED / FULL. Changing the level resets the options to its preset. Turning it off
    # keeps the rules bookkeeping (the table simply continues as a sandbox); turning it back on
    # or resuming reconciles it with the table (app/rules/reconcile.py).
    automation: Literal["off", "assisted", "full"] | None = None
    automation_options: AutomationOptionsPatch | None = None  # individual switches (→ CUSTOM)
    automation_paused: bool | None = None  # pause / resume automation (the sandbox keeps working)
    r: list[dict[str, Any]] | None = None  # server-filled: reconciliation steps (like an intent's)


class AutomationOptionsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_mana_payment: bool | None = None
    auto_combat_damage: bool | None = None
    auto_sba: bool | None = None
    auto_priority_pass: bool | None = None
    auto_cleanup: bool | None = None
    auto_token_creation: bool | None = None
    auto_counters: bool | None = None
    auto_trigger_stacking: bool | None = None
    auto_shuffle: bool | None = None
    highlights: Literal["off", "subtle", "full"] | None = None


# --- rules intents --------------------------------------------------------------------
# A player's *decision*, compiled by the rules engine (app/rules) into ordinary table actions
# on a scratch copy and recorded in ``r``. Applying one replays those steps, so undo, replay and
# saves work exactly as for sandbox actions, and replay never re-runs rules code.
class _Intent(Base):
    r: list[dict[str, Any]] | None = None  # compiled primitive steps (server-filled)


class PlayLand(_Intent):
    type: Literal["play_land"] = "play_land"
    card_id: Id
    face: int | None = Field(default=None, ge=0, le=3)  # which face of a modal double-faced card
    x: Coord | None = None
    y: Coord | None = None
    pay_life: bool | None = None  # shock lands: the answer to "pay 2 life or enter tapped" (asked if missing)


class Contribution(BaseModel):
    """Pay one mana symbol of the spell's total cost by tapping a creature (convoke, 702.51a),
    tapping an artifact (improvise, 702.126a) or exiling a card from your graveyard (delve, 702.66a)."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["convoke", "improvise", "delve"]
    card: Id


class CostChoice(BaseModel):
    """The objects chosen to pay one part of an activation cost (602.2b / 601.2h): e.g. the
    creature to sacrifice for "Sacrifice another creature". ``component`` is the part's index
    in the cost (app/rules/costs.py); the engine validates everything before paying anything."""

    model_config = ConfigDict(extra="forbid")
    component: int = Field(ge=0, le=20)
    cards: list[Id] = Field(default_factory=list, max_length=30)


class CastSpell(_Intent):
    type: Literal["cast_spell"] = "cast_spell"
    card_id: Id
    face: int | None = Field(default=None, ge=0, le=3)
    # Optional answers given up front; anything missing is asked for as a decision.
    targets: list[Id] = Field(default_factory=list, max_length=20)
    target_counts: TargetCounts = Field(default_factory=list)  # for spells with target groups
    division: Division = Field(default_factory=list)
    x_value: int | None = Field(default=None, ge=0, le=1000)
    modes: list[int] = Field(default_factory=list, max_length=10)
    # MANUAL PAY: exactly these mana sources (plus your mana pool). None: the engine pays per
    # your payment preference (AUTO pays, ASK suggests a payment first, MANUAL asks for sources).
    sources: list[Id] | None = Field(default=None, max_length=60)
    face_down: bool = False  # morph / megamorph (702.37): cast face down as a 2/2 for {3}
    free: bool = False  # cast without paying its mana cost — only when the engine granted it (suspend)
    buyback: bool = False  # 702.27: pay the buyback cost too; it returns to your hand as it resolves
    evoke: bool = False  # 702.74: cast for its evoke cost (sacrificed when it enters)
    dash: bool = False  # 702.109: cast for its dash cost (haste; returns to hand at the next end step)
    awaken: bool = False  # 702.113: cast for its awaken cost (and put its counters on a land)
    fuse: bool = False  # 702.102a: cast both halves of a split card with fuse from your hand (one fused split spell)
    # Cost contributions that aren't mana (convoke / improvise / delve): validated and applied
    # only when the rest of the total cost is paid (601.2h: no partial payments).
    contributions: list[Contribution] = Field(default_factory=list, max_length=60)
    # 702.33: pay the kicker cost this many times (1 for kicker; any number for multikicker)
    kicker: int = Field(default=0, ge=0, le=20)
    # (wave 3$) the objects chosen for the parts of an additional cost ("As an additional cost to cast this spell,
    # sacrifice a creature"); anything missing is asked for as a decision
    cost_choices: list[CostChoice] = Field(default_factory=list, max_length=10)
    # -- cost changers (wave 4I) -- 118.9: pay this alternative cost rather than the mana cost: "<card id>:<ability index>"
    # of the spell's own line (Force of Will) or of a permanent's static (Jodah); the hints list them (``alt_castable``)
    alt_cost: Id | None = None
    # "As an additional cost to cast green permanent spells, you may pay 2 life" (Defiler of Vigor): the permanents whose
    # optional additional cost is paid (601.2b); the hints list them (``optional_costs``)
    optional_costs: list[Id] = Field(default_factory=list, max_length=10)


class TurnFaceUp(_Intent):
    """Morph's special action (702.37e): pay the morph cost and turn your face-down permanent up."""

    type: Literal["turn_face_up"] = "turn_face_up"
    card_id: Id
    sources: list[Id] | None = Field(default=None, max_length=60)
    # -- keyword actions & face-down (wave 3F) -- which way, when there are several: its morph cost
    # (702.37e), its disguise cost (702.168d), or a manifested / cloaked creature card's mana cost (701.40b)
    method: Literal["morph", "disguise", "mana_cost"] | None = None


class UnlockDoor(_Intent):
    """-- Rooms (wave 18G) -- the unlock special action (116.2m, 709.5e): pay a locked half's mana cost (1 left, 2 right)."""

    type: Literal["unlock_door"] = "unlock_door"
    card_id: Id
    door: Literal[1, 2]
    sources: list[Id] | None = Field(default=None, max_length=60)


class ActivateAbility(_Intent):
    type: Literal["activate_ability"] = "activate_ability"
    card_id: Id
    # index into the card's abilities (app/rules/oracle.py): printed 0…99, granted by a static ability 100…, granted
    # by a resolved effect 10 000 + 16 × its timestamp + k (app/rules/granted.py ``index_of``, ``MAX_INDEX``)
    ability: int = Field(ge=0, le=2_000_000)
    targets: list[Id] = Field(default_factory=list, max_length=20)
    target_counts: TargetCounts = Field(default_factory=list)  # (see CastSpell)
    division: Division = Field(default_factory=list)
    x_value: int | None = Field(default=None, ge=0, le=1000)
    # A modal ability (700.2a, 602.2b → 601.2b): the chosen modes, in printed order; ``targets`` then
    # lists one target per chosen mode that has one, in that order (as for a modal spell).
    modes: list[int] = Field(default_factory=list, max_length=10)
    mana_choice: Literal["W", "U", "B", "R", "G", "C"] | None = None  # which colour, for "R or G" abilities
    sources: list[Id] | None = Field(default=None, max_length=60)  # MANUAL PAY (see CastSpell)
    # While paying for a spell with that keyword: commit (or, again, release) this card to pay one
    # symbol of its cost — nothing is tapped or exiled until the whole cost is paid.
    convoke: bool = False  # this creature: {1} or one mana of its color
    improvise: bool = False  # this artifact: {1}
    delve: bool = False  # this card in your graveyard: {1}
    crew: list[Id] | None = Field(default=None, max_length=30)  # Crew N: the creatures tapped to pay it
    # Objects chosen for cost parts ("Sacrifice a creature", "Discard a card" …); any part not
    # given is asked for as a private decision before anything is paid.
    cost_choices: list[CostChoice] = Field(default_factory=list, max_length=10)


class AttackDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_id: Id
    target: Id  # a player id, or a planeswalker / battle card id


class DeclareAttackers(_Intent):
    type: Literal["declare_attackers"] = "declare_attackers"
    attackers: list[AttackDeclaration] = Field(default_factory=list, max_length=100)
    sources: list[Id] | None = Field(default=None, max_length=60)  # -- combat (wave 5C) -- MANUAL PAY of an attack cost


class BlockDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocker_id: Id
    attacker_id: Id


class DeclareBlockers(_Intent):
    type: Literal["declare_blockers"] = "declare_blockers"
    blocks: list[BlockDeclaration] = Field(default_factory=list, max_length=100)


PASS_UNTIL = ("next_action", "stack_changes", "stack_empty", "next_step", "next_turn", "my_turn", "combat")


class PassPriority(_Intent):
    """Pass. ``until`` keeps passing for you until the condition is met (PASS UNTIL NEXT ACTION,
    RESOLVE ONE = stack_changes, RESOLVE ALL = stack_empty …); decisions still come to you."""

    type: Literal["pass_priority"] = "pass_priority"
    until: Literal["next_action", "stack_changes", "stack_empty", "next_step", "next_turn", "my_turn", "combat"] | None = None


class Choose(_Intent):
    """Answer the pending decision (targets, modes, cards to discard, "Done" after a manual step…)."""

    type: Literal["choose"] = "choose"
    decision_id: Id
    option_ids: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=250)
    # A "divide" decision (601.2d): the amount for each option, in the options' order.
    amounts: list[Annotated[int, Field(ge=0, le=10000)]] = Field(default_factory=list, max_length=20)
    # Remember this answer (for prompts that allow it): ALWAYS YES / NO THIS TURN, ALWAYS YIELD.
    remember: Literal["yes_this_turn", "no_this_turn", "always_yield"] | None = None


class Concede(_Intent):
    type: Literal["concede"] = "concede"


class SetStops(_Intent):
    """Where the engine stops to give you priority (Arena-style); elsewhere it passes for you."""

    type: Literal["set_stops"] = "set_stops"
    own: list[str] = Field(default_factory=list, max_length=12)
    others: list[str] = Field(default_factory=list, max_length=12)
    hold_priority: bool = False  # keep priority after casting (Arena's "full control")
    smart_pass: bool = True  # pass for me while I have nothing I could respond with

    @field_validator("own", "others")
    @classmethod
    def _steps(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if s not in PHASES]
        if bad:
            raise ValueError(f"unknown steps: {bad}")
        return list(dict.fromkeys(v))


def _steps_list(v: list[str] | None) -> list[str] | None:
    if v is None:
        return None
    bad = [s for s in v if s not in PHASES]
    if bad:
        raise ValueError(f"unknown steps: {bad}")
    return list(dict.fromkeys(v))


class SetPrefs(_Intent):
    """Your automation preferences (RESPONSE, stops, payment, temporary overrides …). Allowed any
    time, even without priority, while paused or during an animation: it only changes what the
    engine does for you from now on. Only the fields you send change."""

    type: Literal["set_prefs"] = "set_prefs"
    response: Literal["off", "auto", "on"] | None = None
    stops_my_turn: list[str] | None = Field(default=None, max_length=12)
    stops_their_turn: list[str] | None = Field(default=None, max_length=12)
    bluff_stops: bool | None = None
    payment: Literal["self"] | None = None  # players always tap their own mana
    auto_resolve_own_triggers: Literal["off", "safe", "on"] | None = None
    auto_order_identical_triggers: bool | None = None
    hold_priority: bool | None = None
    full_control: bool | None = None
    force_stop: bool | None = None
    cancel_pass: bool = False  # cancel a PASS UNTIL … / HOLD AFTER THIS RESOLVES
    stop_after: Id | None = None  # HOLD AFTER THIS RESOLVES: a card on the stack
    # PREFER / NORMAL / SAVE for one of your mana sources ("normal" clears it).
    mana_source: Id | None = None
    mana_source_protection: Literal["prefer", "normal", "save"] | None = None
    # Remembered answers: add one, or cancel one (by key) or all.
    add_yield: YieldIn | None = None
    cancel_yield: Annotated[str, Field(max_length=120)] | None = None
    cancel_all_yields: bool = False

    _stops = field_validator("stops_my_turn", "stops_their_turn")(_steps_list)


class YieldIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["always_yield", "yes_this_turn", "no_this_turn"]
    key: str = Field(min_length=1, max_length=120)


class SetCardAutomation(_Intent):
    """Right-click → Automation: MANUAL takes one card out of automation (its controller resolves
    it by hand and the engine doesn't enforce its timing); AUTO gives it back."""

    type: Literal["set_card_automation"] = "set_card_automation"
    card_id: Id
    mode: Literal["auto", "manual", "assisted"]


class RepeatUntil(BaseModel):
    """REPEAT UNTIL: stop once the condition holds (checked before each iteration)."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["mana", "tokens", "life_at_most", "life_at_least", "counter"]
    value: int = Field(ge=-100000, le=100000)
    player: Id | None = None  # whose mana / tokens / life (default: you)
    card_id: Id | None = None  # counter: on which permanent
    counter: Annotated[str, Field(max_length=30)] | None = None


class RepeatSequence(_Intent):
    """REPEAT LAST VALIDATED SEQUENCE: replay your last ``count`` intents (which you just did once)
    up to ``times`` more times. Every iteration goes through the rules engine; it stops as soon as
    an iteration becomes illegal, needs a choice or isn't deterministic."""

    type: Literal["repeat_sequence"] = "repeat_sequence"
    count: int = Field(ge=1, le=30)
    times: int = Field(default=1, ge=1, le=500)
    until: RepeatUntil | None = None


class RulesSync(Base):
    """Server-built only: the rules state after a compiled intent (always its last step)."""

    type: Literal["rules_sync"] = "rules_sync"
    rules: dict[str, Any] | None = None


class RulesMana(Base):
    """Server-built only: mana work in one step: tap/sacrifice sources, change one player's pool
    (added minus spent), pay life for Phyrexian mana, or empty every pool at a step change."""

    type: Literal["rules_mana"] = "rules_mana"
    player: Id
    tap: list[Id] = Field(default_factory=list, max_length=100)
    sacrifice: list[Id] = Field(default_factory=list, max_length=100)
    delta: dict[Literal["W", "U", "B", "R", "G", "C"], Annotated[int, Field(ge=-1000, le=1000)]] = Field(default_factory=dict)
    life: int = Field(default=0, ge=0, le=1000)
    empty_all: bool = False
    label: str = Field(default="", max_length=200)  # "paid {1}{G} for Llanowar Elves"


class CommanderHit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player: Id
    commander: Id  # commander_key
    amount: int = Field(ge=0, le=100000)


class RulesDamage(Base):
    """Server-built only: all combat damage of one damage step, dealt simultaneously."""

    type: Literal["rules_damage"] = "rules_damage"
    creatures: dict[str, Annotated[int, Field(ge=0, le=100000)]] = Field(default_factory=dict)  # card -> damage
    players: dict[str, Annotated[int, Field(ge=0, le=100000)]] = Field(default_factory=dict)  # life lost
    commander: list[CommanderHit] = Field(default_factory=list)  # combat damage by commanders (also in players)
    planeswalkers: dict[str, Annotated[int, Field(ge=0, le=100000)]] = Field(default_factory=dict)  # loyalty removed
    lifelink: dict[str, Annotated[int, Field(ge=0, le=100000)]] = Field(default_factory=dict)  # life gained
    wither: dict[str, Annotated[int, Field(ge=0, le=100000)]] = Field(default_factory=dict)  # card -> -1/-1 counters
    # -- triggers (wave 17D) -- 120.3d: card -> the player who puts those counters (its source's controller) -> how many
    wither_by: dict[str, dict[str, Annotated[int, Field(ge=0, le=100000)]]] = Field(default_factory=dict)
    poison: dict[str, Annotated[int, Field(ge=0, le=100000)]] = Field(default_factory=dict)  # player -> poison counters
    first_strike: bool = False
    combat: bool = True  # False: damage from a spell or ability
    dealt: list[DamageDealt] = Field(default_factory=list, max_length=500)  # who dealt what to whom (events)


class DamageDealt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Annotated[str, Field(max_length=64)]  # source object id
    target: Id  # card id or player id
    target_object: Annotated[str, Field(max_length=64)] | None = None
    amount: int = Field(ge=0, le=100000)


class RulesLog(Base):
    """Server-built only: a log line written by the rules engine ("Alice passed", "Turn 3 …")."""

    type: Literal["rules_log"] = "rules_log"
    text: str = Field(max_length=500)
    card_ids: list[Id] = Field(default_factory=list, max_length=20)  # cards appended to the line
    kind: str = Field(default="rules", max_length=20)
    fold: int = Field(default=0, ge=0, le=100000)  # fold the previous N log lines under this one (repeats)


INTENT_TYPES = frozenset(
    {"play_land", "cast_spell", "activate_ability", "declare_attackers", "declare_blockers", "pass_priority",
     "choose", "concede", "set_stops", "set_prefs", "set_card_automation", "repeat_sequence", "turn_face_up", "unlock_door"}
)
SERVER_ONLY_TYPES = frozenset({"rules_sync", "rules_log", "rules_mana", "rules_damage"})


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
    | PhaseShift
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
    | RestoreState
    | SpawnCard
    | ResetDeck
    | RestartGame
    | RunMacro
    | SetAppearance
    | SetTablePlaymat
    | AddEffect
    | RemoveEffect
    | SetDamage
    | SetChoice
    | SetStackInfo
    | SetExileGroup
    | CreateArrow
    | RemoveArrow
    | SetCopySource
    | Cleanup
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
    | Configure
    | PlayLand
    | CastSpell
    | TurnFaceUp
    | UnlockDoor
    | ActivateAbility
    | DeclareAttackers
    | DeclareBlockers
    | PassPriority
    | Choose
    | Concede
    | SetStops
    | SetPrefs
    | SetCardAutomation
    | RepeatSequence
    | RulesSync
    | RulesMana
    | RulesDamage
    | RulesLog,
    Field(discriminator="type"),
]

ACTION_ADAPTER: TypeAdapter[Action] = TypeAdapter(Action)


def parse_action(data: object) -> Action:
    """Validate an untrusted action payload. Raises ``pydantic.ValidationError``."""
    return ACTION_ADAPTER.validate_python(data)
