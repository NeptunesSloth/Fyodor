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
MASKWOOD = ("Creatures you control are every creature type. The same is true for creature spells you control and "
            "creature cards you own that aren't on the battlefield.")


def _definition(subject: str, layer4: dict[str, Any], *, everywhere: bool = False) -> dict[str, Any] | None:
    from app.rules import selectors
    from app.rules.statics import _definition as grant

    sel = selectors.parse(subject[0].lower() + subject[1:])
    if sel is None or sel.player is not None or sel.zones != ("battlefield",):
        return None
    out = {**grant(sel.key(), None, []), "layer4": layer4, "group_layer4": True}
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
    if text == "~ is every creature type.":  # (Mistform Ultimus: a characteristic-defining ability, 604.3 —
        return {"kind": "static", "static": "cda", "effects": []}  # characteristics.changeling applies it in every zone)
    if text == MASKWOOD:
        return _definition("creatures you control", {"all_creature_types": True}, everywhere=True)
    return None


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
                                                         controller=st.controller, card=card, ch=now, conditions=True)]
        if again == chosen:
            break
        chosen = again
    return [(st.seq, st.definition) for st in chosen]


def with_gained_mana(before: Characteristics, after: Characteristics) -> Characteristics:
    """305.6 / 305.7: a land that gained a basic land type has that type's intrinsic mana ability (numbered 90-94 by
    type, after the printed abilities, so the number doesn't change while other types come and go)."""
    if "Land" not in after.types:
        return after
    gained = [t for t in BASIC if t in after.subtypes and not (t in before.subtypes and "Land" in before.types)]
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
