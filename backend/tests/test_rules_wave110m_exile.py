"""Wave 110M: cards in exile that carry a counter-driven trigger. 702.62c-style "when the last time counter is removed from this card, if it's exiled, you may cast it without paying its
mana cost": granted by Alaundo the Seer to the card it exiles from its controller's hand (no suspend: nothing comes off at upkeep). Every scenario checks the replay and a save and a load.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave36a_kit import ready
from tests.wave110m_kit import *

ALAUNDO = "Alaundo the Seer"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([ALAUNDO])


def table(cards, hand=("Lightning Bolt",)):
    s = build(cards, [ALAUNDO, *hand], ["Elite Vanguard"], forests=20)
    ship = put(s, ALAUNDO)
    ready(s, ALAUNDO)
    for n in hand:
        to_hand(s, n)
    return s, ship


def activate(s, ship, pick):
    act(s, "p1", type="activate_ability", card_id=ship.id, ability=0)
    d = None
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.kind == "choose_cards" and d.min_choices == 1
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[card_named(s, pick).id])
    answer(s)


def test_the_exiled_card_gets_time_counters_equal_to_its_mana_value(cards):
    s, ship = table(cards, ["Grizzly Bears"])
    activate(s, ship, "Grizzly Bears")
    bears = card_named(s, "Grizzly Bears")
    assert bears.zone == "p1:exile" and bears.counters.get("time") == 2
    check(s)


def test_a_mana_value_zero_card_gets_no_counters_and_never_triggers(cards):
    s, ship = table(cards, [])
    # (the drawn card is the one exiled: a Forest, mana value 0)
    act(s, "p1", type="activate_ability", card_id=ship.id, ability=0)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)
    exiled = [c for c in s.state.cards.values() if c.zone == "p1:exile"]
    assert len(exiled) == 1 and not exiled[0].counters.get("time")
    check(s)


def test_the_next_activation_takes_a_counter_off_the_other_card_and_casts_it_when_it_was_the_last(cards):
    s, ship = table(cards, ["Lightning Bolt", "Grizzly Bears"])
    activate(s, ship, "Lightning Bolt")  # (1 counter)
    stops(s)
    next_turn(s)
    ready(s, ALAUNDO)
    act(s, "p1", type="activate_ability", card_id=ship.id, ability=0)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards" and d.min_choices == 1:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[card_named(s, "Grizzly Bears").id])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    for _ in range(30):  # the Bolt's last counter came off: its owner may cast it for free
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "choose_one" and "yes" in [o.id for o in d.options]:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes"])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2" if "p2" in [o.id for o in d.options] else d.options[0].id])
    assert zone_of(s, "Lightning Bolt") == "p1:graveyard" and life(s, "p2") == 37
    assert card_named(s, "Grizzly Bears").counters.get("time") == 2  # (the card just exiled keeps all its counters)
    check(s)


def test_a_creature_cast_this_way_has_haste_until_end_of_turn(cards):
    s, ship = table(cards, ["Llanowar Elves", "Grizzly Bears"])
    activate(s, ship, "Llanowar Elves")
    stops(s)
    next_turn(s)
    ready(s, ALAUNDO)
    act(s, "p1", type="activate_ability", card_id=ship.id, ability=0)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards" and d.min_choices == 1:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[card_named(s, "Grizzly Bears").id])
            break
        act(s, s.state.rules.priority, type="pass_priority")
    for _ in range(30):
        d = s.state.rules.decision
        if d is None:
            if not s.state.zones.get("stack"):
                break
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["yes" if "yes" in [o.id for o in d.options] else d.options[0].id])
    elves = card_named(s, "Llanowar Elves")
    assert elves.zone == "p1:battlefield" and "haste" in ch(s, elves).keywords
    next_turn(s)
    assert "haste" not in ch(s, s.state.cards[elves.id]).keywords
    check(s)
