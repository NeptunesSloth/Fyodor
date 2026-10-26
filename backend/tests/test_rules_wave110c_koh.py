"""Wave 110C: Koh, the Face Stealer. 607.2a (exiled with Koh), 608.2d (choice as the ability resolves), 113.10 / 613.1f (all activated and triggered abilities of the
last chosen card), 400.7 (a card that left exile is a new object), 603.2 (a lent triggered ability triggers)."""

from __future__ import annotations

import pytest

from app.rules import coverage
from app.rules.plan import Plan
from tests.game_helpers import act
from tests.test_rules_wave30m_durations import to_phase
from tests.wave110c_kit import answer, build, cast, check, life, make_db, mana, put, real
from tests.wave110d_kit import ability

KOH = ("When Koh enters, exile up to one other target creature.\nWhenever another nontoken creature dies, you may exile it.\n"
       "Pay 1 life: Choose a creature card exiled with Koh.\nKoh has all activated and triggered abilities of the last chosen card.")
PUMP = "{2}: This creature gets +2/+0 until end of turn."
LIFE = "Whenever this creature attacks, you gain 1 life."
EXTRA = [real("Koh, the Face Stealer", "{4}{B}{B}", 6, "Legendary Creature — Shapeshifter Spirit", KOH, ("6", "6"), "B"),
         real("Test Pumper", "{1}{G}", 2, "Creature — Bear", PUMP, ("2", "2"), "G"),
         real("Test Gainer", "{1}{G}", 2, "Creature — Bear", LIFE, ("2", "2"), "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Koh, the Face Stealer")).level == "FULL"


def koh_with(cards, victim):
    s = build(cards, ["Koh, the Face Stealer"], [victim, "Test Gainer"], forests=30, islands=30)
    v = put(s, victim, "p2")
    mana(s, B=2, C=4)
    cast(s, "Koh, the Face Stealer")
    answer(s, v.id)
    assert s.state.cards[v.id].zone == "p2:exile"
    return s, v


def koh(s):
    return next(c for c in s.state.cards.values() if c.name == "Koh, the Face Stealer")


def names(s, c):
    return [a.text for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).abilities]


def test_no_choice_no_abilities_then_pay_life_chooses_and_koh_activates_it(cards):
    s, v = koh_with(cards, "Test Pumper")
    k = koh(s)
    assert not any("+2/+0" in t for t in names(s, k))
    act(s, "p1", type="activate_ability", card_id=k.id, ability=ability(s, k, "Pay 1 life"), sources=[])
    answer(s)
    assert life(s, "p1") == 39
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=k.id, ability=ability(s, k, "{2}"), sources=[])
    answer(s)
    assert Plan(s.state, "p1", s.cards, None).ch(s.state.cards[k.id]).pt == (8, 6)
    check(s)


def test_lent_triggered_ability_triggers_on_koh(cards):
    s, v = koh_with(cards, "Test Gainer")
    k = koh(s)
    act(s, "p1", type="activate_ability", card_id=k.id, ability=ability(s, k, "Pay 1 life"), sources=[])
    answer(s)
    assert life(s, "p1") == 39
    to_phase(s, "declare_attackers", 3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": k.id, "target": "p2"}])
    answer(s)
    assert life(s, "p1") == 40  # (the borrowed "Whenever this creature attacks, you gain 1 life")
    check(s)


def test_a_chosen_card_that_left_exile_gives_nothing(cards):
    s, v = koh_with(cards, "Test Pumper")
    k = koh(s)
    act(s, "p1", type="activate_ability", card_id=k.id, ability=ability(s, k, "Pay 1 life"), sources=[])
    answer(s)
    assert any("+2/+0" in t for t in names(s, k))
    act(s, "p2", type="move", card_ids=[v.id], to={"player": "p2", "zone": "hand"})  # (400.7: a new object)
    assert not any("+2/+0" in t for t in names(s, k))
    check(s)


def test_two_exiled_cards_the_last_chosen_wins(cards):
    """The dies trigger exiles a second creature card; each activation chooses one, and only the latest choice's abilities are lent."""
    s = build(cards, ["Koh, the Face Stealer", "Lightning Bolt"], ["Test Pumper", "Test Gainer"], forests=30, islands=30)
    pumper, gainer = put(s, "Test Pumper", "p2"), put(s, "Test Gainer", "p2")
    mana(s, B=2, C=4)
    cast(s, "Koh, the Face Stealer")
    answer(s, pumper.id)
    mana(s, R=1)
    cast(s, "Lightning Bolt", [gainer.id])
    answer(s, "yes")  # (may exile it)
    assert s.state.cards[gainer.id].zone == "p2:exile"
    k = koh(s)
    for pick, want in ((gainer.id, "attacks"), (pumper.id, "+2/+0")):
        act(s, "p1", type="activate_ability", card_id=k.id, ability=ability(s, k, "Pay 1 life"), sources=[])
        answer(s, pick)
        have = names(s, k)
        assert any(want in t for t in have) and not any(("attacks" if want == "+2/+0" else "+2/+0") in t for t in have)
    check(s)
