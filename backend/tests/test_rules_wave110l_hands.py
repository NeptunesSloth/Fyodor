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


DESCENT = "Descent into Madness"
test_full_descent = full_test([DESCENT])


def to_upkeep_trigger(s):
    """Pass until Alice's next upkeep trigger asks Alice something (or settles)."""
    for _ in range(60):
        if s.state.rules.decision is not None:
            return s.state.rules.decision
        act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("no decision")


def test_descent_into_madness_each_player_exiles_x_from_permanents_and_hand(cards):
    s = build(cards, [DESCENT, "Grizzly Bears", "Llanowar Elves"], ["Giant Growth"])
    put(s, DESCENT)
    put(s, "Grizzly Bears")
    put(s, "Llanowar Elves")
    keep = {"Giant Growth"}
    for pid in ("p1", "p2"):  # hands: p1 empty, p2 only Giant Growth
        for c in list(s.state.zones[f"{pid}:hand"]):
            if s.state.cards[c].name not in keep:
                act(s, pid, type="move", card_ids=[c], to={"zone": "library"})
    to_hand(s, "Giant Growth", "p2")
    act(s, "p1", type="set_stops", own=["upkeep"], others=["upkeep"], smart_pass=False)
    for _ in range(60):  # to Alice's next upkeep: the counter is put (X = 1), then she chooses one of her three permanents, Bob exiles his only card
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p1" and {o.label for o in d.options} == {DESCENT, "Grizzly Bears", "Llanowar Elves"}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.label == "Grizzly Bears")])
    answer(s)
    assert zone_of(s, "Grizzly Bears") == "p1:exile" and zone_of(s, "Giant Growth", "p2") == "p2:exile"
    assert zone_of(s, "Llanowar Elves") == "p1:battlefield"
    check(s)


SLITH = "Etched Slith"
test_full_slith = full_test([SLITH])


def slith_hit(cards, poison=0, counters_on_bears=0):
    s = build(cards, [SLITH, "Grizzly Bears"])
    slith = put(s, SLITH)
    bears = put(s, "Grizzly Bears")
    if counters_on_bears:
        act(s, "p1", type="counter", card_ids=[bears.id], kind="charge", delta=counters_on_bears)
    if poison:
        act(s, "p1", type="resource", player="p2", key="poison", delta=poison)
    next_turn(s)
    stops(s)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": slith.id, "target": "p2"}])
    to_phase(s, "combat_damage")
    return s, slith, bears


def test_slith_can_remove_a_counter_from_another_permanent(cards):
    s, slith, bears = slith_hit(cards, counters_on_bears=2)
    d = resolve_to_decision(s)
    assert d is not None
    ids = {o.label: o.id for o in d.options}
    assert "Etched Slith" not in ids and "Grizzly Bears" in ids  # another permanent only
    pick(s, d, "Grizzly Bears")
    answer(s)
    assert card_named(s, "Grizzly Bears").counters.get("charge") == 1 and card_named(s, SLITH).counters.get("+1/+1") == 1
    check(s)


def test_slith_can_remove_a_counter_from_an_opponent(cards):
    s, slith, bears = slith_hit(cards, poison=3)
    d = resolve_to_decision(s)
    pick(s, d, "Bob")
    answer(s)
    assert s.state.players["p2"].resources.get("poison") == 2
    check(s)


WINTER = "Winter, Cynical Opportunist"
test_full_winter = full_test([WINTER])


def winter_table(cards):
    s = build(cards, [WINTER, "Grizzly Bears", "Sol Ring", "Lightning Bolt", "Giant Growth"])
    put(s, WINTER)
    for n in ("Grizzly Bears", "Sol Ring", "Lightning Bolt", "Giant Growth"):
        c = card_named(s, n)
        act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "graveyard"})
    stops(s)
    to_phase(s, "end")
    d = resolve_to_decision(s)
    assert d is not None and d.min_choices == 0
    return s, d


def resolve_to_decision(s):
    while s.state.rules.decision is None and s.state.zones.get("stack"):
        act(s, s.state.rules.priority, type="pass_priority")
    return s.state.rules.decision


def test_winter_exiles_four_types_and_puts_a_permanent_card_back_with_a_finality_counter(cards):
    s, d = winter_table(cards)
    ids = {o.label: o.id for o in d.options}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[ids[n] for n in ("Grizzly Bears", "Sol Ring", "Forest", "Lightning Bolt")])
    d = resolve_to_decision(s)
    pick(s, d, "Sol Ring")
    answer(s)
    assert zone_of(s, "Sol Ring") == "p1:battlefield" and card_named(s, "Sol Ring").counters.get("finality") == 1
    assert zone_of(s, "Grizzly Bears") == zone_of(s, "Forest") == zone_of(s, "Lightning Bolt") == "p1:exile"
    assert zone_of(s, "Giant Growth") == "p1:graveyard"
    check(s)


def test_winter_refuses_fewer_than_four_card_types(cards):
    from app.game.errors import ActionError

    s, d = winter_table(cards)
    ids = {o.label: o.id for o in d.options}
    with pytest.raises(ActionError):
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[ids[n] for n in ("Grizzly Bears", "Sol Ring", "Lightning Bolt", "Giant Growth")])


def test_winter_may_exile_nothing(cards):
    s, d = winter_table(cards)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    answer(s)
    assert len(s.state.zones["p1:graveyard"]) == 5 and not s.state.zones.get("p1:exile")
    check(s)
