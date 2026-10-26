"""Wave 110N: Soulflayer (702.66a delve, 611.3a: it has each keyword a creature card exiled with its own delve had)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

FLAYER, SKY, VENOM, PLAIN, BOLT = "Soulflayer", "Sky Imp", "Venom Imp", "Plain Imp", "Plain Bolt"
EXTRA = [
    real(FLAYER, "{4}{B}", 5, "Creature — Demon Horror",
         "Delve (Each card you exile from your graveyard while casting this spell pays for {1}.)\nIf a creature card with flying was exiled with this creature's delve ability, "
         "this creature has flying. The same is true for first strike, double strike, deathtouch, haste, hexproof, indestructible, lifelink, reach, trample, and vigilance.", ("4", "4"), "B"),
    real(SKY, "{1}{B}", 2, "Creature — Imp", "Flying", ("1", "1"), "B"),
    real(VENOM, "{1}{B}", 2, "Creature — Imp", "Deathtouch\nVigilance", ("1", "1"), "B"),
    real(PLAIN, "{1}{B}", 2, "Creature — Imp", "", ("1", "1"), "B"),
    real(BOLT, "{R}", 1, "Instant", "Plain Bolt deals 1 damage to any target.", None, "R"),
]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([FLAYER])


def delve_cast(cards, delved):
    s = build(cards, [FLAYER, *delved])
    for n in delved:
        act(s, "p1", type="move", card_ids=[card_named(s, n).id], to={"player": "p1", "zone": "graveyard"})
    mana(s, "p1", B=1, C=5 - len(delved))
    c = to_hand(s, FLAYER)
    act(s, "p1", type="cast_spell", card_id=c.id, contributions=[{"kind": "delve", "card": card_named(s, n).id} for n in delved])
    answer(s)
    assert zone_of(s, FLAYER) == "p1:battlefield"
    return s, c


@pytest.mark.parametrize(("delved", "has", "lacks"), [
    ([SKY, VENOM, PLAIN, BOLT], {"flying", "deathtouch", "vigilance"}, {"haste", "reach", "lifelink", "first strike"}),
    ([PLAIN, BOLT], set(), {"flying", "deathtouch", "vigilance"}),
    ([BOLT], set(), {"flying"}),
    ([SKY], {"flying"}, {"deathtouch"}),
])
def test_it_has_the_keywords_of_the_creature_cards_exiled_with_its_delve(cards, delved, has, lacks):
    s, c = delve_cast(cards, delved)
    kw = ch(s, c).keywords
    assert has <= kw and not (lacks & kw)
    check(s)


def test_without_delve_it_has_none_even_with_such_cards_in_the_graveyard(cards):
    s = build(cards, [FLAYER, SKY])
    act(s, "p1", type="move", card_ids=[card_named(s, SKY).id], to={"player": "p1", "zone": "graveyard"})
    mana(s, "p1", B=1, C=4)
    cast(s, FLAYER, pay=False)
    answer(s)
    assert "flying" not in ch(s, card_named(s, FLAYER)).keywords
    check(s)
