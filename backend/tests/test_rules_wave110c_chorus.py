"""Wave 110C: Chorus of the Conclave. 601.2b / 118.8 (optional additional cost, any amount, announced as the creature spell is cast), 614.1c (enters with that
many additional +1/+1 counters), 113.6 (works only on the battlefield), rulings 2005-10-01 (casting only, not creatures put onto the battlefield)."""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave9c_kit import life, pt
from tests.wave110c_kit import answer, build, check, make_db, mana, put, real, to_hand

CHORUS = ("Forestwalk (This creature can't be blocked as long as defending player controls a Forest.)\n"
          "As an additional cost to cast creature spells, you may pay any amount of mana. If you do, that creature enters with that many "
          "additional +1/+1 counters on it.")
EXTRA = [real("Chorus of the Conclave", "{3}{G}{G}", 5, "Creature — Dryad", CHORUS, ("4", "4"), "G"),
         real("Test Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
         real("Test Kicker Bear", "{1}{G}", 2, "Creature — Bear", "Kicker {1}\nWhen this creature enters, if it was kicked, you gain 1 life.", ("2", "2"), "G"),
         real("Test X Bear", "{X}{G}", 1, "Creature — Bear", "", ("1", "1"), "G"),
         real("Test Sorcery", "{G}", 1, "Sorcery", "You gain 2 life.", None, "G")]


@pytest.fixture()
def card_db(settings):
    return make_db(settings, EXTRA)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve("Chorus of the Conclave")).level == "FULL"


def cast_paying(s, name, extra, pid="p1"):
    c = to_hand(s, name, pid)
    act(s, pid, type="cast_spell", card_id=c.id, chorus=extra)
    answer(s)
    return c


def test_paying_n_gives_n_counters(cards):  # 601.2b + 614.1c
    s = build(cards, ["Chorus of the Conclave", "Test Bear"])
    put(s, "Chorus of the Conclave")
    mana(s, G=5)
    cast_paying(s, "Test Bear", 3)
    assert pt(s, 'Test Bear') == (5, 5)
    check(s)


def test_paying_nothing_is_fine(cards):  # "any amount" includes none
    s = build(cards, ["Chorus of the Conclave", "Test Bear"])
    put(s, "Chorus of the Conclave")
    mana(s, G=2)
    cast_paying(s, "Test Bear", 0)
    assert pt(s, 'Test Bear') == (2, 2)


def test_opponent_creature_spell_gets_it_too(cards):  # "creature spells": every player's
    s = build(cards, ["Chorus of the Conclave"], ["Test Bear"])
    put(s, "Chorus of the Conclave")
    s.state.rules.priority = "p2"
    mana(s, "p2", G=3)
    c = to_hand(s, "Test Bear", "p2")
    s.state.turn.active_player = "p2"
    act(s, "p2", type="cast_spell", card_id=c.id, chorus=1)
    answer(s)
    assert pt(s, 'Test Bear', 'p2') == (3, 3)


def test_not_on_the_battlefield_no_payment(cards):
    s = build(cards, ["Chorus of the Conclave", "Test Bear"])
    mana(s, G=5)
    c = to_hand(s, "Test Bear")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, chorus=1)


def test_non_creature_spell_not_offered(cards):
    s = build(cards, ["Chorus of the Conclave", "Test Sorcery"])
    put(s, "Chorus of the Conclave")
    mana(s, G=3)
    c = to_hand(s, "Test Sorcery")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, chorus=1)


def test_put_onto_battlefield_has_no_counters(cards):  # ruling 2005-10-01
    s = build(cards, ["Chorus of the Conclave", "Test Bear"])
    put(s, "Chorus of the Conclave")
    assert (put(s, 'Test Bear'), pt(s, 'Test Bear'))[1] == (2, 2)


def cast_both(s, kicker, chorus):
    c = to_hand(s, "Test Kicker Bear")
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=kicker, chorus=chorus)
    answer(s)


def test_kicker_creature_uses_both_slots(cards):  # 601.2b: separate additional costs; {1}{G} + kicker {1} + Chorus {2}
    s = build(cards, ["Chorus of the Conclave", "Test Kicker Bear"])
    put(s, "Chorus of the Conclave")
    mana(s, G=5)
    before = life(s, "p1")
    cast_both(s, 1, 2)
    assert pt(s, "Test Kicker Bear") == (4, 4) and life(s, "p1") == before + 1
    check(s)


def test_chorus_alone_is_not_kicked(cards):  # "if it was kicked" stays false
    s = build(cards, ["Chorus of the Conclave", "Test Kicker Bear"])
    put(s, "Chorus of the Conclave")
    mana(s, G=4)
    before = life(s, "p1")
    cast_both(s, 0, 2)
    assert pt(s, "Test Kicker Bear") == (4, 4) and life(s, "p1") == before
    check(s)


def test_kicker_alone_gets_no_counters(cards):  # the kicker {1} is not Chorus's payment
    s = build(cards, ["Chorus of the Conclave", "Test Kicker Bear"])
    put(s, "Chorus of the Conclave")
    mana(s, G=3)
    before = life(s, "p1")
    cast_both(s, 1, 0)
    assert pt(s, "Test Kicker Bear") == (2, 2) and life(s, "p1") == before + 1


def free_cast(s, name):
    c = to_hand(s, name)
    s.state.rules.free_casts.append(c.id)
    act(s, "p1", type="cast_spell", card_id=c.id, free=True)
    return c


def test_free_cast_offers_chorus_and_kicker_separately(cards):  # 118.9d: the free cast may still pay both optional costs
    s = build(cards, ["Chorus of the Conclave", "Test Kicker Bear"])
    put(s, "Chorus of the Conclave")
    mana(s, G=3)
    before = life(s, "p1")
    free_cast(s, "Test Kicker Bear")
    ids = {o.id for o in s.state.rules.decision.options}
    assert {"kicker:1", "chorus:1", "chorus:2", "chorus:other"} <= ids and "chorus:4" not in ids
    answer(s, ["chorus:2", "kicker:1"])
    answer(s)
    assert pt(s, "Test Kicker Bear") == (4, 4) and life(s, "p1") == before + 1
    check(s)


def test_free_cast_typed_chorus_amount(cards):
    s = build(cards, ["Chorus of the Conclave", "Test Bear"])
    put(s, "Chorus of the Conclave")
    mana(s, G=8)
    free_cast(s, "Test Bear")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["chorus:other"])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, name="7")
    answer(s)
    assert pt(s, "Test Bear") == (9, 9)
    check(s)


def test_x_creature_chorus_and_x_are_separate(cards):  # 601.2b announces X and Chorus separately, 601.2f one total: {3}{G} + {2} = 6 mana
    s = build(cards, ["Chorus of the Conclave", "Test X Bear"])
    put(s, "Chorus of the Conclave")
    mana(s, G=6)
    c = to_hand(s, "Test X Bear")
    act(s, "p1", type="cast_spell", card_id=c.id, x_value=3, chorus=2)
    answer(s)
    assert pt(s, "Test X Bear") == (3, 3)  # base 1/1 + 2 counters from Chorus only (X is not a counter count)
    check(s)


def test_chorus_amount_in_hints(cards):  # the client sees which castable cards take CastSpell.chorus (like x_cast / x_kicker)
    s = build(cards, ["Chorus of the Conclave", "Test X Bear", "Test Bear", "Test Sorcery"])
    mana(s, G=6)
    ids = {n: to_hand(s, n).id for n in ("Test X Bear", "Test Bear", "Test Sorcery")}
    assert not s.view("p1")["rules"]["hints"].get("chorus")
    put(s, "Chorus of the Conclave")
    got = set(s.view("p1")["rules"]["hints"]["chorus"])
    assert got == {ids["Test X Bear"], ids["Test Bear"]}
