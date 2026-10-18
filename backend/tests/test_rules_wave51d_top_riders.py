"""Wave 51D: the riders of a cast from the top of the library (CR 2026-09-25), real Oracle text (tests/fixtures/wave51d_cards.json, from data/cards.sqlite). Every scenario
checks the replay and a save and a load.

* 601.3b: Elsha of the Infinite - "You may cast noncreature spells from the top of your library. If you cast a spell this way, you may cast it as though it had flash."
  The flash is only for a spell cast from the top with that permission (a spell in the hand keeps its own timing).
* 614.1c: Mikey & Don - "If you cast a creature spell this way, that creature enters with an additional +1/+1 counter on it." (a creature cast from the hand gets none).
* 611.2a / 613.1f: Thundermane Dragon - "If you cast a creature spell this way, it gains haste until end of turn." (only that turn).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from app.rules import coverage
from tests.game_helpers import act
from tests.test_rules_wave34b_activated import settle, stops, to_phase
from tests.wave9c_kit import build, card_named, check, mana, pt, put, reloaded, to_hand, zone_of
from tests.wave51d_kit import open_repo

ELSHA, MIKEY, DRAGON = "Elsha of the Infinite", "Mikey & Don, Party Planners", "Thundermane Dragon"

@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


@pytest.mark.parametrize("name", [ELSHA, MIKEY, DRAGON])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def on_top(s, name, pid="p1"):
    c = card_named(s, name, pid)
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "library"}, position="top")
    return c


def cast_from_top(s, c, **kw):
    act(s, "p1", type="cast_spell", card_id=c.id, **kw)
    settle(s)


def haste(s, c):
    from app.rules.plan import Plan

    return "haste" in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[c.id]).keywords


# -- Thundermane Dragon ------------------------------------------------------------------------------------------------------------------
def test_thundermane_dragon_gives_a_creature_cast_from_the_top_haste_until_end_of_turn(cards):
    s = build(cards, [DRAGON, "Craw Wurm"], forests=30)
    put(s, DRAGON)
    wurm = on_top(s, "Craw Wurm")
    mana(s, "p1", G=6)
    cast_from_top(s, wurm)
    assert zone_of(s, "Craw Wurm") == "p1:battlefield" and haste(s, wurm)
    check(s)
    assert haste(reloaded(s), wurm)
    to_phase(s, "main1", turn=3)
    assert not haste(s, wurm)  # "until end of turn"


def test_thundermane_dragon_gives_a_creature_cast_from_the_hand_nothing(cards):
    s = build(cards, [DRAGON, "Craw Wurm"], forests=30)
    put(s, DRAGON)
    wurm = to_hand(s, "Craw Wurm")
    mana(s, "p1", G=6)
    act(s, "p1", type="cast_spell", card_id=wurm.id)
    settle(s)
    assert zone_of(s, "Craw Wurm") == "p1:battlefield" and not haste(s, wurm)
    check(s)


def test_thundermane_dragon_cannot_cast_a_small_creature_from_the_top(cards):
    s = build(cards, [DRAGON, "Hill Giant"], forests=30)
    put(s, DRAGON)
    giant = on_top(s, "Hill Giant")
    mana(s, "p1", G=4)
    with pytest.raises(ActionError):
        cast_from_top(s, giant)  # power 3: not "power 4 or greater"
    assert zone_of(s, "Hill Giant") == "p1:library"
    check(s)


# -- Mikey & Don -------------------------------------------------------------------------------------------------------------------------
def test_mikey_and_don_cast_a_ninja_from_the_top_with_an_additional_counter(cards):
    s = build(cards, [MIKEY, "Ninja of the Deep Hours"], forests=30)
    put(s, MIKEY)
    ninja = on_top(s, "Ninja of the Deep Hours")
    mana(s, "p1", U=1, G=3)
    cast_from_top(s, ninja)
    assert zone_of(s, "Ninja of the Deep Hours") == "p1:battlefield"
    assert s.state.cards[ninja.id].counters.get("+1/+1") == 1 and pt(s, "Ninja of the Deep Hours") == (3, 3)
    check(s)
    assert reloaded(s).state.cards[ninja.id].counters.get("+1/+1") == 1


def test_mikey_and_don_cast_from_the_hand_gets_no_counter(cards):
    s = build(cards, [MIKEY, "Ninja of the Deep Hours"], forests=30)
    put(s, MIKEY)
    ninja = to_hand(s, "Ninja of the Deep Hours")
    mana(s, "p1", U=1, G=3)
    act(s, "p1", type="cast_spell", card_id=ninja.id)
    settle(s)
    assert zone_of(s, "Ninja of the Deep Hours") == "p1:battlefield" and not s.state.cards[ninja.id].counters.get("+1/+1")
    check(s)


def test_mikey_and_don_cannot_cast_another_creature_type_from_the_top(cards):
    s = build(cards, [MIKEY, "Hill Giant"], forests=30)
    put(s, MIKEY)
    giant = on_top(s, "Hill Giant")
    mana(s, "p1", G=4)
    with pytest.raises(ActionError):
        cast_from_top(s, giant)
    check(s)


def test_mikey_and_don_plays_a_land_from_the_top(cards):
    s = build(cards, [MIKEY], forests=30)
    put(s, MIKEY)
    land = on_top(s, "Forest")
    act(s, "p1", type="play_land", card_id=land.id)
    assert zone_of(s, "Forest") == "p1:battlefield"
    check(s)


# -- Elsha of the Infinite ---------------------------------------------------------------------------------------------------------------
def test_elsha_casts_a_noncreature_spell_from_the_top_at_instant_speed(cards):
    s = build(cards, [ELSHA, "Smuggler's Copter"], ["Hill Giant"], forests=30)
    put(s, ELSHA)
    copter = on_top(s, "Smuggler's Copter")
    stops(s)
    to_phase(s, "upkeep", turn=2)  # Bob's turn: an artifact is a sorcery-speed spell, unless it has flash
    act(s, "p2", type="pass_priority")
    mana(s, "p1", G=2)
    cast_from_top(s, copter)
    assert zone_of(s, "Smuggler's Copter") == "p1:battlefield"
    check(s)


def test_elsha_gives_a_spell_in_the_hand_no_flash(cards):
    s = build(cards, [ELSHA, "Smuggler's Copter"], ["Hill Giant"], forests=30)
    put(s, ELSHA)
    copter = to_hand(s, "Smuggler's Copter")
    stops(s)
    to_phase(s, "upkeep", turn=2)
    act(s, "p2", type="pass_priority")
    mana(s, "p1", G=2)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=copter.id)
    assert zone_of(s, "Smuggler's Copter") == "p1:hand"
    check(s)
