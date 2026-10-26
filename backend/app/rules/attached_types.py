"""-- attached events (wave 4L) -- An Aura's or Equipment's static that changes what the attached creature *is*,
researched against CR 2026-09-25 and the cards' Wizards rulings.

"Enchanted creature loses all abilities and is a green Elk creature with base power and toughness 3/3."
(Kenrith's Transformation), "Enchanted creature is an Insect artifact creature with base power and toughness 0/1
and has indestructible, and it loses all other abilities, card types, and creature types." (Darksteel Mutation),
"Enchanted creature is a Treefolk with base power and toughness 0/4 and loses all abilities." (Lignify),
"Equipped creature gets +10/+10 and loses flying." (Colossus Hammer), "Enchanted creature gets +4/+4, has flying
and first strike, and is an Angel in addition to its other types." (Angelic Destiny), "… is legendary".

The parts, by layer (613.1):

* layer 4 (613.1d): "is a [color] [creature types] creature" sets the card type to creature (205.1a: replacing the
  others; rulings on Frogify and Kenrith's Transformation: "it loses any other card types it has (such as
  artifact)", supertypes stay) and the creature types; without the word "creature" ("is a Treefolk") only the
  creature types are set; "[types] artifact creature" keeps the other card types (205.1b) unless the text says it
  loses them (Darksteel Mutation); "in addition to its other types" adds (205.1b); "legendary" adds a supertype.
* layer 5 (613.1e): a color word sets the colors (105.3).
* layer 6 (613.1f): "loses all [other] abilities" — every ability the object had before, printed or granted by an
  effect with an earlier timestamp (613.7), is gone; the static's own grants ("has indestructible") and later ones
  apply (rulings: "If the affected creature gains an ability after Kenrith's Transformation becomes attached to it,
  it will keep that ability"). Its static abilities stop applying too (Lignify ruling: "overwrites static
  abilities that come from the creature itself"), and so does its characteristic-defining P/T (7a, applied after
  layer 6). "loses flying": the keyword, in timestamp order with grants.
* layer 7b (613.4b): "with base power and toughness N/N".

Definition keys on a grant static (app/rules/statics.py; applied by app/rules/layers.py): ``lose_keywords``,
``lose_all``, ``layer4`` ({set_types, add_types, set_creature_types, add_subtypes, add_supertypes}), ``set_colors``.
Only an unconditional Aura's or Equipment's static carries them; anything else stays manual.
A terminal named clause sets the host's name in layer 3, before the remaining parts apply. A land type ("Enchanted land is an Island", wave 12D: ``layer4.set_land_types``) is set in layer 4 and, by
305.7, takes away the land's rules-text abilities (layers._derive, ``wipes``); it gains the types' mana abilities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.layers import Static

import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_BASICS = "Plains|Island|Swamp|Mountain|Forest"
_LOSE_TYPES = "\u0002lose-all-types"
_LOSE_LANDS = "\u0002lose-land-types"  # -- wave 110J -- "loses all land types and abilities" (Lithoform Blight)
# -- layers (wave 22A) -- "Enchanted permanent is a colorless Forest land." (Song of the Dryads), "… is a colorless land with "{T}: Add {C}"
# and loses all other card types and abilities." (Imprisoned in the Moon), "… is a colorless Food artifact with "…"" (Sugar Coat), "… is a
# Treasure artifact with "…"" (Minimus Containment): 205.1a sets the card type (the other types, and the subtypes that go with them, are
# gone) and the subtype of its kind (a land type: 305.7, an artifact type) and, 105.3, "colorless" its colors
_SET_TYPE = re.compile(r'^is (?:a|an) (?P<col>colorless )?(?:(?P<sub>[A-Z][a-z]+) )?(?P<ty>land|artifact)(?: with (?P<q>"[^"]+"))?$')
_IS = re.compile(r"^is (?:a|an) (?P<desc>.+?)(?: with base power and toughness (?P<p>\d+)/(?P<t>\d+))?"
                 r"(?P<add> in addition to its other (?P<also>colors_and_)?types)?$")


def protect(predicate: str) -> str:
    """Keep Darksteel Mutation's "it loses all other abilities, card types, and creature types" one piece."""
    predicate = re.sub(r"\bis an? (?:white|blue|black|red|green)(?: and (?:white|blue|black|red|green))+",
                       lambda m: m[0].replace(" and ", "\u0005"), predicate)
    predicate = re.sub(rf"\bis an? (?:{_BASICS})(?:(?:, and |, | and )(?:{_BASICS}))+",  # (wave 20A: "is a Mountain, Forest, and Plains": one piece)
                       lambda m: re.sub(r", and |, | and ", "\u0004", m[0]), predicate)
    predicate = predicate.replace("loses all land types and abilities", _LOSE_LANDS).replace("loses all other card types and abilities", _LOSE_TYPES)  # (wave 22A: the same, without the creature types)
    return predicate.replace("it loses all other abilities, card types, and creature types", _LOSE_TYPES) \
        .replace("its other colors and types", "its other colors_and_types")


def piece(text: str, extra: dict[str, Any]) -> bool | list[int] | None:
    """One predicate piece about layers 4-6 → recorded in ``extra`` (True; a base P/T [p, t] to set), False when it
    is one of these but not read, None when it's not one of these."""
    text = re.sub(r"^it (?=loses )", "", text).replace("\u0004", ", ").replace("\u0005", " and ")
    if (m := _SET_TYPE.fullmatch(text)) is not None:
        return _set_type(m, extra)
    if text == _LOSE_LANDS:  # 305.7, 613.1d: no land types (so no intrinsic mana abilities), and no abilities
        extra["lose_all"] = True
        extra["_lose_lands"] = True
        _layer4(extra)["set_land_types"] = []
        return True
    if text == _LOSE_TYPES:
        extra["lose_all"] = True
        extra["_lose_types"] = True
        return True
    if text in ("loses all abilities", "loses all other abilities"):
        extra["lose_all"] = True
        return True
    m = re.fullmatch(r"loses (?P<kw>[a-z ]+)", text)
    if m:
        from app.rules.statics import GRANTABLE_KEYWORDS

        if m["kw"] not in GRANTABLE_KEYWORDS:
            return False
        extra.setdefault("lose_keywords", []).append(m["kw"])
        return True
    if text == "is every basic land type in addition to its other types":
        from app.rules.type_statics import BASIC

        _layer4(extra).setdefault("add_subtypes", []).extend(BASIC)
        return True
    # -- land types set (wave 12D) -- "Enchanted land is a Swamp." / "is a Mountain, Forest, and Plains." (305.7, 613.1d)
    m = re.fullmatch(rf"is an? (?P<t>(?:{_BASICS})(?:(?:, | and |, and )(?:{_BASICS}))*)", text)  # (wave 20A: the alternation grouped)
    if m:
        if "set_land_types" in _layer4(extra):
            return False
        _layer4(extra)["set_land_types"] = re.findall(_BASICS, m["t"])
        return True
    if text in ("is legendary", "is snow"):  # (wave 20A: "Enchanted land is snow", 205.4a: a supertype added)
        _layer4(extra).setdefault("add_supertypes", []).append(text[3:].capitalize())
        return True
    if text in ("is every creature type", "is all creature types"):  # (205.3m: "all creature types")
        _layer4(extra)["all_creature_types"] = True
        return True
    if text == "is the chosen type":  # -- chosen filters (wave 53B) -- "Enchanted land is the chosen type." (Phantasmal Terrain): the basic land type its Aura chose as it entered, 305.7
        if "set_land_types" in _layer4(extra):
            return False
        _layer4(extra)["set_land_types"] = ["@land"]
        return True
    if text == "is the chosen color":  # (Shimmerwilds Growth) 105.3: its colors become the one its Aura chose as it entered
        if "set_colors" in extra:
            return False
        extra["set_colors"] = ["@color"]
        return True
    m = re.fullmatch(r"is (?P<c>white|blue|black|red|green|colorless)", text)
    if m:  # layer 5: "Enchanted creature gets +3/+1 and is black." (105.3: its colors become that)
        if "set_colors" in extra:
            return False
        extra["set_colors"] = [] if m["c"] == "colorless" else [_COLORS[m["c"]]]
        return True
    if not text.startswith("is "):
        return None
    m = _IS.fullmatch(text)
    if m is None:
        return False
    return _desc(m, extra)


def _set_type(m: re.Match[str], extra: dict[str, Any]) -> bool:
    from app.rules.layers import ARTIFACT_TYPES

    layer4 = _layer4(extra)
    if "set_types" in layer4 or "set_colors" in extra:
        return False
    sub, land = m["sub"], m["ty"] == "land"
    if sub is not None and not (sub in re.findall(_BASICS, sub) if land else sub in ARTIFACT_TYPES):
        return False
    layer4["set_types"] = ["Land" if land else "Artifact"]
    if sub is not None:
        layer4["set_land_types" if land else "set_artifact_types"] = [sub]
    if m["col"]:
        extra["set_colors"] = []
    if m["q"]:
        from app.rules.scripts import granted_ability

        text = m["q"][1:-1].rstrip(",")  # (the comma after the last word of a quote is Oracle punctuation)
        text = text if text[-1] in ".)" else text + "."
        if granted_ability(text) is None:
            return False
        extra.setdefault("_grants", []).append(text)
    extra["_typeset"] = True
    return True


def _layer4(extra: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = extra.setdefault("layer4", {})
    return out


def _desc(m: re.Match[str], extra: dict[str, Any]) -> bool | list[int]:
    from app.rules.creature_types import CREATURE_TYPES

    words = m["desc"].split()
    legendary = bool(words) and words[0] == "legendary"
    words = words[1:] if legendary else words
    colors: list[str] | None = None
    if words and (words[0] in _COLORS or words[0] == "colorless"):
        colors = [] if words[0] == "colorless" else [_COLORS[words[0]]]
        words = words[1:]
        while len(words) > 1 and words[0] == "and" and words[1] in _COLORS and colors:
            colors.append(_COLORS[words[1]])
            words = words[2:]
    subs: list[str] = []
    while words and words[0] in CREATURE_TYPES:
        subs.append(words.pop(0))
    artifact = bool(words) and words[0] == "artifact"
    words = words[1:] if artifact else words
    creature = words == ["creature"]
    if words and not creature:
        return False  # ("a colorless Forest land", "a Treasure artifact": not read)
    layer4 = _layer4(extra)
    if legendary:
        layer4.setdefault("add_supertypes", []).append("Legendary")
    if m["add"] and creature and m["p"] and not (artifact or legendary) and (subs or colors is None):  # (wave 27A: Ensoul Artifact, no creature type)
        # -- Zendikon (wave 16F) -- "Enchanted land is a 3/3 black Ooze creature. It's still a land.": the land becomes a creature of
        # that type with that base P/T (and that color) and stays a land (205.1b, 613.1d); only a land (see ``consistent``)
        layer4.setdefault("add_types", []).append("Creature")
        layer4.setdefault("add_subtypes", []).extend(subs)
        if colors is not None:
            extra["set_colors"] = colors
        extra["_animate"] = True
        return [int(m["p"]), int(m["t"])]
    if m["add"] and m["p"] and creature and artifact and subs and colors is None and not legendary:
        # -- Unable to Scream (wave 110D) -- "is a Toy artifact creature with base power and toughness 0/2 in addition to its other types": the
        # subtype and the artifact type are added (205.1b), the base P/T is set (613.4b); a creature stays what it was
        layer4.setdefault("add_types", []).append("Artifact")
        layer4.setdefault("add_subtypes", []).extend(subs)
        return [int(m["p"]), int(m["t"])]
    if m["add"]:
        # "is an Angel in addition to its other types"; "is an artifact in addition to its other types" (205.1b);
        # "is a black Zombie in addition to its other colors and types" (105.3: a color added)
        if (colors is not None) != bool(m["also"]) or m["p"] or creature or not (subs or legendary or artifact):
            return False
        layer4.setdefault("add_subtypes", []).extend(subs)
        if artifact:
            layer4.setdefault("add_types", []).append("Artifact")
        if colors:
            extra["add_colors"] = colors
        return True
    if not subs or (artifact and not creature):
        return False
    if "set_creature_types" in layer4:
        return False
    layer4["set_creature_types"] = subs
    if creature:
        layer4["set_types"] = ["Artifact", "Creature"] if artifact else ["Creature"]
        layer4["_artifact"] = artifact
    if colors is not None:
        extra["set_colors"] = colors
    return [int(m["p"]), int(m["t"])] if m["p"] else True


def consistent(extra: dict[str, Any], kind: str | None) -> bool:
    """The parts make one effect the engine applies (and the private notes are resolved)."""
    lose_types = extra.pop("_lose_types", False)
    if extra.pop("_lose_lands", False):  # (wave 110J) only an Aura's "Enchanted land loses all land types and abilities and has ..."
        return kind == "land" and set(extra) == {"layer4", "lose_all"} and extra["layer4"] == {"set_land_types": []}
    if extra.pop("_typeset", False):  # -- layers (wave 22A) -- an Aura that sets its host's card type, whatever it is: nothing else to read
        return not set(extra) - {"layer4", "set_colors", "lose_all"}
    if kind == "permanent" and set(extra) == {"lose_all"}:  # (wave 22A) "Enchanted permanent loses all abilities" (613.1f)
        return True
    if extra.pop("_animate", False):
        return kind in ("land", "artifact") and set(extra) <= {"layer4", "set_colors"} and not lose_types  # (wave 27A: Ensoul Artifact)
    if set(extra) == {"set_colors"} and extra["set_colors"] == ["@color"]:  # -- chosen filters (wave 53B) -- "Enchanted land is the chosen color." (Shimmerwilds Growth): 105.3, 613.1e: any permanent has a color
        return True
    layer4 = extra.get("layer4") or {}
    if "set_land_types" in layer4:  # -- land types set (wave 12D) -- only an Aura's "Enchanted land is a Swamp." on its own
        return kind == "land" and set(extra) == {"layer4"} and set(layer4) == {"set_land_types"} and not lose_types
    if kind == "land" and set(extra) == {"layer4"} and set(layer4) == {"add_subtypes"}:
        from app.rules.type_statics import BASIC

        # 305.7: adding basic land types preserves other subtypes and abilities.
        return bool(layer4["add_subtypes"]) and set(layer4["add_subtypes"]) <= set(BASIC) and not lose_types
    artifact = layer4.pop("_artifact", False)
    if lose_types and layer4.get("set_types") is None:
        return False  # ("loses all other card types" with no type it is)
    if artifact and not lose_types:
        layer4["add_types"] = layer4.pop("set_types")  # 205.1b: "[creature type] artifact creature" keeps the others
    if layer4 and not layer4.get("set_types") and not layer4.get("add_types") and kind != "creature" \
            and set(layer4) != {"add_supertypes"}:
        return False  # (creature types for something that may not be a creature)
    if kind != "creature" and (extra.get("lose_all") or extra.get("lose_keywords") or "set_colors" in extra
                               or "add_colors" in extra or layer4.get("set_types") or layer4.get("add_types")
                               or layer4.get("all_creature_types")):
        return False
    if not layer4:
        extra.pop("layer4", None)
    return True


# -- applying (app/rules/layers.py) ------------------------------------------------------------------------------
def layer45(state: GameState, card: CardInstance, table: list[Static]) -> list[tuple[float, dict[str, Any]]]:
    """The type- and color-changing statics of what is attached to ``card`` (timestamp, definition): applied to it
    whatever it is right now (Frogify ruling: an Aura on a permanent that is a creature only for a while keeps it a
    creature)."""
    from app.rules import (
        wave110a_paper,  # -- wave 110A -- Psychic Paper: the name and creature type its Equipment last chose
    )

    return [(st.seq, wave110a_paper.layer45_definition(state, st.source, st.definition) if st.definition.get("paper110a") else st.definition) for st in table
            if st.gate is None and st.definition.get("who") == "attached"
            and (st.definition.get("layer4") or "set_colors" in st.definition or "add_colors" in st.definition or "set_name" in st.definition
                 or st.definition.get("paper110a"))
            and state.cards[st.source].attached_to == card.id]


def wipes(state: GameState, table: list[Static]) -> dict[str, tuple[int, int, int]]:
    """Permanents that lose all abilities (card id → the ordering key of the latest such effect, 613.7): by a
    resolved effect (``remove_abilities``) or by the static of what is attached to them."""
    r = state.rules
    out: dict[str, tuple[int, int, int]] = {}
    if r is None:
        return out
    by_object = {r.object_id(cid): cid for cid, c in state.cards.items() if c.zone.endswith(":battlefield")}
    for e in r.effects:
        if e.layer == "6" and e.remove_abilities:
            for oid in e.affected:
                cid = by_object.get(oid)
                if cid is not None:
                    out[cid] = max(out.get(cid, (-1, 0, 0)), (e.object_seq, 1, e.timestamp))
        elif e.layer == "4" and e.set_land_types is not None:  # -- land types set (wave 12D) -- 305.7: its own abilities are
            for oid in e.affected:  # gone, whatever it is granted (layer 6) still applies: the earliest possible key
                cid = by_object.get(oid)
                if cid is not None:
                    out.setdefault(cid, (-1, 0, 0))
    for st in table:
        if (st.definition.get("layer4") or {}).get("set_land_types") and st.gate is None:  # -- land types set (wave 12D) --
            host = state.cards[st.source].attached_to  # 305.7: the enchanted land's own abilities are gone
            if host is not None and host in state.cards:
                out.setdefault(host, (-1, 0, 0))
        if st.definition.get("lose_all") and st.gate is None:
            host = state.cards[st.source].attached_to
            if host is not None and host in state.cards:
                out[host] = max(out.get(host, (-1, 0, 0)), wipe_key(st))
    return out


def wipe_key(st: Static) -> tuple[int, int, int]:
    """A static "loses all abilities"'s place in timestamp order: just before the source's other effects, so its
    own grants ("has indestructible") and those of the same source apply after it."""
    return (st.seq, -1, 0)
