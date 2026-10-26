"""Wave 110B: the Final Fantasy "Limit Break" tiered spells (702.183a: choose one tier, pay its cost as an additional cost), real Oracle text
(tests/fixtures/wave110b_cards.json). Every scenario checks the replay and a save and a load.

* Tifa's Limit Break: +2/+2, double (701.10b) or triple (701.11b: +X/+Y with X, Y twice the power and toughness as it resolves) until end of turn.
* Cloud's Limit Break: destroy a tapped creature, any number of tapped creatures with different controllers (115.1, 601.2c), or all tapped creatures.
* Vincent's Limit Break: the creature you control has the tier's base power and toughness (613.4b) and returns tapped when it dies this turn.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.wave110b_kit import build, card_named, check, drive, mana, pt, put, repository, to_hand


@pytest.fixture()
def cards(settings):
    yield from repository(settings)


@pytest.mark.parametrize("name", ["Tifa's Limit Break", "Cloud's Limit Break", "Vincent's Limit Break"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


@pytest.mark.parametrize("mode, extra, size", [(0, {}, (4, 4)), (1, {"C": 2}, (4, 4)), (2, {"C": 6, "G": 2}, (6, 6))])
def test_tifa_pumps_doubles_or_triples_power_and_toughness(cards, mode, extra, size):
    s = build(cards, ["Tifa's Limit Break", "Grizzly Bears"], [])
    bears = put(s, "Grizzly Bears")
    mana(s, "p1", **{"G": 1, **extra})
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Tifa's Limit Break").id, modes=[mode], targets=[bears.id])
    drive(s)
    assert pt(s, "Grizzly Bears") == size  # 2/2: +2/+2; doubled +2/+2; tripled +4/+4
    check(s)


def test_tifa_cant_cast_a_tier_without_paying_its_cost(cards):
    s = build(cards, ["Tifa's Limit Break", "Grizzly Bears"], [])
    bears = put(s, "Grizzly Bears")
    mana(s, "p1", G=1, C=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Tifa's Limit Break").id, modes=[1], targets=[bears.id])  # Meteor Strikes costs {2} more
    check(s)


def tap(s, *cards_):
    act(s, "p1", type="tap", card_ids=[c.id for c in cards_], tapped=True)


def test_cloud_cross_slash_destroys_one_tapped_creature(cards):
    s = build(cards, ["Cloud's Limit Break", "Grizzly Bears"], ["Grizzly Bears"])
    mine, theirs = put(s, "Grizzly Bears"), put(s, "Grizzly Bears", "p2")
    tap(s, theirs)
    mana(s, "p1", W=1, G=1)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Cloud's Limit Break").id, modes=[0], targets=[mine.id])  # untapped: no target
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Cloud's Limit Break").id, modes=[0], targets=[theirs.id])
    drive(s)
    assert s.state.cards[theirs.id].zone == "p2:graveyard" and s.state.cards[mine.id].zone == "p1:battlefield"
    check(s)


def test_cloud_blade_beam_takes_tapped_creatures_with_different_controllers_only(cards):
    s = build(cards, ["Cloud's Limit Break", "Grizzly Bears", "Garruk's Horde"], ["Grizzly Bears", "Garruk's Horde"])
    a1, a2 = put(s, "Grizzly Bears"), put(s, "Garruk's Horde")
    b1, b2 = put(s, "Grizzly Bears", "p2"), put(s, "Garruk's Horde", "p2")
    tap(s, a1, a2, b1, b2)
    mana(s, "p1", W=1, C=2)
    cast = card_named(s, "Cloud's Limit Break")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=to_hand(s, "Cloud's Limit Break").id, modes=[1], targets=[a1.id, a2.id], target_counts=[2])  # both Alice's
    act(s, "p1", type="cast_spell", card_id=cast.id, modes=[1], targets=[a2.id, b1.id], target_counts=[2])
    drive(s)
    assert [s.state.cards[c.id].zone for c in (a1, a2, b1, b2)] == ["p1:battlefield", "p1:graveyard", "p2:graveyard", "p2:battlefield"]
    check(s)


def test_cloud_omnislash_destroys_all_tapped_creatures_and_spares_untapped_ones(cards):
    s = build(cards, ["Cloud's Limit Break", "Grizzly Bears", "Llanowar Elves"], ["Grizzly Bears"])
    a, e = put(s, "Grizzly Bears"), put(s, "Llanowar Elves")
    b = put(s, "Grizzly Bears", "p2")
    tap(s, a, b)
    mana(s, "p1", W=2, C=4)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Cloud's Limit Break").id, modes=[2])
    drive(s)
    assert [s.state.cards[c.id].zone for c in (a, e, b)] == ["p1:graveyard", "p1:battlefield", "p2:graveyard"]
    check(s)


@pytest.mark.parametrize("mode, size, extra", [(0, (3, 2), 0), (1, (5, 2), 1), (2, (7, 2), 3)])
def test_vincent_sets_base_power_and_toughness_and_returns_the_creature_tapped_when_it_dies(cards, mode, size, extra):
    s = build(cards, ["Vincent's Limit Break", "Garruk's Horde", "Lightning Bolt"], [])
    horde = put(s, "Garruk's Horde")
    mana(s, "p1", B=1, C=1 + extra)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Vincent's Limit Break").id, modes=[mode], targets=[horde.id])
    drive(s)
    assert pt(s, "Garruk's Horde") == size  # (a 7/7 with base 3/2, 5/2 or 7/2)
    mana(s, "p1", R=1)
    act(s, "p1", type="cast_spell", card_id=to_hand(s, "Lightning Bolt").id, targets=[horde.id])
    drive(s)
    got = s.state.cards[horde.id]
    assert got.zone == "p1:battlefield" and got.tapped  # (it died to 3 damage and came back: a new object, tapped)
    check(s)
