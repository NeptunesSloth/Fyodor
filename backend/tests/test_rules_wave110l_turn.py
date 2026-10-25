"""Wave 110L: this-turn history conditions, real Oracle text, replay and save/load checked.

* Oblivious Bookworm - the discard is skipped if a permanent entered face down under your control this turn (708.2) or you turned one face up (702.37e).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110l_kit import *

BOOK, SUMMONS = "Oblivious Bookworm", "Soul Summons"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([BOOK, SUMMONS])


def hand_size(s, pid="p1"):
    return len(s.state.zones.get(f"{pid}:hand", []))


def manifest_bears(s):
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"zone": "library"}, position="top")
    cast(s, SUMMONS)
    answer(s)


def end_step(s):
    before = hand_size(s)
    to_phase(s, "end")
    answer(s)
    return hand_size(s) - before


def test_bookworm_draws_then_discards_when_nothing_happened(cards):
    s = build(cards, [BOOK, SUMMONS, "Grizzly Bears"])
    put(s, BOOK)
    next_turn(s)
    stops(s)
    assert end_step(s) == 0  # drew one, discarded one
    assert zone_of(s, "Grizzly Bears") != "p1:battlefield"
    check(s)


def test_bookworm_keeps_the_card_when_a_permanent_entered_face_down(cards):
    s = build(cards, [BOOK, SUMMONS, "Grizzly Bears"])
    put(s, BOOK)
    next_turn(s)
    stops(s)
    manifest_bears(s)
    assert end_step(s) == 1
    check(s)


def test_bookworm_keeps_the_card_when_you_turned_a_permanent_face_up(cards):
    s = build(cards, [BOOK, SUMMONS, "Grizzly Bears"])
    put(s, BOOK)
    manifest_bears(s)  # on an earlier turn: it does not count now
    face_down = next(c for c in s.state.cards.values() if c.face_down and c.owner == "p1")
    next_turn(s)
    stops(s)
    fund(s, "{1}{G}")
    act(s, "p1", type="turn_face_up", card_id=face_down.id)
    answer(s)
    assert end_step(s) == 1
    check(s)



WAR = "The First Tyrannic War"
test_full_war = full_test([WAR])


def counters(s, name):
    return card_named(s, name).counters.get("+1/+1", 0)


@pytest.mark.parametrize(("creature", "expect"), [("Walking Ballista", 3), ("Grizzly Bears", 0)])
def test_first_tyrannic_war_counters_only_for_a_mana_cost_with_x(cards, creature, expect):
    s = build(cards, [WAR, creature], forests=9)
    for land in [c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1"][:3]:  # three lands (the rest stay in the library)
        act(s, "p1", type="move", card_ids=[land.id], to={"player": "p1", "zone": "battlefield"})
    to_hand(s, creature)
    cast(s, WAR)
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    answer(s, "Yes", creature)  # "you may", then the card
    assert zone_of(s, creature) == "p1:battlefield"
    assert counters(s, creature) == expect
    check(s)
