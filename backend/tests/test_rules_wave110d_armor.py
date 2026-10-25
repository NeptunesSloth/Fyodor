"""Wave 110D: Iron Man Armor, real Oracle text (tests/fixtures/wave110d_cards.json). Every scenario checks the replay and a save and a load.

* 613.1d, 613.1f, 611.2a: "{2}: If this Equipment isn't a creature, it becomes a 0/0 Construct Hero artifact creature with flying and "This creature gets +1/+1
  for each artifact you control" until end of turn." — a creature with the granted pump (its own artifact count) and flying; a second activation does nothing.
"""

from __future__ import annotations

from tests.wave9c_kit import build
from tests.wave110d_kit import activate, card_db, ch, check, full, mana, put, settle  # noqa: F401


def test_iron_man_armor_is_full():
    assert full("Iron Man Armor")


def test_becomes_creature_scaled_by_artifacts(cards):
    s = build(cards, ["Iron Man Armor", "Sol Ring"])
    armor, _ring = put(s, "Iron Man Armor"), put(s, "Sol Ring")
    mana(s, C=4)
    activate(s, armor, "{2}: If")
    settle(s)
    c = ch(s, armor)
    assert "Creature" in c.types and "Construct" in c.subtypes and c.pt == (2, 2) and "flying" in c.keywords
    activate(s, armor, "{2}: If")
    settle(s)
    assert ch(s, armor).pt == (2, 2)
    check(s)
