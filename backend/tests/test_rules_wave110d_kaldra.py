"""Wave 110D: Helm of Kaldra, real Oracle text.

* 701.3a, 111.1: with Helm, Sword and Shield of Kaldra under your control, {1} makes the legendary 4/4 Avatar token Kaldra and attaches all three.
"""

from __future__ import annotations

from tests.wave9c_kit import build, card_named
from tests.wave110d_kit import activate, card_db, check, full, mana, put, settle  # noqa: F401

NAMES = ["Helm of Kaldra", "Sword of Kaldra", "Shield of Kaldra"]


def test_helm_is_full():
    assert full("Helm of Kaldra")


def test_all_three_make_kaldra(cards):
    s = build(cards, NAMES)
    eq = [put(s, n) for n in NAMES]
    mana(s, "p1", C=1)
    activate(s, eq[0], "{1}: If")
    kaldra = card_named(s, "Kaldra")
    assert kaldra.zone == "p1:battlefield"
    assert all(s.state.cards[c.id].attached_to == kaldra.id for c in eq)
    check(s)


def test_two_of_three_do_nothing(cards):
    s = build(cards, NAMES)
    eq = [put(s, n) for n in NAMES[:2]]
    mana(s, "p1", C=1)
    activate(s, eq[0], "{1}: If")
    assert not any(c.name == "Kaldra" for c in s.state.cards.values())
    check(s)
