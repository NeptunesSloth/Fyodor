"""Wave 110A: Deadpool, Trading Card (612.5 exchange text boxes as a layer 3 effect fixed as he enters, 614.12a "as enters", 102.2 each other player)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.rules import coverage
from tests.wave110a_kit import *

DEADPOOL = "Deadpool, Trading Card"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


def _lines(s, c):
    return sorted(a.text for a in ch(s, c).abilities)


def _scene(cards, pick):
    s = build(cards, [DEADPOOL, "Llanowar Elves"])
    elves = put(s, "Llanowar Elves")
    cast(s, DEADPOOL)
    answer(s, elves.id if pick else "none")
    return s, elves, card_named(s, DEADPOOL)


def test_full(cards):
    assert coverage.of_card_data(cards.resolve(DEADPOOL)).level == "FULL"


def test_declining_keeps_both_texts(cards):
    s, elves, dp = _scene(cards, False)
    assert any("lose 3 life" in t for t in _lines(s, dp)) and not any("lose 3 life" in t for t in _lines(s, elves))
    check(s)


def test_exchanged_text_boxes_swap_the_abilities_and_keep_the_other_characteristics(cards):
    s, elves, dp = _scene(cards, True)
    assert not any("lose 3 life" in t for t in _lines(s, dp)) and any("Add {G}" in t for t in _lines(s, dp))  # Deadpool now has the mana ability
    assert any("lose 3 life" in t for t in _lines(s, elves)) and not any("Add {G}" in t for t in _lines(s, elves))
    assert pt_of(s, dp) == (5, 3) and ch(s, dp).name == DEADPOOL and ch(s, elves).name == "Llanowar Elves"  # only text is exchanged (612.5)
    check(s)


def test_the_elves_with_deadpools_text_pay_life_each_upkeep_and_can_be_sacrificed(cards):
    s, elves, dp = _scene(cards, True)
    start = life(s)
    next_turn(s)  # Alice's next upkeep: Elves has "At the beginning of your upkeep, you lose 3 life."
    assert life(s) == start - 3
    fund(s, "{3}")
    sac = next(a.index for a in ch(s, elves).abilities if a.kind == "activated")
    hand = len(s.state.zones["p2:hand"])
    act(s, "p1", type="activate_ability", card_id=elves.id, ability=sac)
    answer(s)
    assert s.state.cards[elves.id].zone == "p1:graveyard" and len(s.state.zones["p2:hand"]) == hand + 1  # each other player draws a card
    check(s)


def pt_of(s, c):
    from app.rules import sba

    return sba.power(s.state.cards[c.id], ch(s, c)), sba.toughness(s.state.cards[c.id], ch(s, c))


def test_static_abilities_follow_the_exchanged_text(cards):
    s = build(cards, [DEADPOOL, "Muscle Sliver"])
    sliver = put(s, "Muscle Sliver")
    assert pt_of(s, sliver) == (2, 2)  # its own "All Sliver creatures get +1/+1."
    cast(s, DEADPOOL)
    answer(s, sliver.id)
    assert pt_of(s, sliver) == (2, 2)  # Deadpool has the static now and still buffs the Sliver
    act(s, "p1", type="move", card_ids=[card_named(s, DEADPOOL).id], to={"player": "p1", "zone": "graveyard"})
    assert pt_of(s, sliver) == (1, 1)  # the Sliver itself has Deadpool's text: the static went with the text box
    check(s)


def test_exchange_of_words_lasts_while_the_enchantment_stays(cards):  # 612.5, 611.2b; ruling 2022-10-07
    eow = "Exchange of Words"
    s = build(cards, [eow, "Llanowar Elves", "Muscle Sliver", "Naturalize"])
    elves, sliver = put(s, "Llanowar Elves"), put(s, "Muscle Sliver")
    cast(s, eow)
    answer(s, [elves.id, sliver.id])
    assert any("Sliver creatures" in a.text for a in ch(s, elves).abilities) and any("Add {G}" in a.text for a in ch(s, sliver).abilities)
    check(s)
    cast(s, "Naturalize", [card_named(s, eow).id])  # the Enchantment leaves: the exchange ends
    answer(s)
    assert any("Add {G}" in a.text for a in ch(s, elves).abilities) and any("Sliver creatures" in a.text for a in ch(s, sliver).abilities)
    check(s)
