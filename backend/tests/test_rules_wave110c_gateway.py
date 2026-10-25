"""Wave 110C: Cryptic Gateway (602.2 the cost taps two creatures; the put-onto-the-battlefield may only take a creature card sharing a creature type with each, 205.3m)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from tests.game_helpers import act
from tests.wave110c_kit import answer, build, check, make_db, put, real, to_hand

GATE = ("Tap two untapped creatures you control: You may put a creature card from your hand that shares a creature type with each creature tapped "
        "this way onto the battlefield.")
EXTRA = [real("Cryptic Gateway", "{5}", 5, "Artifact", GATE, None, ""),
         real("Elf Warrior", "{G}", 1, "Creature — Elf Warrior", "", ("1", "1"), "G"),
         real("Elf Shaman", "{G}", 1, "Creature — Elf Shaman", "", ("1", "1"), "G"),
         real("Elf Archer", "{G}", 1, "Creature — Elf Archer", "", ("1", "1"), "G"),
         real("Goblin Warrior", "{R}", 1, "Creature — Goblin Warrior", "", ("1", "1"), "R")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Cryptic Gateway")).level == "FULL"


def test_only_cards_sharing_a_type_with_each_tapped(cards):
    s = build(cards, ["Cryptic Gateway", "Elf Warrior", "Elf Shaman", "Elf Archer", "Goblin Warrior"])
    gate = put(s, "Cryptic Gateway")
    a, b = put(s, "Elf Warrior"), put(s, "Elf Shaman")
    elf, gob = to_hand(s, "Elf Archer"), to_hand(s, "Goblin Warrior")
    act(s, "p1", type="activate_ability", card_id=gate.id, ability=0)
    d = s.state.rules.decision
    assert d is not None and {o.id for o in d.options} == {elf.id}
    answer(s, [elf.id])
    assert s.state.cards[elf.id].zone == "p1:battlefield" and s.state.cards[gob.id].zone == "p1:hand"
    assert s.state.cards[a.id].tapped and s.state.cards[b.id].tapped
    check(s)


def test_no_card_shares_a_type_with_both(cards):
    s = build(cards, ["Cryptic Gateway", "Elf Warrior", "Goblin Warrior", "Elf Archer"])
    gate = put(s, "Cryptic Gateway")
    a, b = put(s, "Elf Warrior"), put(s, "Goblin Warrior")
    elf = to_hand(s, "Elf Archer")
    act(s, "p1", type="activate_ability", card_id=gate.id, ability=0)
    d = s.state.rules.decision
    assert d is not None and not d.options
    answer(s, [])
    assert s.state.cards[elf.id].zone == "p1:hand" and s.state.cards[a.id].tapped and s.state.cards[b.id].tapped
    check(s)
