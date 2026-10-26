"""-- Dark Intimations (wave 110C) -- "When you cast a Bolas planeswalker spell, exile this card from your graveyard. That planeswalker enters with an
additional loyalty counter on it."

113.6k-style graveyard trigger (the exile of its own card from the graveyard puts it among the abilities that work only there, triggers.graveyard_ability);
601.2i / 603.3: it triggers when the spell is cast and resolves above it; 614.1c: "enters with an additional loyalty counter" is a replacement effect of the
permanent entering, here a rider on the spell's payment record (the cast_riders way) that replacements.entering_counters reads, 122.1 / 306.5b."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

TEXT = "When you cast a Bolas planeswalker spell, exile this card from your graveyard. That planeswalker enters with an additional loyalty counter on it."
RIDER = "loyalty110c"


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != "triggered" or scripts.self_text(ability.text, ch.name) != TEXT:
        return None
    base = scripts.define(replace(ability, text="When you cast a Bolas planeswalker spell, you gain 1 life."), ch)
    if base is None:
        return None
    return {**base, "effects": [{"do": "exile", "who": "self_gy"}, {"do": "spell_rider", "who": "event_spell", "riders": [{"kind": RIDER}]}]}


def entering_loyalty(plan: Any, card: Any) -> int:
    from app.rules import mana_units

    rec = mana_units.record_of(plan, card)
    return sum(1 for r in (rec.mana_riders if rec is not None else ()) if r["kind"] == RIDER)


def watch_ok(effect: dict[str, Any], cond: dict[str, Any] | None) -> bool:
    """Is this the loyalty rider of a "you cast a Bolas planeswalker spell" trigger (that planeswalker is the spell the event is about)?"""
    from app.rules import selectors

    key = (cond or {}).get("spell")
    sel = selectors.from_key(key) if isinstance(key, str) and key.startswith(selectors.PREFIX) else None
    return (effect.get("riders") == [{"kind": RIDER}] and cond is not None and cond.get("event") == "cast" and cond.get("subject") == "player"
            and cond.get("player") == "you" and not cond.get("copy") and sel is not None and sel.types == ("Planeswalker",) and sel.subtypes == ("Bolas",)
            and sel.zones == ("stack",) and not sel.union and not sel.not_types)
