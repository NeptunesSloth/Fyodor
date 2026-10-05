"""Wave 22C: "can't be regenerated" wordings (CR 701.19c): the shield isn't applied to a creature that can't be regenerated.

Each wording is tried against a creature with a regeneration shield (it dies) and, as the control, against the same effect
without the clause (the shield saves it).
"""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.test_rules_attachments import build, token
from tests.test_rules_effects import replay_matches
from tests.test_rules_replacements2 import activate, permanent

REGEN = "{1}: Regenerate this creature."
WORDINGS = [
    ("{1}: Destroy target creature. That creature can't be regenerated.", True),  # Nekrataal
    ("{1}: Destroy target creature. A creature destroyed this way can't be regenerated.", True),  # Soul Rend, Essence Vortex
    ("{1}: Destroy target creature. It can't be regenerated.", True),  # Befoul, Purge
    ("{1}: Killer deals 3 damage to target creature. A creature dealt damage this way can't be regenerated this turn.", True),  # Incinerate
    ("{1}: Killer deals 3 damage to target creature. It can't be regenerated this turn.", True),  # Engulfing Flames
    ("{1}: Destroy target creature.", False),
    ("{1}: Killer deals 3 damage to target creature.", False),
]


@pytest.mark.parametrize("text, dies", WORDINGS)
def test_a_regeneration_shield_saves_the_creature_only_without_the_clause(cards, text, dies):
    s = build(cards)
    bear = token(s, "p1", "Bear", "2/2", REGEN)
    activate(s, bear)  # (a regeneration shield for this turn)
    killer = permanent(s, "p1", "Killer", "Enchantment", text)
    activate(s, killer, targets=[bear.id])
    gone = bear.id not in s.state.cards
    assert gone == dies, text
    replay_matches(s)


def test_those_wordings_are_read():
    for text, _ in WORDINGS:
        cov = coverage.of_card_data({"name": "T" + str(abs(hash(text))), "oracle_id": str(abs(hash(text))), "type_line": "Enchantment",
                                     "oracle_text": text, "faces": [], "mana_cost": "{1}", "colors": [], "keywords": []})
        assert cov.level == "FULL", text
