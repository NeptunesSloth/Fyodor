"""Wave 12B: lure (509.1c) — "All creatures able to block this creature do so." as a static and as an activated ability."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.test_rules_conditionals import settle
from tests.test_rules_effects import replay_matches
from tests.test_rules_wave6c_tokens_pumps import mana, reloaded
from tests.test_rules_wave7e_activated import combat_table


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))


def test_static_lure_makes_every_able_creature_block(cards):
    from tests.test_rules_combat import attack, block

    s, lure, guard, spare = combat_table(cards, "All creatures able to block this creature do so.")
    act(s, "p1", type="pass_priority")
    attack(s, (lure, "p2"))
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2")
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2", (guard, lure))
    block(s, "p2", (guard, lure), (spare, lure))
    check(s)


def test_activated_lure_lasts_the_turn(cards):
    from tests.test_rules_combat import attack, block

    s, lure, guard, spare = combat_table(cards, "{2}{G}: All creatures able to block this creature this turn do so.")
    mana(s, G=1, C=2)
    act(s, "p1", type="activate_ability", card_id=lure.id, ability=0)
    settle(s)
    act(s, "p1", type="pass_priority")
    attack(s, (lure, "p2"))
    with pytest.raises(ActionError, match="if able"):
        block(s, "p2", (guard, lure))
    block(s, "p2", (guard, lure), (spare, lure))
    check(s)
