"""Wave 110N: Grip of Amnesia (118.12a counter unless the spell's controller exiles their graveyard; an empty graveyard can still be exiled)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

GRIP = "Grip of Amnesia"
EXTRA = [real("Flash Squire", "{U}", 1, "Creature — Human", "Flash", ("1", "1"), "U"), real("Make Token", "{W}", 1, "Instant", "Create a 1/1 white Soldier creature token.", None, "W")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([GRIP])




@pytest.mark.parametrize(("grave", "choice"), [(1, "pay"), (1, "decline"), (0, "pay"), (0, "decline")])
def test_the_spell_is_countered_unless_its_controller_exiles_their_graveyard(cards, grave, choice):
    s = build(cards, [GRIP, "Make Token"], ["Flash Squire", "Llanowar Elves"])
    if grave:
        act(s, "p2", type="move", card_ids=[card_named(s, "Llanowar Elves", "p2").id], to={"player": "p2", "zone": "graveyard"})
    for pid in ("p1", "p2"):
        act(s, pid, type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    cast(s, "Make Token")
    mana(s, "p2", U=1)
    squire = cast(s, "Flash Squire", pid="p2", pay=False)
    while s.state.rules.priority != "p1":
        act(s, s.state.rules.priority, type="pass_priority")
    assert squire.id in s.state.zones["stack"]
    hand = len(s.state.zones["p1:hand"])
    cast(s, GRIP, [squire.id])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p2" and {o.id for o in d.options} == {"pay", "decline"}  # asked even with an empty graveyard
    act(s, "p2", type="choose", decision_id=d.id, option_ids=[choice])
    answer(s)
    assert zone_of(s, "Flash Squire", "p2") == ("p2:battlefield" if choice == "pay" else "p2:graveyard")
    if grave:
        assert (zone_of(s, "Llanowar Elves", "p2") == "p2:exile") is (choice == "pay")
    assert len(s.state.zones["p1:hand"]) == hand + 1  # a card drawn (the Grip came to the hand and left it)
    check(s)
