"""Wave 110C: Heirloom Epic: "For each mana in this ability's activation cost, you may tap an untapped creature you control rather than pay that mana" (the payment of
701.67a, creatures only, not a waterbend; tapping them is no {T} cost, so a summoning-sick creature helps, 302.6); sorcery speed."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_conditionals import creature
from tests.wave9c_kit import build
from tests.wave110c_kit import check, make_db, mana, put, real

EPIC = ("{4}, {T}: Draw a card. For each mana in this ability's activation cost, you may tap an untapped creature you control rather than pay that mana. "
        "Activate only as a sorcery.")
EXTRA = [real("Heirloom Epic", "{1}", 1, "Artifact — Book", EPIC, None, ""),
         real("Rock", "{1}", 1, "Artifact", "", None, "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Heirloom Epic")).level == "FULL"


def start(cards, helpers, mana_c):
    s = build(cards, ["Heirloom Epic", "Rock"])
    epic = put(s, "Heirloom Epic")
    rock = put(s, "Rock")
    kids = [creature(s, "p1", f"Helper {i}", pt="1/1") for i in range(helpers)]
    if mana_c:
        mana(s, C=mana_c)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="activate_ability", card_id=epic.id, ability=0)
    return s, epic, rock, kids, hand


def pick(s, ids):
    d = s.state.rules.decision
    assert d is not None
    act(s, "p1", type="choose", decision_id=d.id, option_ids=ids)


def test_creatures_pay_mana_not_artifacts(cards):
    s, epic, rock, kids, hand = start(cards, 3, 1)
    d = s.state.rules.decision
    assert {o.id for o in d.options} == {k.id for k in kids}  # (not the Rock, not the Epic that taps itself)
    pick(s, [k.id for k in kids])
    while s.state.rules.stack:
        act(s, s.state.rules.priority, type="pass_priority")
    assert len(s.state.zones["p1:hand"]) == hand + 1 and all(s.state.cards[k.id].tapped for k in kids)
    check(s)


def test_paid_with_mana_alone(cards):
    s, epic, rock, kids, hand = start(cards, 1, 4)
    pick(s, [])
    while s.state.rules.stack:
        act(s, s.state.rules.priority, type="pass_priority")
    assert len(s.state.zones["p1:hand"]) == hand + 1 and not s.state.cards[kids[0].id].tapped
    check(s)


def test_cost_must_be_paid(cards):
    s, epic, rock, kids, hand = start(cards, 2, 0)
    with pytest.raises(ActionError):  # ({2} of the cost is left and there's no mana for it)
        pick(s, [k.id for k in kids])
    assert not s.state.cards[epic.id].tapped
