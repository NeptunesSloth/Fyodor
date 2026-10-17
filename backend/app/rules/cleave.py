"""-- keywords (wave 50H) -- cleave (CR 702.148), researched against the stored Comprehensive Rules (2026-09-25).

* 702.148a — "Cleave [cost]" is an alternative cost (118.9; app/rules/alt_costs.py, tag "cleave") and, when it is paid, a text-changing
  effect: all text within square brackets is removed from the spell's rules text (612). Cast any other way the brackets are only
  punctuation: oracle.parse_abilities reads the text without the bracket characters.
* The Wizards rulings: the cleave cost may have {X} (chosen as the spell is cast); it is never combined with another alternative cost, and a
  spell cast "without paying its mana cost" can't use it (118.9a, 601.2b).

:func:`overlay` is the characteristics the spell is cast with (and resolves as) once the cleave cost is chosen: the rules text re-read
without the bracketed words; :func:`supported` is what coverage asks (the cleaved text must be carried out too).
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics


def cleaved(text: str) -> str:
    """The rules text with every "[…]" removed (702.148a), and the space it leaves behind."""
    text = re.sub(r" ?\[[^\]]*\]", "", text)
    return re.sub(r"\n +| +\n", "\n", text).strip()


def overlay(ch: Characteristics) -> Characteristics:
    """The spell with the words in square brackets removed (702.148a)."""
    from app.rules.oracle import parse_abilities

    text = cleaved(ch.oracle_text)
    return replace(ch, oracle_text=text, abilities=tuple(parse_abilities(text, spell=ch.is_instant_or_sorcery)))


def supported(ch: Characteristics) -> bool:
    """Whether the cleaved spell is carried out by the engine (read whole, as an ordinary instant or sorcery)."""
    from app.rules import coverage, scripts

    over = overlay(ch)
    whole = scripts.spell_definition(over)
    return whole is not None and coverage.definition_supported(whole) and coverage.x_selector_ok(over, whole)
