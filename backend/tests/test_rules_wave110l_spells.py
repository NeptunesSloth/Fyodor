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


VALEYARD, SYCORAX = "The Valeyard", "Sycorax Commander"
test_full_valeyard = full_test([VALEYARD, SYCORAX])


def facing(s):
    """Cast Sycorax Commander for Alice and answer every villainous choice with the damage option; count how many times Bob faced it."""
    clear_hand(s, "p2", ("Giant Growth", "Opt"))
    cast(s, SYCORAX)
    times = 0
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None:
            assert d.player == "p2" and "villainous" in d.prompt
            times += 1
            act(s, "p2", type="choose", decision_id=d.id, option_ids=["b"])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return times


@pytest.mark.parametrize(("mine", "theirs", "times"), [(0, 0, 1), (1, 0, 2), (0, 1, 1)])
def test_valeyard_adds_a_villainous_choice_for_each_opposing_copy(cards, mine, theirs, times):
    s = build(cards, [SYCORAX, *[VALEYARD] * mine], ["Giant Growth", "Opt", *[VALEYARD] * theirs])
    for n in ("Giant Growth", "Opt"):
        to_hand(s, n, "p2")
    for pid, count in (("p1", mine), ("p2", theirs)):
        for c in [c for c in s.state.cards.values() if c.name == VALEYARD and c.owner == pid][:count]:
            act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    assert facing(s) == times
    assert life(s, "p2") == 40 - 2 * times  # each damage option deals as many as the cards in hand (2)
    check(s)


SUFFOCATION = "Suffocation"
test_full_suffocation = full_test([SUFFOCATION])


def bolt_alice(s):
    """Alice passes in her main phase; Bob answers with Lightning Bolt on her, which resolves."""
    to_hand(s, "Lightning Bolt", "p2")
    act(s, "p1", type="pass_priority")
    mana(s, "p2", R=1)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Lightning Bolt", "p2").id, targets=["p1"])
    while s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")


def test_suffocation_hits_the_controller_of_the_red_spell_and_draws_next_upkeep(cards):
    s = build(cards, [SUFFOCATION], ["Lightning Bolt"])
    stops(s)
    bolt_alice(s)
    assert life(s, "p1") == 37
    before = len(s.state.zones["p1:hand"])
    cast(s, SUFFOCATION)
    answer(s)
    assert life(s, "p2") == 36 and life(s, "p1") == 37
    to_phase(s, "main1", turn=3)
    answer(s)
    assert len(s.state.zones["p1:hand"]) == before + 2  # Suffocation's delayed draw (Bob's upkeep, the next turn's) and her own draw step's
    check(s)


def test_suffocation_cant_be_cast_without_that_damage(cards):
    from app.game.errors import ActionError

    s = build(cards, [SUFFOCATION])
    stops(s)
    with pytest.raises(ActionError):
        cast(s, SUFFOCATION)


def test_suffocation_cant_be_cast_after_damage_from_a_creature(cards):
    from app.game.errors import ActionError

    s = build(cards, [SUFFOCATION], ["Monastery Swiftspear"])
    stops(s)
    put(s, "Monastery Swiftspear", "p2")
    to_phase(s, "declare_attackers", turn=2)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": card_named(s, "Monastery Swiftspear", "p2").id, "target": "p1"}])
    to_phase(s, "end_combat")
    assert life(s, "p1") == 39
    with pytest.raises(ActionError):
        cast(s, SUFFOCATION)
