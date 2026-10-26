"""Wave 110A session 13: real-Oracle scenario tests."""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *

NAMES = ["Ghyrson Starn, Kelermorph", "Averna, the Chaos Bloom"]


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test(NAMES)


def _ping(s, sorc, target):
    act(s, "p1", type="activate_ability", card_id=sorc.id, ability=next(a.index for a in ch(s, sorc).abilities if a.kind == "activated"), targets=[target])
    answer(s)


def _table(cards):
    s = build(cards, ["Ghyrson Starn, Kelermorph", "Prodigal Sorcerer"], ["Grizzly Bears"])
    put(s, "Ghyrson Starn, Kelermorph")
    sorc = put(s, "Prodigal Sorcerer")
    bears = put(s, "Grizzly Bears", "p2")
    next_turn(s)
    return s, sorc, bears


def test_ghyrson_doubles_one_damage_to_a_player(cards):  # 120.3: exactly 1 damage from another source -> 2 more
    s, sorc, _ = _table(cards)
    _ping(s, sorc, "p2")
    assert life(s, "p2") == 40 - 3
    check(s)


def test_ghyrson_doubles_one_damage_to_a_creature(cards):
    s, sorc, bears = _table(cards)
    _ping(s, sorc, bears.id)
    assert s.state.cards[bears.id].zone != "p2:battlefield"  # 1 + 2 = 3 damage kills the 2/2
    check(s)


def test_ghyrson_ignores_other_amounts_and_itself(cards):
    s = build(cards, ["Ghyrson Starn, Kelermorph", "Lightning Bolt"])
    put(s, "Ghyrson Starn, Kelermorph")
    cast(s, "Lightning Bolt", ["p2"])
    answer(s)
    assert life(s, "p2") == 37  # 3 damage: not exactly 1


def _cascade_table(cards, extra_top=()):
    s = build(cards, ["Averna, the Chaos Bloom", "Bloodbraid Elf", "Grizzly Bears"])
    put(s, "Averna, the Chaos Bloom")
    bears = card_named(s, "Grizzly Bears")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "library"}, position="top")
    act(s, "p1", type="move", card_ids=[forest.id], to={"player": "p1", "zone": "library"}, position="top")
    cast(s, "Bloodbraid Elf")
    return s, forest, bears


def test_averna_puts_an_exiled_land_onto_the_battlefield_tapped(cards):  # 702.85a: before deciding whether to cast the nonland card
    s, forest, bears = _cascade_table(cards)
    answer(s, [forest.id], "yes")
    assert s.state.cards[forest.id].zone == "p1:battlefield" and s.state.cards[forest.id].tapped
    assert s.state.cards[card_named(s, "Grizzly Bears").id].zone == "p1:battlefield"  # the cascade still found and cast it
    check(s)


def test_averna_land_is_optional(cards):
    s, forest, bears = _cascade_table(cards)
    answer(s, [], "yes")
    assert s.state.cards[forest.id].zone == "p1:library"  # no land: exiled lands go on the bottom with the rest
    check(s)
