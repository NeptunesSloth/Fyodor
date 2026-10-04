"""-- casting extras (wave 18E) -- overload (CR 702.96), researched against the stored Comprehensive Rules (2026-09-25).

* 702.96a — "Overload [cost]" is an alternative cost (118.9; app/rules/alt_costs.py, tag "overload") and, when it is paid, a
  text-changing effect: every instance of the word "target" in the spell's text becomes "each" (612).
* 702.96b — the overloaded spell requires no targets and may affect objects that couldn't have been chosen as targets.

:func:`overlay` is the characteristics the spell is cast with (and resolves as) once the overload cost is chosen: the spell lines
are re-read with "each" in place of "target", so any wording the grammar can't carry out that way keeps the card manual
(:func:`supported` is what coverage asks).
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics

_TARGET = re.compile(r"\b(t)arget\b", re.IGNORECASE)


def overlay(ch: Characteristics) -> Characteristics:
    """The spell with "target" read as "each" (702.96a); no longer a spell with targets (702.96b)."""
    abilities = tuple(a if a.kind == "keywords" else replace(a, text=_TARGET.sub(lambda m: "Each" if m[1] == "T" else "each", a.text))
                      for a in ch.abilities)
    return replace(ch, abilities=abilities, oracle_text=_TARGET.sub(lambda m: "Each" if m[1] == "T" else "each", ch.oracle_text))


def supported(ch: Characteristics) -> bool:
    """Whether the overloaded spell is carried out by the engine (an instant or sorcery read whole, with no target left)."""
    from app.rules import coverage, scripts

    over = overlay(ch)
    whole = scripts.spell_definition(over)
    return (whole is not None and coverage.definition_supported(whole) and coverage.x_selector_ok(over, whole)
            and not whole.get("modes") and not scripts.target_groups(whole))
