"""-- type statics (wave 5F) -- static abilities that add types to a group of objects, researched against CR 2026-09-25.

* "Each land is a Swamp in addition to its other land types." (Urborg, Tomb of Yawgmoth; Yavimaya, Cradle of Growth;
  Blanket of Night), "Lands you control are every basic land type in addition to their other types." (Dryad of the
  Ilysian Grove, Prismatic Omen, Leyline of the Guildpact), "Nontoken creatures you control are Forest lands in
  addition to their other types." (Ashaya, Soul of the Wild): layer 4 (613.1d), type-changing effects that ADD types
  (205.1b). 305.7: a land that gains a land type in addition to its own keeps its land types and rules text and gains
  the new types' mana abilities; 305.6: an object with the land card type and a basic land type has the intrinsic
  "{T}: Add [mana]." (``with_gained_mana``: a land type that is SET — Blood Moon — is not read here.)
* "Creatures you control are every creature type. The same is true for creature spells you control and creature
  cards you own that aren't on the battlefield." (Maskwood Nexus, 205.3m): the static says it works outside the
  battlefield too (611.3: a static of a permanent applies to the objects it names, in any zone it names).
* -- layers (wave 22A) -- the group statics of layers 4-6: "Nonbasic lands are Mountains." (Blood Moon; 305.7),
  "All creatures lose all abilities and have base power and toughness 1/1." (Humility), "Each other non-Aura enchantment
  is a creature in addition to its other types and has base power and base toughness each equal to its mana value."
  (Opalescence), "All permanents are colorless.", "All nonland permanents are legendary.", "Forests you control are 1/1
  green Elf creatures that are still lands.": the definition carries ``layered`` and the parts by layer; app/rules/
  group_layers.py solves them against each other (613.6, 613.8) and ``layers._derive`` applies them.

A static line is the definition :func:`parse` returns (a static "grant", ``layers._hits`` reads the layer 6/7 parts) carrying
``layered``, ``layer4`` (``{"add_types": […], "add_subtypes": […], "set_land_types": […], "add_supertypes": […], …}``, the
attached-object format ``layers._layer4`` reads), ``set_colors`` / ``add_colors`` / ``chosen_color``, ``lose_all`` / ``keep_mana``,
``base`` / ``base_mv`` and ``everywhere`` (the cards and spells outside the battlefield it names). Anything else stays unsupported.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics

BASIC = ("Plains", "Island", "Swamp", "Mountain", "Forest")  # 205.3i
_BASIC_RE = "|".join(BASIC)
_EACH_LAND = re.compile(rf"^Each land is an? (?P<t>{_BASIC_RE}) in addition to its other land types\.$")
_EVERY_BASIC = re.compile(r"^(?P<s>Lands you control) are every basic land type in addition to their other types\.$")
_ARE_LANDS = re.compile(rf"^(?P<s>(?:Nontoken )?creatures you control) are (?P<t>{_BASIC_RE}) lands in addition to "
                        r"their other types\.$")
# -- static_other sweep (wave 17C) -- "Artifacts you control are Foods in addition to their other types and have "{2}, {T}, Sacrifice this
# artifact: You gain 3 life."" (Ragost) / "Other creatures are Food artifacts in addition to their other types and have "..."" (Ygra) /
# "Nontoken artifacts you control are lands in addition to their other types." (Toph): the same layer-4 addition (613.1d, 205.1b) for any
# group on the battlefield, the types lower case plural ("artifacts") and the subtypes capitalised ("Foods"), then layer 6 grants
_ARE_ALSO = re.compile(r"^(?P<during>During your turn, )?(?P<s>[A-Za-z0-9+/',\- ]+?)(?: have base power and toughness (?P<p>\d+)/(?P<t>\d+)(?:, have (?P<kw0>[a-z]+),)? and)? (?:are|is) (?:an? )?"  # (wave 26D: "is a Wall", "…4/4, have flying, and are Angels")
                       r"(?P<what>[A-Za-z ]+?) in addition to (?:their|its) other (?:creature )?types"
                       r"(?: and (?:have|has) (?P<kw>[a-z]+)\.|"  # (wave 26D: "and has defender": a keyword, layer 6)
                       r" and have (?P<q>\"[^\"]+\")(?P<eq>(?:,? (?:and )?equip(?: [A-Z][a-z]+)? \{[^}]+\})+)?\.?"  # (wave 25D: + equip costs, and a period after the quote)
                       r"|\.(?P<same> The same is true for [^.]+\.)?)$")  # (Kudo, Graaz: base P/T, 7b; Roshan: the Maskwood sentence)
_GRANT_AND_TYPE = re.compile(r"^(?P<s>(?:Each|All) [A-Za-z' -]+?(?: you control)?(?: but don't own)?|[A-Z][A-Za-z' -]+? you control(?: but don't own)?) "
                             r"(?P<grant>(?:gets?|ha(?:s|ve)) [^\"]+?),? and (?:is|are) (?:an? )?(?P<what>[A-Z][A-Za-z ]+?) in addition to (?:its|their) other types\.$")
_TYPE_WORDS = {"artifacts": "Artifact", "creatures": "Creature", "enchantments": "Enchantment", "lands": "Land"}
MASKWOOD = ("Creatures you control are every creature type. The same is true for creature spells you control and "
            "creature cards you own that aren't on the battlefield.")


# -- layers (wave 22A) -- the cards and spells the static also names ("The same is true for …", 611.3): who may own them, which types
# they have to have; the Maskwood Nexus sentence is one, Encroaching Mycosynth's and Celestial Dawn's the others
_SAME = {
    "The same is true for creature spells you control and creature cards you own that aren't on the battlefield.":
        {"own": True, "types": ["Creature"], "not_types": [], "permanent": False},
    "The same is true for permanent spells you control and nonland permanent cards you own that aren't on the battlefield.":
        {"own": True, "types": [], "not_types": ["Land"], "permanent": True},
    "The same is true for spells you control and nonland cards you own that aren't on the battlefield.":
        {"own": True, "types": [], "not_types": ["Land"], "permanent": False},
}
_SAME_CREATURES = list(_SAME.values())[0]
_EVERYWHERE = {"own": False, "types": [], "not_types": [], "permanent": False}
_COLOR_CODES = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_ALL_COLORS = ["W", "U", "B", "R", "G"]
_LAND_PLURALS = {"Plains": "Plains", "Islands": "Island", "Swamps": "Swamp", "Mountains": "Mountain", "Forests": "Forest"}


def _definition(subject: str, layer4: dict[str, Any] | None, *, everywhere: dict[str, Any] | None = None, during: bool = False,
                base: list[int] | None = None, grants: list[str] | None = None, keywords: list[str] | None = None,
                **parts: Any) -> dict[str, Any] | None:
    """A layered group static (``group_layers``): its subject (a group on the battlefield) and the parts by layer."""
    from app.rules.statics import UNION, _subject
    from app.rules.statics import _definition as grant

    who, _kind = _subject(re.sub(r"\band all ", "and ", subject), plural=True)
    if who is None or who in ("self", "attached") or who.startswith(UNION):
        return None
    out = {**grant(who, None, [{"static": "your_turn"}] if during else [], base=base, grants=grants, keywords=keywords),
           "layered": True, **parts}
    if layer4:
        out["layer4"] = layer4
    if everywhere is not None:
        out["everywhere"] = everywhere
    return out


def _everywhere(subject: str, same: str) -> dict[str, Any] | None:
    """What a static that says "The same is true for …" also names (None: not worded so)."""
    from app.rules import selectors

    where = _SAME.get(same)
    sel = selectors.parse(subject)
    if where is None or sel is None or sel.controller != "you" or (where["types"] and list(sel.types) != where["types"]):
        return None
    return {**where, "not_types": list(sel.not_types) if not where["types"] else []}


def parse(text: str) -> dict[str, Any] | None:
    """One static line (the card's own name written as ~) → its definition, or None."""
    text = re.sub(r"^[A-Z][A-Za-z' -]+ — ", "", text)  # (an ability word, 207.2c, has no rules meaning: "Hypertoxic Miasma — …")
    if (m := _EACH_LAND.fullmatch(text)) is not None:
        return _definition("lands", {"add_subtypes": [m["t"]]})
    if (m := _EVERY_BASIC.fullmatch(text)) is not None:
        return _definition(m["s"], {"add_subtypes": list(BASIC)})
    if (m := _ARE_LANDS.fullmatch(text)) is not None:
        return _definition(m["s"], {"add_types": ["Land"], "add_subtypes": [m["t"]]})
    if (m := _ARE_ALSO.fullmatch(text)) is not None and (found := _also(m)) is not None:
        return found
    if (m := _GRANT_AND_TYPE.fullmatch(text)) is not None:
        # -- static_other (wave 42A) -- "Each creature you control but don't own gets +2/+2, has menace and deathtouch, and is a Pirate in addition to its other
        # types." (Don Andres): the grant (layers 6-7) and the layer-4 type addition (205.1b, 613.1d) of ONE group, read as the two sentences they would be
        from app.rules import statics

        grant = statics.parse(f"{m['s']} {m['grant']}.")
        typed = parse(f"{m['s']} are {m['what']} in addition to their other types.")
        if grant is None or typed is None or grant["who"] != typed["who"] or grant.get("layered") or not typed.get("layer4"):
            return None
        return {**grant, "layered": True, "layer4": typed["layer4"]}
    if (found := _layered(text)) is not None:
        return found
    if re.fullmatch(r"~ is also an? [A-Z][A-Za-z]*(?:(?:, | and |, and )[A-Z][A-Za-z]*)*\.", text) \
            or re.fullmatch(r"~ is all colors\.(?: This ability doesn't affect its color identity\.)?", text):
        return {"kind": "static", "static": "cda", "effects": []}  # -- static_other sweep (wave 17C) -- characteristics.changeling / all_colors
    if text == "~ is every creature type.":  # (Mistform Ultimus: a characteristic-defining ability, 604.3 —
        return {"kind": "static", "static": "cda", "effects": []}  # characteristics.changeling applies it in every zone)
    if text == MASKWOOD:
        return _definition("creatures you control", {"all_creature_types": True}, everywhere=_SAME_CREATURES)
    return None


# -- layers (wave 22A) -- the group statics of layers 4-6 that change what the objects are (CR 305.7, 613.1d-f, 613.4b)
_SUBJ = r"(?P<s>(?:All |Each )?[A-Za-z0-9+/' -]+?(?: and (?:all )?[A-Za-z' -]+?)?(?: you control)?)"
_LAND_SET = re.compile(rf"^{_SUBJ} (?:is|are) (?:an? )?(?P<t>Plains|Islands?|Swamps?|Mountains?|Forests?)\.$")
_LOSE_ALL = re.compile(rf"^{_SUBJ} lose all (?P<other>other )?abilities(?P<mana> except mana abilities)?"
                       r"(?: and have base power and toughness (?P<p>\d+)/(?P<t>\d+))?\.$")
_HAVE_LOSE = re.compile(rf"^{_SUBJ} have (?P<q>\"[^\"]+\") and lose all other abilities\.$")
_COLOR = re.compile(r"^(?P<during>During your turn, )?(?P<s>[A-Za-z' ,-]+?) (?:is|are) "
                    r"(?P<c>colorless|all colors|white|blue|black|red|green|the chosen color)"
                    r"(?P<add> in addition to (?:its|their) other colors)?\.(?P<same> The same is true for .+)?$")
_LEGENDARY = re.compile(rf"^{_SUBJ} (?:is|are) legendary\.$")
_ANIMATE_MV = re.compile(r"^(?P<s>Each [A-Za-z' -]+?) is an? (?P<ty>(?:(?:artifact|enchantment|land) )*creature)"
                         r"(?P<add> in addition to its other types and has base power and base toughness| with power and toughness)"
                         r" each equal to its mana value\.$")
_STILL_LANDS = re.compile(rf"^{_SUBJ} are (?P<p>\d+)/(?P<t>\d+) (?:(?P<col>white|blue|black|red|green) )?(?P<subs>(?:[A-Z][a-z]+ )*)"
                          r"creatures(?: with (?P<kw>[a-z ]+))?(?: that are still lands\.|\. They're still lands\.)$")
_LIFE_AND_LIMB = re.compile(r"^(?P<s>All [A-Z][a-z]+ and all [A-Z][a-z]+) are (?P<p>\d+)/(?P<t>\d+) (?P<col>white|blue|black|red|green) "
                            r"(?P<sub>[A-Z][a-z]+) creatures and (?P<land>[A-Z][a-z]+) lands in addition to their other types\.$")


def _layered(text: str) -> dict[str, Any] | None:
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.scripts import granted_ability
    from app.rules.statics import GRANTABLE_KEYWORDS

    if (m := re.fullmatch(r"As long as (?P<cond>[^,]+), (?P<rest>[a-zA-Z].+)", text)) is not None:  # 611.3a: read as the table is solved
        from app.rules import statics as grammar

        cond, found = grammar.condition(m["cond"]), _layered(m["rest"][0].upper() + m["rest"][1:])
        if cond is None or found is None or found["conditions"] or not _count_of(cond, found):
            return None
        return {**found, "conditions": [cond]}

    if (m := _LAND_SET.fullmatch(text)) is not None:  # 305.7: the land types are set (never the card types)
        found = _definition(m["s"], {"set_land_types": [_LAND_PLURALS.get(m["t"], m["t"].rstrip("s") if m["t"] != "Plains" else m["t"])]})
        return found if found is not None and _lands(found) else None
    if (m := _LOSE_ALL.fullmatch(text)) is not None:  # 613.1f
        return _definition(m["s"], None, base=[int(m["p"]), int(m["t"])] if m["p"] else None, lose_all=True,
                           **({"keep_mana": True} if m["mana"] else {}))  # type: ignore[arg-type]
    if (m := _HAVE_LOSE.fullmatch(text)) is not None:  # (Toxicrene) 613.1f: the abilities it grants come after it takes them away
        q = m["q"][1:-1]
        q = q if q[-1] in ".)" else q + "."
        return _definition(m["s"], None, grants=[q], lose_all=True) if granted_ability(q) is not None else None
    if (m := _COLOR.fullmatch(text)) is not None:  # 613.1e, 105.3
        everywhere = _EVERYWHERE if m["s"] == "All cards that aren't on the battlefield, spells, and permanents" else None
        subject = "permanents" if everywhere is not None else m["s"]
        if m["same"]:
            everywhere = _everywhere(subject, m["same"].strip())
            if everywhere is None:
                return None
        if m["c"] == "the chosen color":
            parts: dict[str, Any] = {"chosen_color": True, "add_colors": []} if m["add"] else {"chosen_color": "set", "set_colors": []}  # (wave 53B: Shifting Sky, 105.3)
        else:
            codes = [] if m["c"] == "colorless" else _ALL_COLORS if m["c"] == "all colors" else [_COLOR_CODES[m["c"]]]
            parts = {"add_colors": codes} if m["add"] else {"set_colors": codes}
        return _definition(subject, None, everywhere=everywhere, during=bool(m["during"]), **parts) if parts else None
    if (m := _LEGENDARY.fullmatch(text)) is not None:  # 205.4: a supertype added
        return _definition(m["s"], {"add_supertypes": ["Legendary"]})
    if (m := re.fullmatch(r"(?P<s>Each (?:nonland )?(?P<k>land|creature) with an? [a-z]+ counter on it) is every (?P=k) type"  # (wave 26D) 205.3i (Omo)
                          r"(?P<add> in addition to its other types)?\.", text)) is not None and bool(m["add"]) == (m["k"] == "land"):
        from app.rules.layers import LAND_TYPES

        return _definition(m["s"], {"add_subtypes": sorted(LAND_TYPES)} if m["k"] == "land" else {"all_creature_types": True})
    if (m := re.fullmatch(r"(?P<s>Creatures you control|Each creature you control|Lands you control|Vehicle creatures you control) (?:is|are) the chosen (?:creature )?type"  # (wave 26D; wave 53B: Lifecraft Engine, Conspiracy)
                          r"(?P<add> in addition to (?:its|their) other (?:creature )?types)?\.(?P<same> The same is true for [^.]+\.)?", text)) is not None \
            and (m["add"] or (m["s"] == "Creatures you control" and m["same"])):
        # 205.1b: the creature type (Xenograft, Arcane Adaptation) or basic land type (Realmwright) its source chose as it entered (614.12a); -- chosen filters (wave 53B) -- without
        # "in addition" (Conspiracy, 205.1a) it is the only creature type the creatures, creature spells and creature cards have (group_layers.with_chosen)
        everywhere = _everywhere(m["s"], m["same"].strip()) if m["same"] else None
        if m["same"] and everywhere is None:
            return None
        kind = "land" if m["s"].startswith("Lands") else "creature" if m["add"] else "creature_set"
        found = _definition(m["s"], {"add_subtypes": [], "chosen_type": kind}, everywhere=everywhere)
        return {**found, "chosen_type": found["layer4"]["chosen_type"]} if found is not None else None
    if text == "Each creature card in your graveyard has the chosen creature type in addition to its other types.":  # -- chosen filters (wave 53B) --
        # Ashes of the Fallen: 205.1b, 611.3: only the creature cards in the controller's graveyard (no battlefield member: the selector names the graveyard)
        from app.rules import selectors
        from app.rules.statics import _definition as grant

        who = selectors.parse("creature cards in your graveyard")
        if who is None:
            return None
        return {**grant(who.key(), None, []), "layered": True, "layer4": {"add_subtypes": [], "chosen_type": "creature"}, "chosen_type": "creature",
                "everywhere": {"own": True, "types": ["Creature"], "not_types": [], "permanent": False, "zones": ["graveyard"]}}
    if (m := re.fullmatch(rf"{_SUBJ} (?:is|are) snow\.", text)) is not None:  # (wave 26D) 205.4: the supertype snow is added (Rimefeather Owl)
        return _definition(m["s"], {"add_supertypes": ["Snow"]})
    if (m := _ANIMATE_MV.fullmatch(text)) is not None:  # Opalescence, March of the Machines: 205.1b ("an artifact creature" keeps the
        # object's other types and subtypes too), 613.4b
        return _definition(m["s"], {"add_types": [w.capitalize() for w in m["ty"].split()]}, base_mv=True)
    if (m := _STILL_LANDS.fullmatch(text)) is not None:  # Nature's Revolt, Kormus Bell, Ambush Commander, Natural Emergence
        subs = m["subs"].split()
        if any(w not in CREATURE_TYPES for w in subs) or (m["kw"] and m["kw"] not in GRANTABLE_KEYWORDS):
            return None
        return _definition(m["s"], {"add_types": ["Creature"], "add_subtypes": subs}, base=[int(m["p"]), int(m["t"])],
                           keywords=[m["kw"]] if m["kw"] else None, **({"set_colors": [_COLOR_CODES[m["col"]]]} if m["col"] else {}))  # type: ignore[arg-type]
    if (m := _LIFE_AND_LIMB.fullmatch(text)) is not None:  # 205.1b: creature and land types added, the color set
        if m["sub"] not in CREATURE_TYPES or m["land"] not in BASIC:
            return None
        return _definition(m["s"], {"add_types": ["Creature", "Land"], "add_subtypes": [m["sub"], m["land"]]},
                           base=[int(m["p"]), int(m["t"])], set_colors=[_COLOR_CODES[m["col"]]])
    return None


def _count_of(cond: dict[str, Any], found: dict[str, Any]) -> bool:
    """May this condition gate the static? It is read as the table is solved, so it must not depend on what the static itself changes:
    a count of objects of types the static leaves alone ("five or more enchantments" for a static that makes them creatures), or a
    condition that reads no characteristics at all (``statics._layer4_safe``)."""
    from app.rules import selectors
    from app.rules.statics import _layer4_safe

    value = cond.get("value")
    if cond.get("static") is not None or not isinstance(value, dict) or set(value) != {"count"}:
        return _layer4_safe(cond)
    sel = selectors.from_key(value["count"])
    l4 = found.get("layer4") or {}
    changed = {*l4.get("add_types", ()), *l4.get("set_types", ())}
    return bool(sel.types) and not set(sel.types) & changed and not (sel.subtypes or sel.colors or sel.not_types or sel.not_subtypes) \
        and not (found.get("lose_all") or "set_colors" in found or "add_colors" in found or l4.get("set_land_types"))


def _lands(d: dict[str, Any]) -> bool:
    """Does the subject name lands (305.7: an effect that sets land types: lands, or a land type)?"""
    from app.rules import selectors

    sel = selectors.from_key(d["who"])
    return sel.types == ("Land",) or (not sel.types and bool(sel.subtypes) and set(sel.subtypes) <= set(BASIC))


def _singular(word: str, known: set[str] | frozenset[str]) -> str | None:
    """-- type statics (wave 42A) -- the type a plural subtype word names ("Pirates", "Mercenaries", "Elves"), or None."""
    from app.rules.protection import _PLURALS

    for one in (_PLURALS.get(word.lower()), word[:-1], word[:-3] + "y" if word.endswith("ies") else None, word[:-2] if word.endswith("es") else None):  # (wave 50G: "Heroes")
        if one and word.endswith("s") and one in known:
            return one
    return None


def _also(m: re.Match[str]) -> dict[str, Any] | None:
    from app.rules.creature_types import CREATURE_TYPES
    from app.rules.layers import ARTIFACT_TYPES, ENCHANTMENT_TYPES, LAND_TYPES
    from app.rules.scripts import granted_ability

    types: list[str] = []
    subtypes: list[str] = []
    for w in m["what"].split(" "):
        if w in _TYPE_WORDS:
            types.append(_TYPE_WORDS[w])
        elif w[:1].isupper() and (one := _singular(w, CREATURE_TYPES | LAND_TYPES | ARTIFACT_TYPES | ENCHANTMENT_TYPES)) is not None:
            subtypes.append(one)  # (wave 42A: "Mercenaries" is the plural of Mercenary, "Elves" of Elf: 205.3m)
        elif w[:1].isupper() and w in ARTIFACT_TYPES | LAND_TYPES | ENCHANTMENT_TYPES | CREATURE_TYPES:
            subtypes.append(w)  # ("Food artifacts": the singular before the type; wave 26D: "is a Wall")
        else:
            return None
    if not types and not subtypes:
        return None
    everywhere = None
    if m["same"]:
        everywhere = _everywhere(m["s"], m["same"].strip())
        if everywhere is None or m["p"]:
            return None  # ("The same is true for …": the spells and cards of the same group, as Maskwood Nexus does)
    from app.rules.statics import GRANTABLE_KEYWORDS

    kws = [k for k in (m["kw0"], m["kw"]) if k]
    if any(k not in GRANTABLE_KEYWORDS for k in kws):
        return None
    d = _definition(m["s"], {"add_types": types, "add_subtypes": subtypes}, during=bool(m["during"]), everywhere=everywhere,
                    base=[int(m["p"]), int(m["t"])] if m["p"] else None, keywords=kws or None)
    if d is not None and m["q"]:
        text = m["q"][1:-1].rstrip(",")
        text = text if text[-1] in ".)" else text + "."  # (wave 25D: "…gets +2/+0," ends the clause)
        if granted_ability(text) is None:
            return None
        d["grants"] = [text]
        # -- attached events (wave 25D) -- "… and have "Equipped creature gets +2/+0" and equip {2}." (Armed with Proof, Gemcutter Buccaneer):
        # each equip ability (702.6) is its own granted keyword line, equip Pirate {1} the Pirate-only one
        for eq in re.findall(r"equip(?: [A-Z][a-z]+)? \{[^}]+\}", m["eq"] or ""):
            line = eq[0].upper() + eq[1:]
            if granted_ability(line) is None:
                return None
            d["grants"].append(line)
    elif d is not None and m["eq"]:
        return None
    return d


def with_gained_mana(before: Characteristics, after: Characteristics, set_land: bool = False) -> Characteristics:
    """305.6 / 305.7: a land that gained a basic land type has that type's intrinsic mana ability (numbered 90-94 by
    type, after the printed abilities, so the number doesn't change while other types come and go). -- land types set
    (wave 12D) -- ``set_land``: an effect set its land types (305.7): the abilities of its rules text (and of any copiable
    effects, layer 1) are gone (the ones other effects grant are layer 6, applied after this), and it has the intrinsic
    mana ability of each basic land type it has now."""
    if "Land" not in after.types:
        return after
    if set_land:
        from dataclasses import replace

        after = replace(after, abilities=tuple(a for a in after.abilities if a.index >= 90))
    gained = [t for t in BASIC if t in after.subtypes and (set_land or not (t in before.subtypes and "Land" in before.types))]
    if not gained:
        return after
    from dataclasses import replace

    from app.rules.characteristics import BASIC_LAND_MANA
    from app.rules.oracle import AbilityText

    have = {a.text for a in after.abilities}
    extra: list[AbilityText] = []
    for t in gained:
        text = f"{{T}}: Add {{{BASIC_LAND_MANA[t]}}}."
        if text not in have:
            extra.append(AbilityText(index=90 + BASIC.index(t), text=text, kind="mana", cost="{T}", intrinsic=True))
    return replace(after, abilities=after.abilities + tuple(extra)) if extra else after
