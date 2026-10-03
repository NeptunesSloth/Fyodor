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
Only an unconditional Aura's or Equipment's static carries them; anything else stays manual. A land type
("Enchanted land is an Island": 305.7 takes away its rules-text abilities), a name or a chosen color isn't read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.layers import Static

import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_LOSE_TYPES = "\u0002lose-all-types"
_IS = re.compile(r"^is (?:a|an) (?P<desc>.+?)(?: with base power and toughness (?P<p>\d+)/(?P<t>\d+))?"
                 r"(?P<add> in addition to its other (?P<also>colors_and_)?types)?$")


def protect(predicate: str) -> str:
    """Keep Darksteel Mutation's "it loses all other abilities, card types, and creature types" one piece."""
    return predicate.replace("it loses all other abilities, card types, and creature types", _LOSE_TYPES) \
        .replace("its other colors and types", "its other colors_and_types")


def piece(text: str, extra: dict[str, Any]) -> bool | list[int] | None:
    """One predicate piece about layers 4-6 → recorded in ``extra`` (True; a base P/T [p, t] to set), False when it
    is one of these but not read, None when it's not one of these."""
    text = re.sub(r"^it (?=loses )", "", text)
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
    if text == "is legendary":
        _layer4(extra).setdefault("add_supertypes", []).append("Legendary")
        return True
    if text in ("is every creature type", "is all creature types"):  # (205.3m: "all creature types")
        _layer4(extra)["all_creature_types"] = True
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
    layer4 = extra.get("layer4") or {}
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
def layer45(state: GameState, card: CardInstance, table: list[Static]) -> list[tuple[int, dict[str, Any]]]:
    """The type- and color-changing statics of what is attached to ``card`` (timestamp, definition): applied to it
    whatever it is right now (Frogify ruling: an Aura on a permanent that is a creature only for a while keeps it a
    creature)."""
    return [(st.seq, st.definition) for st in table
            if st.gate is None and st.definition.get("who") == "attached"
            and (st.definition.get("layer4") or "set_colors" in st.definition or "add_colors" in st.definition)
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
    for st in table:
        if st.definition.get("lose_all") and st.gate is None:
            host = state.cards[st.source].attached_to
            if host is not None and host in state.cards:
                out[host] = max(out.get(host, (-1, 0, 0)), wipe_key(st))
    return out


def wipe_key(st: Static) -> tuple[int, int, int]:
    """A static "loses all abilities"'s place in timestamp order: just before the source's other effects, so its
    own grants ("has indestructible") and those of the same source apply after it."""
    return (st.seq, -1, 0)
