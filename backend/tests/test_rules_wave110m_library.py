"""Wave 110M: effects that read or move the top card of a library. Every scenario checks the replay and a save and a load.

* 613.4c, 400.7: "As long as the top card of your library is a creature card, creatures you control that share a color with that card get +1/+1." and
  "{G}{W}: Put the top card of your library on the bottom of your library." (Crown of Convergence).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110m_kit import *

CROWN = "Crown of Convergence"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([CROWN])


def on_top(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return c


def top(s, pid="p1"):
    return s.state.zones[f"{pid}:library"][0]


# top card -> (Bears (green) pt, Lions (white) pt)
@pytest.mark.parametrize("top_name,bears,lions", [
    ("Llanowar Elves", (3, 3), (2, 1)),     # a green creature card: green creatures
    ("Elite Vanguard", (2, 2), (3, 2)),      # a white creature card: white creatures
    ("Forest", (2, 2), (2, 1)),              # not a creature card: nobody
])
def test_crown_pumps_the_creatures_sharing_a_color_with_a_top_creature_card(cards, top_name, bears, lions):
    s = build(cards, [CROWN, "Grizzly Bears", "Savannah Lions", "Llanowar Elves", "Elite Vanguard"])
    for n in (CROWN, "Grizzly Bears", "Savannah Lions"):
        put(s, n)
    on_top(s, top_name)
    assert pt(s, "Grizzly Bears") == bears and pt(s, "Savannah Lions") == lions
    check(s)


def test_crown_ability_puts_the_top_card_on_the_bottom_and_the_bonus_follows(cards):
    s = build(cards, [CROWN, "Grizzly Bears", "Savannah Lions", "Llanowar Elves", "Elite Vanguard"])
    crown = put(s, CROWN)
    put(s, "Grizzly Bears")
    put(s, "Savannah Lions")
    vanguard = on_top(s, "Elite Vanguard")
    elves = on_top(s, "Llanowar Elves")
    assert pt(s, "Grizzly Bears") == (3, 3) and pt(s, "Savannah Lions") == (2, 1)
    mana(s, G=1, W=1)
    act(s, "p1", type="activate_ability", card_id=crown.id, ability=2)
    answer(s)
    assert top(s) == vanguard.id and s.state.zones["p1:library"][-1] == elves.id
    assert pt(s, "Grizzly Bears") == (2, 2) and pt(s, "Savannah Lions") == (3, 2)
    check(s)


# -- Faces of the Past ----------------------------------------------------------------------------------------------------------------
FACES = "Faces of the Past"


@pytest.mark.parametrize("choice,tapped_after", [("tap", {"Mother of Runes": True, "Llanowar Elves": False, "Savannah Lions": False}),
                                                  ("untap", {"Mother of Runes": False, "Llanowar Elves": True, "Savannah Lions": True})])
def test_faces_of_the_past_taps_or_untaps_only_creatures_sharing_a_type_with_the_dead_one(cards, choice, tapped_after):
    """The controller picks as it resolves; Elite Vanguard (Human Soldier) died, so only the other Human shares a creature type with it (not the Elf or the Cat)."""
    s = build(cards, [FACES, "Elite Vanguard", "Mother of Runes", "Llanowar Elves", "Savannah Lions", "Murder"], forests=20)
    put(s, FACES)
    vanguard = put(s, "Elite Vanguard")
    for n in tapped_after:
        put(s, n)
    if choice == "untap":  # (everything else starts tapped, so only the creatures sharing a type change)
        act(s, "p1", type="tap", card_ids=[card_named(s, n).id for n in tapped_after], tapped=True)
    cast(s, "Murder", [vanguard.id])
    answer(s, choice)
    assert s.state.cards[vanguard.id].zone == "p1:graveyard"
    assert {n: s.state.cards[card_named(s, n).id].tapped for n in tapped_after} == tapped_after
    check(s)


def test_faces_of_the_past_with_a_dying_changeling_reaches_every_creature_with_a_type(cards):
    """702.73a: a changeling has every creature type, so every creature with a creature type shares one with it."""
    s = build(cards, [FACES, "Changeling Outcast", "Mother of Runes", "Llanowar Elves", "Murder"], forests=20)
    put(s, FACES)
    outcast = put(s, "Changeling Outcast")
    put(s, "Mother of Runes")
    put(s, "Llanowar Elves")
    cast(s, "Murder", [outcast.id])
    answer(s, "tap")
    assert s.state.cards[card_named(s, "Mother of Runes").id].tapped and s.state.cards[card_named(s, "Llanowar Elves").id].tapped
    check(s)


# -- Lucius the Eternal ----------------------------------------------------------------------------------------------------------------------
LUCIUS = "Lucius the Eternal"
test_lucius_full = full_test([LUCIUS])


def lucius_table(cards, theirs=("Grizzly Bears",)):
    s = build(cards, [LUCIUS, "Murder", "Doom Blade"], list(theirs), forests=20)
    lucius = put(s, LUCIUS)
    for n in theirs:
        put(s, n, "p2")
    return s, lucius


@pytest.mark.parametrize("dies,returns", [("Elite Vanguard", True), ("Grizzly Bears", False)])
def test_lucius_exiles_itself_and_returns_when_the_chosen_creature_leaves(cards, dies, returns):
    s, lucius = lucius_table(cards, ("Grizzly Bears", "Elite Vanguard"))
    cast(s, "Murder", [lucius.id])
    answer(s, card_named(s, "Elite Vanguard", "p2").id)  # (the chosen creature: Elite Vanguard)
    assert s.state.cards[lucius.id].zone == "p1:exile"
    check(s)
    cast(s, "Doom Blade", [card_named(s, dies, "p2").id])
    answer(s)
    assert zone_of(s, dies, "p2") == "p2:graveyard"
    assert (s.state.cards[lucius.id].zone, s.state.cards[lucius.id].controller) == (("p1:battlefield", "p1") if returns else ("p1:exile", "p1"))
    check(s)


def test_lucius_with_no_opponent_creature_to_choose_stays_in_the_graveyard(cards):
    s, lucius = lucius_table(cards, ())
    cast(s, "Murder", [lucius.id])
    answer(s)
    assert s.state.cards[lucius.id].zone == "p1:graveyard"
    check(s)
