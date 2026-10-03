"""Wave 7R (second part of the wave 7 review): regressions for the seams found in the shield-counter, power-up, coin-flip
and must-block code of wave 7. Researched against CR 2026-09-25; cards carry real Oracle text."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import mana as M
from tests.test_rules_combat import attack, automate, block, creature, table
from tests.test_rules_effects import replay_matches


# -- 509.1c: a block that obeys its own requirement isn't taken as disobeying another one ------------------------------
def test_a_blocker_obeying_its_own_requirement_is_not_taken_away_from_another(cards):
    s = table(cards)
    soldier = creature(s, "p1", "Soldier", "2/2", "This creature must be blocked if able.")
    other = creature(s, "p1", "Other", "2/2")
    screen = creature(s, "p2", "Screen", "1/3", "This creature blocks each combat if able.")
    automate(s)
    attack(s, (soldier, "p2"), (other, "p2"))
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2")  # neither requirement obeyed
    block(s, "p2", (screen, other))  # "blocks each combat if able" obeyed; the one blocker can't also block the Soldier
    replay_matches(s)


# -- 118.7g: snow in a power-up cost is not read ---------------------------------------------------------------------
def test_power_up_with_snow_is_not_read():
    from app.rules import power_up
    from app.rules.characteristics import Characteristics

    def ch(cost):
        return Characteristics(name="X", mana_cost=cost)

    assert not power_up.readable(ch("{S}"), "{2}{G}")
    assert not power_up.readable(ch("{1}{G}"), "{S}{G}")
    assert power_up.readable(ch("{1}{G}"), "{2}{G}")
    assert M.parse_cost("{S}").colored == ("S",)
