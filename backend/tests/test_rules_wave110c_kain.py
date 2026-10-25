"""Wave 110C: Kain, Traitorous Dragoon (510.2 combat damage, 110.2 / 108.4 control change by the damaged player, 608.2c "If they do" gates the draw, Treasure and life loss)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.test_rules_wave30p_combat import attack, to_phase
from tests.wave110c_kit import answer, build, check, make_db, put, real

TEXT = ("Jump — During your turn, Kain has flying.\nWhenever Kain deals combat damage to a player, that player gains control of Kain. If they do, you draw that many cards, "
        "create that many tapped Treasure tokens, then lose that much life.")
EXTRA = [real("Kain, Traitorous Dragoon", "{2}{B}", 3, "Legendary Creature — Human Knight", TEXT, ("2", "4"), "B")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Kain, Traitorous Dragoon")).level == "FULL"


def test_damaged_player_gets_kain_and_you_get_the_rewards(cards):
    s = build(cards, ["Kain, Traitorous Dragoon", "Forest"], ["Island"])
    kain = put(s, "Kain, Traitorous Dragoon")
    to_phase(s, "declare_attackers", 3)
    hand, life = len(s.state.zones["p1:hand"]), s.state.players["p1"].life
    attack(s, (kain, "p2"))
    answer(s)
    assert s.state.cards[kain.id].controller == "p2"
    assert len(s.state.zones["p1:hand"]) == hand + 2 and s.state.players["p1"].life == life - 2
    treasures = [c for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield"]
    assert len(treasures) == 2 and all(c.tapped for c in treasures)
    check(s)
