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
* Dependencies (613.8): every effect here only adds types, so an effect whose subject a type-adding effect changes
  (Dryad's "lands you control" once Ashaya made a creature a land) is applied after it — the objects each applies to
  are found again until nothing changes (``layer4_entries``); all of them are then applied in timestamp order with
  the object's other layer-4 effects (613.7).

A static line is the definition :func:`parse` returns (a static "grant" with no layer 6/7 parts, so ``layers._hits``
ignores it) carrying ``layer4`` (``{"add_types": […], "add_subtypes": […], "all_creature_types": bool}``, the
attached-object format ``layers._layer4`` already reads) and ``group_layer4`` True. Anything else stays unsupported.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance, GameState
    from app.rules.characteristics import CardInfo, Characteristics

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
_ARE_ALSO = re.compile(r"^(?P<during>During your turn, )?(?P<s>[A-Za-z' ]+?)(?: have base power and toughness (?P<p>\d+)/(?P<t>\d+) and)? are "
                       r"(?P<what>[A-Za-z ]+?) in addition to their other (?:creature )?types"
                       r"(?: and have (?P<q>\"[^\"]+\")|\.(?P<same> The same is true for creature spells you control and creature cards you own "
                       r"that aren't on the battlefield\.)?)$")  # (Kudo, Graaz: base P/T, 7b; Roshan: the Maskwood sentence)
_TYPE_WORDS = {"artifacts": "Artifact", "creatures": "Creature", "enchantments": "Enchantment", "lands": "Land"}
MASKWOOD = ("Creatures you control are every creature type. The same is true for creature spells you control and "
            "creature cards you own that aren't on the battlefield.")


def _definition(subject: str, layer4: dict[str, Any], *, everywhere: bool = False, during: bool = False,
                base: list[int] | None = None) -> dict[str, Any] | None:
    from app.rules import selectors
    from app.rules.statics import _definition as grant

    sel = selectors.parse(re.sub(r"^All ", "", subject)[0].lower() + re.sub(r"^All ", "", subject)[1:])  # (wave 17C: "All permanents")
    if sel is None or sel.player is not None or sel.zones != ("battlefield",):
        return None
    out = {**grant(sel.key(), None, [{"static": "your_turn"}] if during else [], base=base), "layer4": layer4, "group_layer4": True}
    if everywhere:
        out["everywhere"] = True
    return out


def parse(text: str) -> dict[str, Any] | None:
    """One static line (the card's own name written as ~) → its definition, or None."""
    if (m := _EACH_LAND.fullmatch(text)) is not None:
        return _definition("lands", {"add_subtypes": [m["t"]]})
    if (m := _EVERY_BASIC.fullmatch(text)) is not None:
        return _definition(m["s"], {"add_subtypes": list(BASIC)})
    if (m := _ARE_LANDS.fullmatch(text)) is not None:
        return _definition(m["s"], {"add_types": ["Land"], "add_subtypes": [m["t"]]})
    if (m := _ARE_ALSO.fullmatch(text)) is not None and (found := _also(m)) is not None:
        return found
    if re.fullmatch(r"~ is also an? [A-Z][A-Za-z]*(?:(?:, | and |, and )[A-Z][A-Za-z]*)*\.", text) \
            or re.fullmatch(r"~ is all colors\.(?: This ability doesn't affect its color identity\.)?", text):
        return {"kind": "static", "static": "cda", "effects": []}  # -- static_other sweep (wave 17C) -- characteristics.changeling / all_colors
    if text == "~ is every creature type.":  # (Mistform Ultimus: a characteristic-defining ability, 604.3 —
        return {"kind": "static", "static": "cda", "effects": []}  # characteristics.changeling applies it in every zone)
    if text == MASKWOOD:
        return _definition("creatures you control", {"all_creature_types": True}, everywhere=True)
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
        elif w[:1].isupper() and w.endswith("s") and w[:-1] in CREATURE_TYPES | LAND_TYPES | ARTIFACT_TYPES | ENCHANTMENT_TYPES:
            subtypes.append(w[:-1])
        elif w[:1].isupper() and w in ARTIFACT_TYPES | LAND_TYPES | ENCHANTMENT_TYPES:
            subtypes.append(w)  # ("Food artifacts": the singular before the type)
        else:
            return None
    if not types and not subtypes:
        return None
    if m["same"] and (m["s"] not in ("Creatures you control", "Other creatures you control") or m["p"]):
        return None  # ("The same is true for creature spells …": the creature spells and cards of the same group, as Maskwood Nexus does)
    d = _definition(m["s"], {"add_types": types, "add_subtypes": subtypes}, during=bool(m["during"]), everywhere=bool(m["same"]),
                    base=[int(m["p"]), int(m["t"])] if m["p"] else None)
    if d is not None and m["q"]:
        text = m["q"][1:-1]
        if granted_ability(text) is None:
            return None
        d["grants"] = [text]
    return d


def _group_statics(state: GameState, info: CardInfo) -> list[Any]:
    from app.rules.layers import statics

    return [st for st in statics(state, info) if st.definition.get("group_layer4") and st.gate is None]


def _off_field_applies(st: Any, card: CardInstance, ch: Characteristics) -> bool:
    """Maskwood Nexus: "creature spells you control" (on the stack) and "creature cards you own that aren't on the
    battlefield" (every other zone, the command zone too)."""
    if not st.definition.get("everywhere") or card.ability is not None or "Creature" not in ch.types:
        return False
    if card.zone == "stack":
        return card.controller == st.controller
    return card.owner == st.controller


def layer4_entries(state: GameState, card: CardInstance, ch: Characteristics, info: CardInfo | None,
                   apply: Any) -> list[tuple[int, dict[str, Any]]]:
    """The group type-adding statics that apply to ``card`` ((timestamp, definition) for ``layers._layer4``).
    ``apply(entries)`` is the object's layer 4 with these entries added: a subject is read from the object as the
    other type-adding effects leave it (613.8), until nothing changes."""
    if info is None or state.rules is None:
        return []
    table = _group_statics(state, info)
    if not table:
        return []
    on_field = card.zone.endswith(":battlefield")
    if not on_field:
        return [(st.seq, st.definition) for st in table if _off_field_applies(st, card, ch)]
    from app.rules import statics as grammar
    from app.rules.layers import _view

    view = _view(state, info)
    chosen: list[Any] = []
    for _ in range(4):
        now = apply([(st.seq, st.definition) for st in chosen])
        again = [st for st in table if grammar.applies(view, st.definition, source=state.cards[st.source],
                                                         controller=st.controller, card=card, ch=now, conditions=None)]  # (wave 17C: None, the static's own conditions are read: "During your turn")
        if again == chosen:
            break
        chosen = again
    return [(st.seq, st.definition) for st in chosen]


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
