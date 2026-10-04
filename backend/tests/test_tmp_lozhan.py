from __future__ import annotations

import pytest

from tests.test_rules_wave17b_activated import *  # noqa: F401,F403
from tests.test_rules_wave17b_activated import EXTRA, card_db  # noqa: F401
from tests.test_rules_wave17b_activated import real
from tests.fixtures.cards import card, fixture_cards


def test_tmp(cards):
    s = build(cards, "Lozhan, Dragons' Legacy", "Shivan Dragon", p2=("Grizzly Bears",))
    on_field(s, "Lozhan, Dragons' Legacy")
    bears = on_field(s, "Grizzly Bears", "p2")
    spell = next(c for c in s.state.cards.values() if c.name == "Shivan Dragon")
    act(s, "p1", type="move", card_ids=[spell.id], to={"zone": "hand"})
    mana(s, "p1", R=2, C=4)
    act(s, "p1", type="cast_spell", card_id=spell.id)
    d = s.state.rules.decision
    print("DECISION", d)
    print("STACK", s.state.zones.get("stack"))
    raise AssertionError
