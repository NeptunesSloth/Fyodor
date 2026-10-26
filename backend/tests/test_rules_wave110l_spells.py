"""Wave 110L: spells with loops and alternating choices, real Oracle text, replay and save/load checked.

* Forbidden Ritual - each pass sacrifices a nontoken permanent; the opponent loses 2 life unless they sacrifice a permanent or discard a card; repeat at will.
* Struggle for Sanity - the revealed hand is exiled card by card, the opponent first (701.20a, 400.7).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110l_kit import *

RITUAL, STRUGGLE = "Forbidden Ritual", "Struggle for Sanity"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([RITUAL, STRUGGLE])


def clear_hand(s, pid, keep=()):
    for c in list(s.state.zones[f"{pid}:hand"]):
        if s.state.cards[c].name not in keep:
            act(s, pid, type="move", card_ids=[c], to={"zone": "library"})


def names(s, zone, pid):
    return sorted(s.state.cards[c].name for c in s.state.zones.get(f"{pid}:{zone}", []))


def ritual_table(cards, mine=("Grizzly Bears", "Llanowar Elves"), theirs=("Giant Growth",)):
    s = build(cards, [RITUAL, *mine], list(theirs))
    for n in mine:
        put(s, n)
    for n in theirs:
        to_hand(s, n, "p2")
    clear_hand(s, "p2", theirs)
    return s


def test_ritual_opponent_loses_two_life_when_they_pay_nothing(cards):
    s = ritual_table(cards)
    cast(s, RITUAL, ["p2"])
    answer(s, "Grizzly Bears", "life", "no")
    assert life(s, "p2") == 38 and zone_of(s, "Grizzly Bears") == "p1:graveyard"
    check(s)


def test_ritual_opponent_may_sacrifice_a_permanent_instead(cards):
    s = ritual_table(cards, theirs=("Giant Growth", "Grizzly Bears"))
    put(s, "Grizzly Bears", "p2")
    cast(s, RITUAL, ["p2"])
    answer(s, "Llanowar Elves", "sacrifice", "Grizzly Bears", "no")
    assert life(s, "p2") == 40 and zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    check(s)


def test_ritual_opponent_may_discard_a_card_instead(cards):
    s = ritual_table(cards)
    cast(s, RITUAL, ["p2"])
    answer(s, "Llanowar Elves", "discard", "Giant Growth", "no")
    assert life(s, "p2") == 40 and names(s, "graveyard", "p2") == ["Giant Growth"]
    check(s)


def test_ritual_can_repeat_and_stops_when_no_nontoken_permanent_is_left(cards):
    s = ritual_table(cards)
    cast(s, RITUAL, ["p2"])
    answer(s, "Grizzly Bears", "life", "yes", "Llanowar Elves", "life", "yes")  # a third pass finds nothing to sacrifice
    assert life(s, "p2") == 36 and not [n for n in names(s, "battlefield", "p1") if n != "Forest"]
    check(s)


def test_ritual_does_nothing_beyond_the_sacrifice_if_you_cant(cards):
    s = ritual_table(cards, mine=())
    cast(s, RITUAL, ["p2"])
    answer(s)
    assert life(s, "p2") == 40
    check(s)


def struggle_table(cards):
    s = build(cards, [STRUGGLE], ["Giant Growth", "Counterspell", "Opt", "Murder"])
    for n in ("Giant Growth", "Counterspell", "Opt", "Murder"):
        to_hand(s, n, "p2")
    clear_hand(s, "p2", ("Giant Growth", "Counterspell", "Opt", "Murder"))
    return s


def test_struggle_for_sanity_alternates_and_splits_the_hand(cards):
    s = struggle_table(cards)
    cast(s, STRUGGLE, ["p2"])
    # Bob exiles Giant Growth, Alice exiles Counterspell, Bob exiles Opt, Alice exiles the last card (Murder, no choice)
    answer(s, "Giant Growth", "Counterspell", "Opt")
    assert names(s, "hand", "p2") == ["Giant Growth", "Opt"]
    assert names(s, "graveyard", "p2") == ["Counterspell", "Murder"] and not names(s, "exile", "p2")
    check(s)


def test_struggle_for_sanity_with_an_empty_hand_does_nothing(cards):
    s = struggle_table(cards)
    clear_hand(s, "p2")
    cast(s, STRUGGLE, ["p2"])
    answer(s)
    assert not names(s, "hand", "p2") and not names(s, "graveyard", "p2")
    check(s)
