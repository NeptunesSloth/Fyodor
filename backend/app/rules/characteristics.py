"""Characteristics of objects, derived on demand (never stored).

Today this is the *printed* layer: name, types, mana cost, colors, power/toughness, loyalty and
abilities from the card database (the right face for double-faced and modal cards), from the
token definition, or the fixed 2/2 of a face-down permanent. Continuous effects (the layer
system) arrive with milestone 16 and are applied on top of this in one place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from app.game.state import CardInstance
from app.rules import levelers, read_pass
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
    defense: str | None = None  # a battle's printed defense (310.4a)
    oracle_text: str = ""
    abilities: tuple[AbilityText, ...] = field(default_factory=tuple)
    oracle_id: str | None = None
    face_down: bool = False
    is_ability: bool = False  # an ability object on the stack
    # Derived by app.rules.layers (never printed): current power/toughness, keywords gained/lost.
    pt: tuple[int, int] | None = None
    base_pt: tuple[int, int] | None = None  # -- base power (wave 30J) -- 208.4b: after layers 7a and 7b, before counters and 7c's modifications
    granted: frozenset[str] = frozenset()
    lost: frozenset[str] = frozenset()
    # Rules imposed on it: by resolved effects ("can't block this turn"), by other objects (an
    # Aura's "Enchanted creature can't block.", "Creatures your opponents control can't block.")
    # and by its own restriction statics ("~ can't be blocked by creatures with power 2 or less.").
    # The vocabulary is app/rules/statics.py's (cant_block, must_attack, doesnt_untap,
    # cant_be_blocked_by:<selector> …). They aren't abilities: losing abilities doesn't remove
    # the ones other objects impose.
    imposed: frozenset[str] = frozenset()
    level: int | None = None  # -- Class (wave 16A) -- 716.2b: the permanent's class level (None: not read for a permanent, all sections)
    doors: frozenset[int] | None = None  # -- Rooms (wave 18G) -- 709.5: the halves (1 left, 2 right) that count; a Room's abilities are sectioned by door
    word: str | None = None  # -- linked words (wave 33B) -- 607.2f: the word the object chose as it entered ("" none; None: not read, every linked ability)

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
_fused_cache: dict[str, Characteristics | None] = {}  # (wave 16B)
_CACHE_MAX = 5000


HALVES = ("split", "adventure", "aftermath")  # one card, two spells: you cast one half


# -- keyword actions & face-down (wave 3F) ------------------------------------------------------
# 708.2a: a face-down spell or permanent is a 2/2 creature with no text, no name, no subtypes and no
# mana cost — unless what made it face down lists other characteristics: disguise (702.168a) and
# cloak (701.58a) give it ward {2}. These are its copiable values (708.2).
_WARD_2 = (AbilityText(index=0, text="Ward {2}", kind="keywords", keywords=("ward",)),)


SPEC_TYPES = {"artifact": "Artifact", "creature": "Creature", "land": "Land", "enchantment": "Enchantment"}


def parse_spec(text: str) -> str | None:
    """-- hidden exile (wave 18A) -- 708.2a: what an effect says a permanent it turned face down is — "a 2/2 Cyberman artifact creature",
    "5/5 artifact creatures", "a Forest land" — as the canonical "[P/T ]<subtypes> <types>" (singular), or None when it isn't exactly
    that: P/T if and only if it is a creature; capitalised subtype words, lower-case card types (artifact, creature, land, enchantment)."""
    m = re.fullmatch(r"(?:an? )?(?:(\d+/\d+) )?([A-Za-z]+(?: [A-Za-z]+)*)", text.strip())
    if m is None:
        return None
    types: list[str] = []
    subs: list[str] = []
    for w in m[2].split():
        single = w if w.lower() in SPEC_TYPES else w[:-1] if w.lower().endswith("s") and w[:-1].lower() in SPEC_TYPES else None
        if single is not None:
            types.append(single.lower())
        elif w[0].isupper() and w.isalpha():
            subs.append(w)
        else:
            return None
    if not types or ("creature" in types) != bool(m[1]):
        return None
    return " ".join([*([m[1]] if m[1] else []), *subs, *types])


def join_spec(body: str) -> str:
    """"…face down[ under your control]. It's / They're a 2/2 Cyberman artifact creature." as one clause, "… face down … as a 2/2 Cyberman
    artifact creature" (708.2a: the characteristics come with the instruction that turns them face down)."""
    return re.sub(r"(face down(?: under (?:your|its owner's|their owner's) control)?)\. (?:It's|They're) ([^.]+)\.",
                  lambda m: f"{m[1]} as {m[2]}." if parse_spec(m[2]) else m[0], body)


def face_down_characteristics(kind: str | None, spec: str | None = None) -> Characteristics:
    """708.2a: a 2/2 creature with no name, text, subtypes or mana cost — unless the effect that turned it face down says what it is
    (-- hidden exile (wave 18A) -- ``spec``, "[P/T ]<subtypes and types>": "2/2 Cyberman artifact creature", "Forest land")."""
    abilities = _WARD_2 if kind in ("disguise", "cloak") else ()
    if not spec:
        return Characteristics(name="", types=frozenset({"Creature"}), power="2", toughness="2", face_down=True, abilities=abilities)
    pt, _, words = spec.partition(" ") if re.match(r"\d+/\d+ ", spec) else ("", "", spec)
    types = frozenset(SPEC_TYPES[w.lower()] for w in words.split() if w.lower() in SPEC_TYPES)
    subtypes = frozenset(w for w in words.split() if w.lower() not in SPEC_TYPES)
    power, _, toughness = pt.partition("/")
    return Characteristics(name="", types=types, subtypes=subtypes, power=power or None, toughness=toughness or None, face_down=True,
                           abilities=with_intrinsic_mana(list(abilities), subtypes))


def _from_card_data(data: dict[str, Any], face: int, *, half: bool = False) -> Characteristics:
    faces = data.get("faces") or []
    layout = data.get("layout")
    if not half and room(data):
        return _room(data)
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
        if layout == "transform" and face > 0:  # -- transform (wave 11A) -- 712.8e: its mana value is its front face's
            return replace(_build(data, src, text), mana_value=mana_value(str(faces[0].get("mana_cost") or "")))
        if layout == "flip" and face > 0:  # -- flip (wave 24C) -- 710.1c: the mana cost and colors of a flipped permanent don't change
            front = _build(data, faces[0], str(faces[0].get("oracle_text") or ""))
            return replace(_build(data, src, text), mana_cost=front.mana_cost, mana_value=front.mana_value, colors=front.colors)
    elif faces and layout == "adventure":
        # -- ability words (wave 9C) -- 715.4: outside the stack (and on it not as an Adventure) an adventurer card has only
        # its normal characteristics: its Adventure's text and types are not the permanent's (a static of a permanent
        # Adventure card, Virtue of Strength, would otherwise be read as a spell line)
        src = faces[min(face, len(faces) - 1)]
        text = str(src.get("oracle_text") or "")
    elif faces and layout in ("split", "aftermath"):
        src = faces[min(face, len(faces) - 1)] if face else data
        text = str(src.get("oracle_text") or data.get("oracle_text") or "")
    else:
        src = data
        text = str(data.get("oracle_text") or "")
    return _build(data, src, text)


def room(data: dict[str, Any]) -> bool:
    """-- Rooms (wave 18G) -- 709.5: a split card with one shared type line (every half is a Room)."""
    faces = data.get("faces") or []
    return data.get("layout") == "split" and len(faces) == 2 and all("Room" in str(f.get("type_line") or "") for f in faces)


def _room(data: dict[str, Any]) -> Characteristics:
    """The Room card with both doors (hand, graveyard …; 202.3d: the halves' costs combined). The right door's abilities
    follow the left's, each tagged with its door (``AbilityText.section``); ``with_doors`` narrows it to the doors that count."""
    a, b = (_from_card_data(data, i, half=True) for i in (0, 1))
    abilities = (*a.abilities, *(replace(x, index=len(a.abilities) + x.index, section=2) for x in b.abilities))
    return replace(a, name=f"{a.name} // {b.name}", mana_cost=a.mana_cost + b.mana_cost, mana_value=a.mana_value + b.mana_value,
                   colors=a.colors | b.colors, oracle_text=f"{a.oracle_text}\n{b.oracle_text}", abilities=abilities,
                   doors=frozenset({1, 2}))


def with_doors(ch: Characteristics, data: dict[str, Any], doors: frozenset[int]) -> Characteristics:
    """-- Rooms (wave 18G) -- 709.5: a locked half has no name, mana cost or rules text; only ``doors`` count."""
    halves = [half_from_data(data, d - 1) for d in sorted(doors)]
    return replace(ch, doors=doors, name=" // ".join(h.name for h in halves), mana_cost="".join(h.mana_cost for h in halves),
                   mana_value=sum(h.mana_value for h in halves),
                   colors=frozenset().union(*(h.colors for h in halves)) if halves else frozenset())


def _build(data: dict[str, Any], src: dict[str, Any], text: str) -> Characteristics:
    type_line = str(src.get("type_line") or data.get("type_line") or "")
    supertypes, types, subtypes = parse_type_line(type_line)
    cost = str(src.get("mana_cost") or (data.get("mana_cost") if src is data else "") or "")
    colors = src.get("colors") if src.get("colors") is not None else data.get("colors")
    station = levelers.station_creature(text) is not None  # -- Station (wave 46D) -- 721.2c: its power/toughness box is the station symbol's
    abilities = with_intrinsic_mana(parse_abilities(text, spell=bool(types & {"Instant", "Sorcery"}), pt=(src.get("power"), src.get("toughness"))), subtypes)
    return Characteristics(
        name=str(src.get("name") or data.get("name") or ""),
        supertypes=supertypes,
        types=types,
        subtypes=changeling(subtypes, abilities, str(src.get("name") or data.get("name") or "")),
        mana_cost=cost,
        mana_value=mana_value(cost),
        colors=frozenset() if _devoid(abilities) else frozenset("WUBRG") if all_colors(abilities, str(src.get("name") or data.get("name") or ""))
        else frozenset(colors or []),
        power=None if station else src.get("power"),
        toughness=None if station else src.get("toughness"),
        loyalty=src.get("loyalty"),
        defense=src.get("defense"),
        oracle_text=text,
        abilities=abilities,
        oracle_id=data.get("oracle_id"),
    )


def _devoid(abilities: tuple[AbilityText, ...]) -> bool:
    """702.114a devoid: "This object is colorless" (a characteristic-defining ability, every zone)."""
    return any(a.kind == "keywords" and "devoid" in a.keywords for a in abilities)


def changeling(subtypes: frozenset[str], abilities: tuple[AbilityText, ...], name: str = "") -> frozenset[str]:
    """702.73a: changeling is a characteristic-defining ability, "this object is every creature
    type" — in every zone (CR 205.3m list). -- type statics (wave 5F) -- so is "Mistform Ultimus is every creature
    type (even if this card isn't on the battlefield)." (604.3: a characteristic-defining ability of the object itself)."""
    every = f"{name} is every creature type." if name else None
    if any((a.kind == "keywords" and "changeling" in a.keywords) or (a.kind == "static" and a.text == every)
           for a in abilities):
        from app.rules.creature_types import CREATURE_TYPES

        return subtypes | CREATURE_TYPES
    # -- static_other sweep (wave 17C) -- 604.3: "Burakos is also a Cleric, Rogue, Warrior, and Wizard." (a characteristic-defining ability
    # adding creature types, in every zone)
    for a in abilities:
        m = _ALSO.fullmatch(a.text.strip()) if a.kind == "static" else None
        if m is not None and m["n"] in (name, name.split(",")[0]) and (types := [w for w in re.split(r", and |, | and ", m["l"]) if w]):
            from app.rules.creature_types import CREATURE_TYPES

            if all(t in CREATURE_TYPES for t in types):
                subtypes = subtypes | frozenset(types)
    return subtypes


_ALSO = re.compile(r"^(?P<n>[^,.]+(?:, [A-Z][^,.]*)?) is also an? (?P<l>[A-Z][A-Za-z]*(?:(?:, | and |, and )[A-Z][A-Za-z]*)*)\.$")
_ALL_COLORS = re.compile(r"^(?P<n>.+?) is all colors\.(?: This ability doesn't affect its color identity\.)?$")


def all_colors(abilities: tuple[AbilityText, ...], name: str) -> bool:
    """-- static_other sweep (wave 17C) -- 604.3, 105.2c: "Transguild Courier is all colors." (a characteristic-defining ability, every zone)"""
    return any((m := _ALL_COLORS.fullmatch(a.text.strip())) is not None and m["n"] in (name, name.split(",")[0])
               for a in abilities if a.kind == "static")


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


def transformable(card: CardInstance, info: CardInfo) -> bool:
    """-- transform (wave 11A) -- 701.27a, 712.9: a card that can transform or convert: a double-faced card that isn't a meld card
    (712.4c; review 30b: a modal one too, 712.9 of CR 2026-09-25 — Gwen Stacy's ruling of 2025-09-19, "This is a change from previous
    rules"), whose other face is a permanent face (712.10)."""
    data = info.get(card.card_id) if card.card_id and card.token is None and not card.is_token else None
    faces = (data or {}).get("faces") or []
    if data is None or data.get("layout") not in ("transform", "modal_dfc") or len(faces) < 2:
        return False
    return not {"Instant", "Sorcery"} & set(parse_type_line(str(faces[0 if card.face else 1].get("type_line") or ""))[1])


def flippable(card: CardInstance, info: CardInfo, printing: str | None = None) -> bool:
    """-- flip (wave 24C) -- 710.4: a flip card's permanent that isn't flipped yet (flipping is one-way). ``printing``: the card it
    copies (review 24C, 707.3: a copy of a flip card flips too)."""
    pid = printing or (card.card_id if card.token is None and not card.is_token else None)
    data = info.get(pid) if pid else None
    return data is not None and data.get("layout") == "flip" and len(data.get("faces") or []) >= 2 and not card.flipped


def half_from_data(data: dict[str, Any], face: int) -> Characteristics:
    """One half of a split card / adventure (its own name, cost, type and text), cached."""
    key = (str(data.get("id")) + "#half", face)
    hit = _printed_cache.get(key)
    if hit is None:
        hit = _printed_cache[key] = _from_card_data(data, face, half=True)
    return hit


def fused_from_data(data: dict[str, Any]) -> Characteristics | None:
    """-- static_other sweep (wave 16B) -- 702.102b / 709.4d: a fused split spell has the combined characteristics of its two halves:
    both names, the two mana costs (702.102c) added up, each card type and each ability of either half (the text of the left half
    first: 702.102d). None unless both halves have fuse."""
    faces = data.get("faces") or []
    if data.get("layout") != "split" or len(faces) != 2:
        return None
    key = str(data.get("id"))
    if key not in _fused_cache:
        a, b = half_from_data(data, 0), half_from_data(data, 1)
        fuse = [any(x.kind == "keywords" and "fuse" in x.keywords for x in h.abilities) for h in (a, b)]
        rest = [x for x in (*a.abilities, *b.abilities) if not (x.kind == "keywords" and x.keywords == ("fuse",))]
        _fused_cache[key] = replace(
            a, name=f"{a.name} // {b.name}", mana_cost=a.mana_cost + b.mana_cost, mana_value=a.mana_value + b.mana_value,
            supertypes=a.supertypes | b.supertypes, types=a.types | b.types, subtypes=a.subtypes | b.subtypes, colors=a.colors | b.colors,
            oracle_text=f"{a.oracle_text}\n{b.oracle_text}", abilities=tuple(replace(x, index=i) for i, x in enumerate(rest))) \
            if all(fuse) else None
    return _fused_cache[key]


def is_two_spell_card(card: CardInstance, info: CardInfo) -> bool:
    data = info.get(card.card_id) if card.card_id else None
    return bool(data and data.get("faces") and data.get("layout") in HALVES)


def as_cast(card: CardInstance, info: CardInfo, face: int | None, fused: bool = False) -> Characteristics:
    """The spell you cast from this card: for split cards and adventures, the half you chose
    (its own cost and type), otherwise the card as it is (after turning it to ``face``). ``fused``: both halves (702.102a)."""
    data = info.get(card.card_id) if card.card_id else None
    if fused and data and card.ability is None and not card.token and (both := fused_from_data(data)) is not None:
        return both
    if data and data.get("faces") and data.get("layout") in HALVES and card.ability is None and not card.token:
        return half_from_data(data, face or 0)
    return of(card.model_copy(update={"face": face}) if face is not None else card, info)


def of(card: CardInstance, info: CardInfo) -> Characteristics:
    """Current characteristics of a card instance (printed layer; see module docstring)."""
    sc = read_pass.for_info(info)
    if sc is not None and sc.state.cards.get(card.id) is card:  # -- hints speed (wave 29A) -- a card of the table a read-only pass is over: looked up once
        kept = sc.printed.get(id(card))
        if kept is not None and kept[0] is card:
            return kept[1]
        ch = _of(card, info)
        ch = merged_of(card, info, ch) if card.merged and not ch.face_down else ch
        sc.printed[id(card)] = (card, ch)
        return ch
    ch = _of(card, info)
    return merged_of(card, info, ch) if card.merged and not ch.face_down else ch


def merged_of(card: CardInstance, info: CardInfo, top: Characteristics) -> Characteristics:
    """-- merged permanents (wave 18D) -- a merged permanent has the characteristics of its topmost component (the instance's own card
    fields, 730.2a) and all abilities of every component (702.140e); text naming a lower card names the permanent (its card name is
    written as the top's). A melded permanent has only its combined back face's characteristics (712.8g) and the sum of its two front
    faces' mana values (202.3c, 712.8g)."""
    stubs = [CardInstance(id=p.id, card_id=p.card_id, name=p.name, owner=p.owner, controller=card.controller, zone=card.zone,
                          is_token=p.is_token, token=p.token) for p in card.merged]
    if card.melded:
        return replace(top, mana_value=sum(_of(s, info).mana_value for s in stubs))
    abilities = list(top.abilities)
    for stub in stubs[1:]:
        low = _of(stub, info)
        names = sorted({n for n in (low.name, low.name.split(",")[0].strip()) if len(n) >= 3 and n != top.name}, key=len, reverse=True)
        for ab in low.abilities:
            if ab.intrinsic:
                continue
            text = ab.text
            cost = ab.cost
            for n in names:
                text = re.sub(rf"(?<![\w']){re.escape(n)}(?![\w'])", top.name, text)
                cost = re.sub(rf"(?<![\w']){re.escape(n)}(?![\w'])", top.name, cost) if cost else cost
            abilities.append(replace(ab, index=len(abilities), text=text, cost=cost))
    return replace(top, abilities=tuple(abilities))


def _of(card: CardInstance, info: CardInfo) -> Characteristics:
    if card.ability is not None:
        return Characteristics(name=card.ability.source_name or "Ability", oracle_text=card.ability.text,
                               abilities=tuple(parse_abilities(card.ability.text, spell=True)), is_ability=True)
    if card.face_down and (card.zone.endswith(":battlefield") or card.zone == "stack"):
        return face_down_characteristics(card.face_down_kind, card.face_down_as)  # -- keyword actions & face-down (wave 3F) --
    if card.token is not None and not card.card_id:
        t = card.token
        if t.back is not None and card.face == 1:  # -- keyword actions & face-down (wave 3F) -- transformed (701.27, 111.10i)
            t = t.back
        supertypes, types, subtypes = parse_type_line(t.type_line)
        abilities = with_intrinsic_mana(parse_abilities(t.text, spell=bool(types & {"Instant", "Sorcery"})), subtypes)
        return Characteristics(
            name=t.name, supertypes=supertypes, types=types, subtypes=changeling(subtypes, abilities, t.name),
            colors=frozenset() if _devoid(abilities) else frozenset(t.colors), power=t.power, toughness=t.toughness, oracle_text=t.text, abilities=abilities,
            mana_cost=t.mana_cost, mana_value=mana_value(t.mana_cost),  # (wave 49D: 111.3, 202.3)
        )
    data = info.get(card.card_id) if card.card_id else None
    if data is None:
        # Unknown to the card database (a custom object): typeless, so the engine won't guess.
        return Characteristics(name=card.name or "")
    # -- flip (wave 24C) -- 710.2: a flipped permanent (status, 110.5: ``flipped``, the Kamigawa rotation) has the alternative characteristics
    return printed_from_data(data, 1 if card.flipped and data.get("layout") == "flip" and card.zone.endswith(":battlefield") else card.face)
