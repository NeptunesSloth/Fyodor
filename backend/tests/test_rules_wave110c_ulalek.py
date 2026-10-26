"""Wave 110C: Ulalek, Fused Atrocity (707.10, 707.10c, 118.12): on casting an Eldrazi spell, for {C}{C} every spell the controller controls on the stack is copied, then every other
activated or triggered ability they control there (not Ulalek's own trigger); each copy may get new targets."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import build
from tests.wave110c_kit import STEPS, answer, check, life, make_db, mana, put, real, to_hand
from tests.wave110d_kit import ability

EXTRA = [real("Ulamog's Nullifier", "{2}{U}{B}", 4, "Creature — Eldrazi Processor",
              "Devoid (This card has no color.)\nFlash\nFlying\nWhen this creature enters, you may put two cards your opponents own from exile into their owners' graveyards. If you do, counter target spell.",
              ("2", "3"), ""),
         real("Prodigal Pyromancer", "{2}{R}", 3, "Creature — Human Wizard", "{T}: This creature deals 1 damage to any target.", ("1", "1"), "R"),
         real("Ulalek, Fused Atrocity", "{C/W}{C/U}{C/B}{C/R}{C/G}", 5, "Legendary Creature — Eldrazi",
              "Devoid (This card has no color.)\nWhenever you cast an Eldrazi spell, you may pay {C}{C}. If you do, copy all spells you control, then copy all other activated and triggered abilities you control. "
              "You may choose new targets for the copies. (Mana abilities can't be copied.)", ("2", "5"), "")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Ulalek, Fused Atrocity")).level == "FULL"


@pytest.mark.parametrize("pay", [True, False])
def test_copies_every_spell_then_every_other_ability(cards, pay):
    s = build(cards, ["Ulalek, Fused Atrocity", "Prodigal Pyromancer", "Lightning Bolt", "Ulamog's Nullifier"])
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False, hold_priority=True)  # (keep priority: everything stays on the stack)
    put(s, "Ulalek, Fused Atrocity")
    pyro = put(s, "Prodigal Pyromancer")
    s.state.rules.controlled_since[pyro.id].turn = 0
    act(s, "p1", type="activate_ability", card_id=pyro.id, ability=ability(s, pyro, "{T}"), targets=["p2"])
    bolt = to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=["p2"])
    sky = to_hand(s, "Ulamog's Nullifier")
    mana(s, U=1, B=1, C=4)
    act(s, "p1", type="cast_spell", card_id=sky.id)
    answer(s, "pay" if pay else "decline")
    assert life(s, "p2") == (40 - 3 * 2 - 1 * 2 if pay else 40 - 3 - 1)  # (the ability and the Bolt each twice)
    creatures = [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.name == "Ulamog's Nullifier"]
    assert len(creatures) == (2 if pay else 1)  # (the copy of the creature spell becomes a token)
    check(s)
