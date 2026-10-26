"""-- entry types (wave 110A) -- "As a historic permanent you control enters, it becomes a 7/7 Dinosaur creature in addition to its other types."

614.12: a replacement that modifies how a permanent enters; 205.1b "in addition" adds the types, 613.4b sets base power and toughness.
The effect has no end (611.2a), so it is a permanent layer effect made right after the move (``after_entry``).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.game.state import CardInstance
    from app.rules.plan import Plan

_RE = re.compile(r"^as an? (?P<sel>historic permanent you control) enters, it becomes an? (?P<p>\d+)/(?P<t>\d+) (?P<sub>[A-Z][a-z]+) creature "
                 r"in addition to its other types$", re.I)


# Sigarda's Splendor: "As this enchantment enters, note your life total." Noting is part of entering (614.12a); the number is kept as a choice
# of the permanent (public: 400.1), read back by ``noted_draw110a`` (wave110a_spells).
NOTE = "Noted life total"
_NOTE = re.compile(r"^as (?:this [a-z]+|~) enters, note your life total$", re.I)


def static(t: str) -> dict[str, Any] | None:
    if _NOTE.fullmatch(t.strip().rstrip(".")):
        return {"kind": "static", "static": "note_life110a", "effects": []}
    m = _RE.fullmatch(t.strip().rstrip("."))
    if m is None:
        return None
    return {"kind": "static", "static": "enter_become110a", "sel": m["sel"].lower(), "p": int(m["p"]), "t": int(m["t"]),
            "sub": m["sub"].capitalize(), "effects": []}


def apply(plan: Plan, card: CardInstance) -> None:
    from app.rules import copying, layers, permissions, selectors

    # Superior Spider-Man: "When you do, exile that card" (603.12): a reflexive trigger on the object it copied (400.7: the card as it was)
    if (d := copying.enter_definition(plan, card)) is not None and d.get("exile_copied110a") and (eff := copying._entering_effect(plan, card)) is not None \
            and eff.copy_entry_source is not None:
        from app.rules.triggers import _add

        _add(plan, controller=card.controller, source_card=card.id, source_object=plan.oid(card), name=card.name or "", index=7310,
             definition={"kind": "triggered", "trigger": "reflexive", "optional": False,
                         "effects": [{"do": "exile_object110a", "oid": eff.copy_entry_source.object_id}]})

    for src, _, _d in permissions._table_statics(plan.state, plan.info, {"note_life110a"}):
        if src.id == card.id:
            note(plan, card)
    for src, _, d in permissions._table_statics(plan.state, plan.info, {"enter_become110a"}):
        sel = selectors.parse(d["sel"])
        if sel is None or not selectors.matches(plan, sel, card, plan.ch(card), src.controller, src.id):
            continue
        layers.add_effect(plan, affected=[plan.oid(card)], layer="4", source=None, controller=src.controller, add_types=("Creature",),
                          add_subtypes=(d["sub"],), duration="permanent", label=f"{d['sub']} creature (enters)")
        layers.add_effect(plan, affected=[plan.oid(card)], layer="7b", source=None, controller=src.controller, power=d["p"],
                          toughness=d["t"], duration="permanent", label=f"{d['p']}/{d['t']} (enters)")


def note(plan: Plan, card: CardInstance) -> None:
    """Note the controller's life total as of now (replacing the earlier note, "the last noted life total")."""
    plan.do({"type": "set_choice", "card_id": card.id, "key": NOTE, "value": str(plan.state.players[card.controller].life)}, actor=card.controller)


def exile_object(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Exile one specific object wherever it is, if it is still that object (400.7)."""
    from app.rules import effects

    card = plan.state.cards.get(e["oid"].rsplit(".", 1)[0])
    return effects.exile_cards(plan, ctx, e, [card.id] if card is not None and plan.oid(card) == e["oid"] else [])


PRIMITIVES = {"exile_object110a": exile_object}
