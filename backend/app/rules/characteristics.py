"""Characteristics of objects, derived on demand (never stored).

Today this is the *printed* layer: name, types, mana cost, colors, power/toughness, loyalty and
abilities from the card database (the right face for double-faced and modal cards), from the
token definition, or the fixed 2/2 of a face-down permanent. Continuous effects (the layer
system) arrive with milestone 16 and are applied on top of this in one place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.game.state import CardInstance
from app.rules.oracle import AbilityText, parse_abilities

SUPERTYPES = frozenset({"Basic", "Legendary", "Snow", "World", "Ongoing", "Elite", "Host"})
CARD_TYPES = frozenset({
    "Artifact", "Battle", "Creature", "Enchantment", "Instant", "Kindred", "Land", "Planeswalker", "Sorcery",
    "Tribal", "Conspiracy", "Dungeon", "Emblem", "Phenomenon", "Plane", "Scheme", "Vanguard",
})
BASIC_LAND_MANA = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}
PERMANENT_TYPES = frozenset({"Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"})
_MANA_TOKEN = re.compile(r"\{([^}]+)\}")


class CardInfo(Protocol):
    def get(self, card_id: str) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class Characteristics:
    name: str
    supertypes: frozenset[str] = frozenset()
    types: frozenset[str] = frozenset()
    subtypes: frozenset[str] = frozenset()
    mana_cost: str = ""
    mana_value: float = 0
    colors: frozenset[str] = frozenset()
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    oracle_text: str = ""
    abilities: tuple[AbilityText, ...] = field(default_factory=tuple)
    oracle_id: str | None = None
    face_down: bool = False
    is_ability: bool = False  # an ability object on the stack
    # Derived by app.rules.layers (never printed): current power/toughness, keywords gained/lost.
    pt: tuple[int, int] | None = None
    granted: frozenset[str] = frozenset()
    lost: frozenset[str] = frozenset()

    @property
    def is_land(self) -> bool:
        return "Land" in self.types

    @property
    def is_creature(self) -> bool:
        return "Creature" in self.types

    @property
    def is_permanent_card(self) -> bool:
        return bool(self.types & PERMANENT_TYPES)

    @property
    def is_instant_or_sorcery(self) -> bool:
        return bool(self.types & {"Instant", "Sorcery"})

    @property
    def keywords(self) -> frozenset[str]:
        printed = frozenset(k for a in self.abilities if a.kind == "keywords" for k in a.keywords)
        return (printed | self.granted) - self.lost

    @property
    def has_flash(self) -> bool:
        return "flash" in self.keywords


def parse_type_line(type_line: str) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """"Legendary Creature — Elf Druid" → ({Legendary}, {Creature}, {Elf, Druid})."""
    left, _, right = (type_line or "").partition("—")
    words = left.replace("Token", " ").split()
    supertypes = frozenset(w for w in words if w in SUPERTYPES)
    types = frozenset(w for w in words if w in CARD_TYPES)
    subtypes = frozenset(right.split()) if right else frozenset()
    return supertypes, types, subtypes


def mana_value(cost: str) -> float:
    total = 0.0
    for sym in _MANA_TOKEN.findall(cost or ""):
        if sym.isdigit():
            total += int(sym)
        elif sym in ("X", "Y", "Z"):
            continue
        elif sym == "½" or sym == "H":
            total += 0.5
        else:
            total += 1  # coloured, hybrid ({G/W}, {2/B}: counts as its largest part below), phyrexian
            if "/" in sym:
                left = sym.split("/")[0]
                if left.isdigit():
                    total += int(left) - 1
    return total


_printed_cache: dict[tuple[str, int], Characteristics] = {}
_CACHE_MAX = 5000


HALVES = ("split", "adventure", "aftermath")  # one card, two spells: you cast one half


def _from_card_data(data: dict[str, Any], face: int, *, half: bool = False) -> Characteristics:
    faces = data.get("faces") or []
    layout = data.get("layout")
    if half and faces and layout in HALVES:
        face = min(face, len(faces) - 1)
        src = faces[face]
        text = str(src.get("oracle_text") or "")
        return _build(data, src, text)
    # Split cards and adventures are one object with both halves' text while not on the stack;
    # double-faced / modal / flip cards use the face that is up.
    if faces and layout in ("transform", "modal_dfc", "flip", "meld", "reversible_card", "prepare"):
        src = faces[min(face, len(faces) - 1)]
        text = str(src.get("oracle_text") or "")
    elif faces and layout in ("split", "adventure", "aftermath"):
        src = faces[min(face, len(faces) - 1)] if face else data
        text = str(src.get("oracle_text") or data.get("oracle_text") or "")
    else:
        src = data
        text = str(data.get("oracle_text") or "")
    return _build(data, src, text)


def _build(data: dict[str, Any], src: dict[str, Any], text: str) -> Characteristics:
    type_line = str(src.get("type_line") or data.get("type_line") or "")
    supertypes, types, subtypes = parse_type_line(type_line)
    cost = str(src.get("mana_cost") or (data.get("mana_cost") if src is data else "") or "")
    colors = src.get("colors") if src.get("colors") is not None else data.get("colors")
    return Characteristics(
        name=str(src.get("name") or data.get("name") or ""),
        supertypes=supertypes,
        types=types,
        subtypes=subtypes,
        mana_cost=cost,
        mana_value=mana_value(cost),
        colors=frozenset(colors or []),
        power=src.get("power"),
        toughness=src.get("toughness"),
        loyalty=src.get("loyalty"),
        oracle_text=text,
        abilities=with_intrinsic_mana(parse_abilities(text, spell=bool(types & {"Instant", "Sorcery"})), subtypes),
        oracle_id=data.get("oracle_id"),
    )


def with_intrinsic_mana(abilities: list[AbilityText], subtypes: frozenset[str]) -> tuple[AbilityText, ...]:
    """Basic land types grant "{T}: Add [mana]." (rule 305.6), listed after the printed abilities."""
    out = list(abilities)
    for t in sorted(subtypes):
        if t in BASIC_LAND_MANA:
            text = f"{{T}}: Add {{{BASIC_LAND_MANA[t]}}}."
            if not any(a.text == text for a in out):
                out.append(AbilityText(index=len(out), text=text, kind="mana", cost="{T}", intrinsic=True))
    return tuple(out)


def printed_from_data(data: dict[str, Any], face: int = 0) -> Characteristics:
    """Characteristics of a card-database entry (cached per printing and face)."""
    key = (str(data.get("id")), face)
    hit = _printed_cache.get(key)
    if hit is None:
        if len(_printed_cache) > _CACHE_MAX:
            _printed_cache.clear()
        hit = _printed_cache[key] = _from_card_data(data, face)
    return hit


def is_two_spell_card(card: CardInstance, info: CardInfo) -> bool:
    data = info.get(card.card_id) if card.card_id else None
    return bool(data and data.get("faces") and data.get("layout") in HALVES)


def as_cast(card: CardInstance, info: CardInfo, face: int | None) -> Characteristics:
    """The spell you cast from this card: for split cards and adventures, the half you chose
    (its own cost and type), otherwise the card as it is (after turning it to ``face``)."""
    data = info.get(card.card_id) if card.card_id else None
    if data and data.get("faces") and data.get("layout") in HALVES and card.ability is None and not card.token:
        key = (str(data.get("id")) + "#half", face or 0)
        hit = _printed_cache.get(key)
        if hit is None:
            hit = _printed_cache[key] = _from_card_data(data, face or 0, half=True)
        return hit
    return of(card.model_copy(update={"face": face}) if face is not None else card, info)


def of(card: CardInstance, info: CardInfo) -> Characteristics:
    """Current characteristics of a card instance (printed layer; see module docstring)."""
    if card.ability is not None:
        return Characteristics(name=card.ability.source_name or "Ability", oracle_text=card.ability.text,
                               abilities=tuple(parse_abilities(card.ability.text, spell=True)), is_ability=True)
    if card.face_down and card.zone.endswith(":battlefield"):
        return Characteristics(name="", types=frozenset({"Creature"}), power="2", toughness="2", face_down=True)
    if card.token is not None and not card.card_id:
        t = card.token
        supertypes, types, subtypes = parse_type_line(t.type_line)
        return Characteristics(
            name=t.name, supertypes=supertypes, types=types, subtypes=subtypes, colors=frozenset(t.colors),
            power=t.power, toughness=t.toughness, oracle_text=t.text,
            abilities=with_intrinsic_mana(parse_abilities(t.text, spell=bool(types & {"Instant", "Sorcery"})), subtypes),
        )
    data = info.get(card.card_id) if card.card_id else None
    if data is None:
        # Unknown to the card database (a custom object): typeless, so the engine won't guess.
        return Characteristics(name=card.name or "")
    return printed_from_data(data, card.face)
