"""Wave 110N: Jace, Reality Sculptor (701.71 empower Jace, a watch until your next turn for attackers of you or your planeswalkers, 606 loyalty abilities and an activation condition)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

JACE = "Jace, Reality Sculptor"


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, [])


test_full = full_test([JACE])


def tokens(s):
    return [c for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.is_token and "Jace" in ch(s, c).subtypes]


def loyalty(s, c):
    return s.state.cards[c.id].counters.get("loyalty", 0)


def setup(cards, islands=3):
    s = build(cards, [JACE, "Island", "Island", "Island"], forests=9, islands=20)
    for c in [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p1"][:islands]:
        act(s, "p1", type="move", card_ids=[c.id], to={"player": "p1", "zone": "battlefield"})
    jace = cast(s, JACE)
    answer(s)
    return s, jace


def plus(s, jace, ability):
    act(s, "p1", type="activate_ability", card_id=jace.id, ability=ability)
    answer(s)


def test_empower_creates_one_jace_token_and_then_adds_to_it(cards):
    s, jace = setup(cards)
    plus(s, jace, 0)
    assert loyalty(s, jace) == 6 and len(tokens(s)) == 1 and loyalty(s, tokens(s)[0]) == 3  # (three Islands)
    texts = " ".join(a.text for a in ch(s, tokens(s)[0]).abilities)
    assert "Surveil 1" in texts and "Draw a card" in texts and ch(s, tokens(s)[0]).colors == {"U"}
    next_turn(s)
    plus(s, jace, 0)
    assert len(tokens(s)) == 1 and loyalty(s, tokens(s)[0]) == 6  # the same token, three more
    check(s)


def test_attackers_of_you_get_minus_five_power_until_your_next_turn(cards):
    s = build(cards, [JACE], ["Grizzly Bears"], forests=9, islands=9)
    bears = put(s, "Grizzly Bears", "p2")
    jace = cast(s, JACE)
    answer(s)
    plus(s, jace, 1)
    assert loyalty(s, jace) == 2
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    for _ in range(80):  # Bob's turn: the Bears attack Alice
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_attackers":
            act(s, d.player, type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id]) if d is not None else act(s, s.state.rules.priority, type="pass_priority")
    answer(s)
    assert ch(s, bears).pt[0] == 2 - 5
    check(s)


def test_the_zero_needs_twenty_five_loyalty_counters_among_your_jaces(cards):
    s, jace = setup(cards)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=jace.id, ability=2)
    act(s, "p1", type="counter", card_ids=[jace.id], kind="loyalty", delta=20)  # 25 on the Jace
    bottom = s.state.zones["p2:library"][-1]
    before = len(s.state.zones["p2:library"])
    act(s, "p1", type="activate_ability", card_id=jace.id, ability=2)
    answer(s)
    assert s.state.zones["p2:library"] == [bottom] and len(s.state.zones["p2:exile"]) == before - 1
    check(s)


def test_the_counters_of_a_jace_token_count_too(cards):
    s, jace = setup(cards)
    plus(s, jace, 0)  # Jace 6, the token 3
    act(s, "p1", type="counter", card_ids=[tokens(s)[0].id], kind="loyalty", delta=15)  # 6 + 18 = 24
    next_turn(s)
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=jace.id, ability=2)
    act(s, "p1", type="counter", card_ids=[tokens(s)[0].id], kind="loyalty", delta=1)  # 25 among the Jaces
    act(s, "p1", type="activate_ability", card_id=jace.id, ability=2)
    answer(s)
    assert len(s.state.zones["p2:library"]) == 1
    check(s)
