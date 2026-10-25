"""Wave 110H: Unscythe, Killer of Kings (damage_death104 trigger with a may-exile rider: 120.3, 603.10a)."""
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_damage_death104 import DATA, cards, pair104, shoot104  # noqa: F401
from tests.test_rules_library_look import settle
from tests.wave9c_kit import check

NAME = "Unscythe, Killer of Kings"
DATA.append({"name": NAME, "mana_cost": "{U}{B}{B}{R}", "type_line": "Legendary Artifact — Equipment",
             "oracle_text": "Equipped creature gets +3/+3 and has first strike.\nWhenever a creature dealt damage by equipped creature this "
                            "turn dies, you may exile that card. If you do, create a 2/2 black Zombie creature token.\nEquip {2}"})


def test_full(cards):  # noqa: F811
    assert coverage.of_card_data(cards.resolve(NAME)).level == "FULL"


@pytest.mark.parametrize("take", [True, False])
def test_exile_then_zombie(cards, take):  # noqa: F811
    """A creature the equipped creature damaged dies: may exile it, then a 2/2 Zombie (only if exiled)."""
    from tests.test_rules_designations import put

    s, source, host = pair104(cards, NAME)
    victim = put(s, "Llanowar Elves", "battlefield", pid="p2")
    shoot104(s, host, victim)
    d = s.state.rules.decision
    assert d is not None
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes" if take else "no"])
    settle(s)
    zombies = [c for c in s.state.cards.values() if c.name == "Zombie" and c.zone == "p1:battlefield"]
    assert s.state.cards[victim.id].zone == ("p2:exile" if take else "p2:graveyard")
    assert len(zombies) == (1 if take else 0)
    check(s)
