"""Wave 110I session 15.

* The Dominion Bracelet: the granted "{15}, Exile <the Bracelet>: You control target opponent during their next turn" (723.1) pays the Bracelet itself as the exile cost
  (granter cost, 607.1a) and costs {X} less, X = the equipped creature's power including the Bracelet's +1/+1 (ruling 2025-07-25: locked in before costs are paid; 601.2f).
"""
from __future__ import annotations

import pytest

import tests.test_rules_wave110e_cards as base
from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave110e_cards import card_db  # noqa: F401  (the fixture)
from tests.test_rules_wave110e_s11 import _three
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave110i_s14 import BEAR, GIANT  # noqa: F401  (registers the helper creatures)
from tests.wave9c_kit import card_named, check, mana, put

BRACELET = real("The Dominion Bracelet", "{2}", 2, "Legendary Artifact — Equipment",
                "Equipped creature gets +1/+1 and has \"{15}, Exile The Dominion Bracelet: You control target opponent during their next turn. This ability costs {X} less to activate, where X is "
                "this creature's power. Activate only as a sorcery.\" (You see all cards that player could see and make all decisions for them.)\nEquip {1}", None, "")
base.EXTRA.append(BRACELET)


def test_bracelet_full(cards):
    assert coverage.of_card_data(cards.resolve("The Dominion Bracelet")).level == "FULL"


def _granted(s, host):
    from app.rules import characteristics as chars
    from app.rules.layers import derive

    c = s.state.cards[host.id]
    return next(x.index for x in derive(s.state, c, chars.of(c, s.cards), s.cards).abilities if x.index >= 100 and x.kind == "activated")


def _equipped(cards, creature):
    s = _three(cards, ["The Dominion Bracelet", creature])
    bracelet, host = put(s, "The Dominion Bracelet"), put(s, creature)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=bracelet.id, ability=1, targets=[host.id])
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[bracelet.id].attached_to == host.id
    return s, bracelet, host


@pytest.mark.parametrize(("creature", "cost"), [("Bear110I", 12), ("Giant110I", 14)])
def test_bracelet_cost_drops_by_the_equipped_power_and_exiles_it(cards, creature, cost):
    """2/2 Bear + 1 = power 3: {12}; 0/9 Giant + 1 = power 1: {14}. One mana short is refused; paying exiles the Bracelet and Alice controls Bob next turn."""
    s, bracelet, host = _equipped(cards, creature)
    mana(s, C=cost - 1)
    with pytest.raises(ActionError, match="pay|afford|mana"):
        act(s, "p1", type="activate_ability", card_id=host.id, ability=_granted(s, host), targets=["p2"])
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=host.id, ability=_granted(s, host), targets=["p2"])
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    assert s.state.cards[bracelet.id].zone.endswith(":exile")
    assert [(c.controlled, c.controller) for c in s.state.rules.player_control] == [("p2", "p1")]
    check(s)
