"""Wave 110L: hand disruption chosen by the other player, real Oracle text, replay and save/load checked.

* Rakdos Augermage - each player in turn reveals their hand and the *other* player picks the card (701.9a, 701.20a).
"""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110l_kit import *

AUGER = "Rakdos Augermage"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([AUGER])


def hand(s, pid):
    return sorted(s.state.cards[c].name for c in s.state.zones.get(f"{pid}:hand", []))


def resolve_to_decision(s):
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    return s.state.rules.decision


def pick(s, d, name):
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == name)])


def setup(cards, mine, theirs):
    s = build(cards, [AUGER, *mine], [*theirs])
    a = put(s, AUGER)
    next_turn(s)
    stops(s)
    for n in mine:
        to_hand(s, n)
    for n in theirs:
        to_hand(s, n, "p2")
    return s, a


def test_each_player_discards_the_card_the_other_picks(cards):
    s, a = setup(cards, ["Grizzly Bears", "Lightning Bolt"], ["Giant Growth", "Counterspell"])
    # clear any opening hands so only the named cards are there
    keep = {n for n in ("Grizzly Bears", "Lightning Bolt", "Giant Growth", "Counterspell")}
    for pid in ("p1", "p2"):
        for c in list(s.state.zones[f"{pid}:hand"]):
            if s.state.cards[c].name not in keep:
                act(s, pid, type="move", card_ids=[c], to={"zone": "library"})
    act(s, "p1", type="activate_ability", card_id=a.id, ability=1, targets=["p2"])
    d = resolve_to_decision(s)
    assert d.player == "p2"  # the opponent picks from my revealed hand
    pick(s, d, "Lightning Bolt")
    d = resolve_to_decision(s)
    assert d.player == "p1"
    answer(s, "Counterspell")
    assert hand(s, "p1") == ["Grizzly Bears"] and hand(s, "p2") == ["Giant Growth"]
    check(s)


def empty(s, pid):
    for c in list(s.state.zones[f"{pid}:hand"]):
        act(s, pid, type="move", card_ids=[c], to={"zone": "library"})


def test_empty_hand_reveals_nothing_and_a_single_card_needs_no_choice(cards):
    s, a = setup(cards, [], ["Giant Growth"])
    empty(s, "p1")
    for c in list(s.state.zones["p2:hand"]):
        if s.state.cards[c].name != "Giant Growth":
            act(s, "p2", type="move", card_ids=[c], to={"zone": "library"})
    act(s, "p1", type="activate_ability", card_id=a.id, ability=1, targets=["p2"])
    answer(s)
    assert hand(s, "p1") == [] and hand(s, "p2") == []  # my hand was empty; their only card goes with no choice
    check(s)


def test_the_unpicked_cards_are_hidden_again(cards):
    s, a = setup(cards, ["Grizzly Bears", "Lightning Bolt"], ["Giant Growth", "Counterspell"])
    act(s, "p1", type="activate_ability", card_id=a.id, ability=1, targets=["p2"])
    d = resolve_to_decision(s)
    pick(s, d, "Lightning Bolt")
    d = resolve_to_decision(s)
    pick(s, d, "Counterspell")
    answer(s)
    for pid in ("p1", "p2"):
        assert all(not s.state.cards[c].revealed_to for c in s.state.zones[f"{pid}:hand"])
    check(s)


CHIME = "Apocalypse Chime"
test_full_chime = full_test([CHIME])


def test_apocalypse_chime_destroys_only_names_first_printed_in_homelands(cards):
    s = build(cards, [CHIME, "Hungry Mist", "Grizzly Bears"], ["Aysen Bureaucrats"])
    chime = put(s, CHIME)
    for n in ("Hungry Mist", "Grizzly Bears"):
        put(s, n)
    put(s, "Aysen Bureaucrats", "p2")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=chime.id, ability=0)
    answer(s)
    assert zone_of(s, "Hungry Mist") == "p1:graveyard" and zone_of(s, "Aysen Bureaucrats", "p2") == "p2:graveyard"
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield"
    assert zone_of(s, CHIME) == "p1:graveyard"  # sacrificed as a cost
    check(s)
