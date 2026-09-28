"""Safe custom mechanics: declarative macros made of whitelisted primitive steps.

A macro is data, never code. Each step becomes one ordinary engine action (validated like any
client action); the whole macro is applied as a single undoable history entry. There is no
expression language, no loops, no conditions, no network or file access — just these steps:

    CREATE_TOKEN  ADD_COUNTER  REMOVE_COUNTER  CHANGE_LIFE  ADD_MANA  MOVE_CARD  ROLL_DIE
    FLIP_COIN  CREATE_MARKER  SET_NOTE  SET_CHOICE  CREATE_ARROW  CHANGE_CONTROLLER  DISPLAY_TEXT

Targets are symbolic: "this" (the card the macro runs from), "selected" (the cards selected when
it runs), "me", "each_opponent", "each_player", or a player id.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.textutil import clean_text

CardTarget = Literal["this", "selected"]
PlayerTarget = Literal["me", "each_opponent", "each_player"] | Annotated[str, Field(pattern=r"^p[1-6]$")]
Text = Annotated[str, Field(max_length=200)]


class _Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def _clean(cls, v: Any) -> Any:
        return clean_text(v, 200) if isinstance(v, str) else v


class CreateToken(_Step):
    op: Literal["CREATE_TOKEN"]
    token_card_id: str | None = Field(default=None, max_length=64)  # a token printing from the card DB
    name: str | None = Field(default=None, max_length=60)  # or a custom token
    power: str | None = Field(default=None, max_length=5)
    toughness: str | None = Field(default=None, max_length=5)
    type_line: str | None = Field(default=None, max_length=80)
    count: int = Field(default=1, ge=1, le=50)
    tapped: bool = False
    player: PlayerTarget = "me"


class AddCounter(_Step):
    op: Literal["ADD_COUNTER", "CREATE_COUNTER"]
    target: CardTarget = "this"
    kind: Text = "+1/+1"
    amount: int = Field(default=1, ge=1, le=100)


class RemoveCounter(_Step):
    op: Literal["REMOVE_COUNTER"]
    target: CardTarget = "this"
    kind: Text = "+1/+1"
    amount: int = Field(default=1, ge=1, le=100)


class ChangeLife(_Step):
    op: Literal["CHANGE_LIFE"]
    player: PlayerTarget = "me"
    delta: int = Field(ge=-1000, le=1000)


class AddManaStep(_Step):
    op: Literal["ADD_MANA"]
    mana: dict[Literal["W", "U", "B", "R", "G", "C"], Annotated[int, Field(ge=-20, le=20)]]


class MoveCard(_Step):
    op: Literal["MOVE_CARD"]
    target: CardTarget = "this"
    to: Literal["hand", "graveyard", "exile", "library", "battlefield", "command"]
    position: Literal["top", "bottom"] | None = None


class RollDie(_Step):
    op: Literal["ROLL_DIE"]
    sides: int = Field(default=6, ge=2, le=1000)
    count: int = Field(default=1, ge=1, le=20)


class FlipCoin(_Step):
    op: Literal["FLIP_COIN"]
    count: int = Field(default=1, ge=1, le=20)


class CreateMarker(_Step):
    op: Literal["CREATE_MARKER"]
    target: CardTarget = "this"
    name: Annotated[str, Field(min_length=1, max_length=60)]
    value: str | None = Field(default=None, max_length=20)


class SetNote(_Step):
    op: Literal["SET_NOTE"]
    target: Literal["this"] = "this"
    text: Text


class SetChoice(_Step):
    op: Literal["SET_CHOICE"]
    target: Literal["this"] = "this"
    key: Annotated[str, Field(min_length=1, max_length=60)]
    value: Annotated[str, Field(max_length=120)]


class CreateArrowStep(_Step):
    op: Literal["CREATE_ARROW"]
    to: Literal["selected", "each_opponent"] = "selected"
    label: str = Field(default="", max_length=60)


class ChangeController(_Step):
    op: Literal["CHANGE_CONTROLLER"]
    target: CardTarget = "this"
    player: PlayerTarget = "me"


class DisplayText(_Step):
    op: Literal["DISPLAY_TEXT"]
    text: Annotated[str, Field(min_length=1, max_length=200)]


Step = Annotated[
    CreateToken | AddCounter | RemoveCounter | ChangeLife | AddManaStep | MoveCard | RollDie | FlipCoin | CreateMarker
    | SetNote | SetChoice | CreateArrowStep | ChangeController | DisplayText,
    Field(discriminator="op"),
]


class MacroDef(BaseModel):
    """A stored or inline macro."""

    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    name: Annotated[str, Field(min_length=1, max_length=60)]
    steps: Annotated[list[Step], Field(min_length=1, max_length=20)]

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        return clean_text(v, 60) or "Macro"


class MacroError(ValueError):
    pass


def _players(target: str, actor: str, order: list[str]) -> list[str]:
    if target == "me":
        return [actor]
    if target == "each_opponent":
        return [p for p in order if p != actor]
    if target == "each_player":
        return list(order)
    if target not in order:
        raise MacroError(f"No player {target}")
    return [target]


def expand(macro: MacroDef, *, actor: str, order: list[str], this: str | None, selected: list[str]) -> list[dict[str, Any]]:
    """Turn a macro into plain action payloads (validated and resolved by the engine as usual)."""
    out: list[dict[str, Any]] = []

    def cards(target: str) -> list[str]:
        ids = [this] if target == "this" and this else list(selected) if target == "selected" else []
        if not ids:
            raise MacroError("This step needs a card" if target == "this" else "Select some cards first")
        return ids

    for step in macro.steps:
        if isinstance(step, CreateToken):
            if step.token_card_id:
                token: dict[str, Any] = {"card_id": step.token_card_id}
            else:
                token = {"name": step.name or "Token", "power": step.power, "toughness": step.toughness,
                         "type_line": step.type_line or "Token Creature", "colors": [], "text": ""}
            for pid in _players(step.player, actor, order):
                out.append({"type": "create_token", "player": pid, "token": token, "count": step.count, "tapped": step.tapped,
                            **({"source_id": this} if this else {})})
        elif isinstance(step, AddCounter | RemoveCounter):
            delta = step.amount if isinstance(step, AddCounter) else -step.amount
            out.append({"type": "counter", "card_ids": cards(step.target), "kind": step.kind, "delta": delta})
        elif isinstance(step, ChangeLife):
            for pid in _players(step.player, actor, order):
                out.append({"type": "life", "player": pid, "delta": step.delta})
        elif isinstance(step, AddManaStep):
            out.append({"type": "add_mana", "mana": dict(step.mana)})
        elif isinstance(step, MoveCard):
            move: dict[str, Any] = {"type": "move", "card_ids": cards(step.target), "to": {"zone": step.to}}
            if step.position:
                move["position"] = step.position
            out.append(move)
        elif isinstance(step, RollDie):
            out.append({"type": "roll", "sides": step.sides, "count": step.count})
        elif isinstance(step, FlipCoin):
            out.append({"type": "coin", "count": step.count})
        elif isinstance(step, CreateMarker):
            out.append({"type": "add_effect", "card_ids": cards(step.target), "name": step.name,
                        **({"value": step.value} if step.value else {})})
        elif isinstance(step, SetNote):
            out.append({"type": "note", "card_id": cards("this")[0], "text": step.text})
        elif isinstance(step, SetChoice):
            out.append({"type": "set_choice", "card_id": cards("this")[0], "key": step.key, "value": step.value})
        elif isinstance(step, CreateArrowStep):
            targets = selected if step.to == "selected" else [p for p in order if p != actor]
            if not targets:
                raise MacroError("Select the targets first")
            out.append({"type": "create_arrow", "source": cards("this")[0], "targets": targets, "label": step.label})
        elif isinstance(step, ChangeController):
            for pid in _players(step.player, actor, order)[:1]:
                out.append({"type": "set_controller", "card_ids": cards(step.target), "player": pid})
        elif isinstance(step, DisplayText):
            out.append({"type": "chat", "text": step.text})
    return out
