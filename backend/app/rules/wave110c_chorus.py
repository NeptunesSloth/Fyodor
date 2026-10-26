"""-- Chorus of the Conclave (wave 110C) -- "As an additional cost to cast creature spells, you may pay any amount of mana. If you do, that
creature enters with that many additional +1/+1 counters on it."

601.2b / 118.8: an optional additional cost announced as the spell is cast, for every player's creature spell (the static works only on the
battlefield, 113.6; rulings 2005-10-01: only while casting, so a creature put onto the battlefield by an effect is not affected). It has its own
slot, ``CastSpell.chorus`` (generic mana), apart from kicker/offspring/replicate, so the spell is never "kicked" by it and a kicker creature may use both;
the count becomes that many "counter" riders on the spell's payment record, which the entering creature reads (614.1c, mana_units.entering_counters).
A spell with {X} in its cost is not offered the payment."""

from __future__ import annotations

import re
from typing import Any

_TEXT = re.compile(r"^as an additional cost to cast creature spells, you may pay any amount of mana\. if you do, that creature enters with "
                   r"that many additional \+1/\+1 counters on it$", re.IGNORECASE)


def definition(t: str) -> dict[str, Any] | None:
    return {"kind": "static", "static": "chorus110c", "effects": []} if _TEXT.fullmatch(t.strip().rstrip(".")) else None


def offered(state: Any, player: str, card: Any, ch: Any, info: Any) -> bool:
    """Whether ``player`` may pay Chorus's additional cost for this creature spell (the static is on the battlefield, 113.6; {X} spells are not offered)."""
    from app.rules import cast_limits

    return "Creature" in ch.types and "{X}" not in (ch.mana_cost or "") and state.rules is not None and bool(list(cast_limits._statics(state, info, "chorus110c")))


def check(state: Any, a: Any, card: Any, ch: Any, info: Any, player: str) -> None:
    """601.2b: refuse an announced payment the cast has no Chorus for."""
    from app.game.errors import ActionError

    if a.chorus and not offered(state, player, card, ch, info):
        raise ActionError(f"{ch.name or 'That card'} has no Chorus of the Conclave additional cost to pay now")


def riders(n: int) -> list[dict[str, Any]]:
    """614.1c: one entering +1/+1 counter per {1} paid."""
    return [{"kind": "counter", "name": "Chorus of the Conclave"}] * n
