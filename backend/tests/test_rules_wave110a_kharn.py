"""Wave 110A: Khârn the Betrayer: 615.5 the damage is prevented and an opponent (chosen by Khârn's controller) gains control of it (613.1b); 603.10d "When you
lose control" looks back in time, so the old controller draws two cards."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave30p_combat import to_phase
from tests.wave110c_kit import answer, build, check, make_db, put, real

EXTRA = [
    real("Khârn the Betrayer", "{1}{U}{B}", 3, "Legendary Creature — Astartes Berserker",
         "Berzerker — Khârn the Betrayer attacks or blocks each combat if able.\nSigil of Corruption — When you lose control of Khârn the Betrayer, draw two cards.\n"
         "The Betrayer — If damage would be dealt to Khârn the Betrayer, prevent that damage and an opponent of your choice gains control of it.", ("4", "4"), "UB"),
    real("Pinger110", "{1}", 1, "Creature — Wizard", "{T}: Pinger110 deals 1 damage to any target.", ("1", "1"), ""),
]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Khârn the Betrayer")).level == "FULL"


def test_damage_is_prevented_and_the_opponent_gains_control(cards):
    s = build(cards, ["Khârn the Betrayer"], ["Pinger110"])
    kharn, pinger = put(s, "Khârn the Betrayer"), put(s, "Pinger110", "p2")
    to_phase(s, "main1", 2)
    hand = len(s.state.zones["p1:hand"])
    act(s, "p2", type="activate_ability", card_id=pinger.id, ability=0, targets=[kharn.id])
    answer(s)
    k = s.state.cards[kharn.id]
    assert k.zone == "p2:battlefield" and k.controller == "p2" and k.owner == "p1" and k.damage == 0
    assert len(s.state.zones["p1:hand"]) == hand + 2  # (the old controller drew two: it looked back, 603.10d)
    check(s)
