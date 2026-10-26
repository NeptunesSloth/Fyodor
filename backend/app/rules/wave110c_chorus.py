"""-- Chorus of the Conclave (wave 110C) -- "As an additional cost to cast creature spells, you may pay any amount of mana. If you do, that
creature enters with that many additional +1/+1 counters on it."

601.2b / 118.8: an optional additional cost announced as the spell is cast, for every player's creature spell (the static works only on the
battlefield, 113.6; rulings 2005-10-01: only while casting, so a creature put onto the battlefield by an effect is not affected). Read as a
multikicker-like {1} payment the spell is given as it is cast (the way wave110a_grants gives replicate); the count becomes that many
"counter" riders on the spell's payment record, which the entering creature reads (614.1c, mana_units.entering_counters).
A spell that already has a kicker-like ability (one paid-cost slot) or {X} in its cost is not offered the payment."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

_TEXT = re.compile(r"^as an additional cost to cast creature spells, you may pay any amount of mana\. if you do, that creature enters with "
                   r"that many additional \+1/\+1 counters on it$", re.IGNORECASE)
CHORUS_AT = 1050  # ability index of the granted payment (wave110a_grants.GRANTED_AT is 1000)
_SLOT = {"kicker", "multikicker", "replicate", "offspring", "squad", "entwine"}


def definition(t: str) -> dict[str, Any] | None:
    return {"kind": "static", "static": "chorus110c", "effects": []} if _TEXT.fullmatch(t.strip().rstrip(".")) else None


def grant(state: Any, player: str, card: Any, ch: Any, info: Any) -> Any:
    """The creature spell as cast: with the {1} payment Chorus of the Conclave gives it (none when the slot is taken)."""
    from app.rules import cast_limits
    from app.rules.oracle import parse_abilities

    if "Creature" not in ch.types or not ch.mana_cost or "{X}" in ch.mana_cost or state.rules is None:
        return ch
    if any(ab.kind == "keywords" and _SLOT & set(ab.keywords) for ab in ch.abilities) or not list(cast_limits._statics(state, info, "chorus110c")):
        return ch
    (extra,) = parse_abilities("Multikicker {1}.")
    return replace(ch, abilities=(*ch.abilities, replace(extra, index=CHORUS_AT)))


def riders(ch: Any, kicked: int) -> list[dict[str, Any]]:
    """614.1c: one entering +1/+1 counter per {1} paid (empty when the spell wasn't given the payment)."""
    return [{"kind": "counter", "name": "Chorus of the Conclave"}] * kicked if any(ab.index == CHORUS_AT for ab in ch.abilities) else []
