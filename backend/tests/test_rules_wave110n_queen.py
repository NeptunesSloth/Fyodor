"""Wave 110N: Coffin Queen (603.7 one delayed trigger, two events: the Queen untaps / her controller loses control of her)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

QUEEN = "Coffin Queen"
EXTRA = [real("Take Back", "{1}", 1, "Sorcery", "Gain control of target creature.", None, "U")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([QUEEN])


def animate(cards, theirs=()):
    s = build(cards, [QUEEN, "Grizzly Bears"], list(theirs))
    queen = put(s, QUEEN)
    act(s, "p1", type="move", card_ids=[card_named(s, "Grizzly Bears").id], to={"player": "p1", "zone": "graveyard"})
    next_turn(s)  # (no summoning sickness for the {T} cost)
    mana(s, "p1", B=1, C=2)
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="activate_ability", card_id=queen.id, ability=1, targets=[bears.id])
    answer(s)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield"
    return s, queen, bears


def untap_step(s, keep):
    """Alice's next untap step: the "keep tapped" question is answered with ``keep`` (the Queen's "you may choose not to untap")."""
    act(s, "p1", type="set_stops", own=STEPS, others=STEPS, smart_pass=False)
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and "Untap step" in (d.prompt or ""):
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options] if keep else [])
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[d.options[0].id]) if d is not None else act(s, s.state.rules.priority, type="pass_priority")
    answer(s)


def test_it_is_exiled_when_the_queen_untaps(cards):
    s, queen, bears = animate(cards)
    assert s.state.cards[queen.id].tapped
    untap_step(s, keep=False)
    assert zone_of(s, "Grizzly Bears") == "p1:exile"
    check(s)


def test_choosing_not_to_untap_keeps_it(cards):
    s, queen, bears = animate(cards)
    untap_step(s, keep=True)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and s.state.cards[queen.id].tapped
    check(s)


def test_it_is_exiled_when_you_lose_control_of_the_queen(cards):
    s, queen, bears = animate(cards, ["Take Back"])
    stops(s)
    until(s, lambda s: s.state.turn.active_player == "p2" and s.state.turn.phase == "main1" and s.state.rules.priority == "p2")
    mana(s, "p2", C=1)
    cast(s, "Take Back", [queen.id], pid="p2")
    answer(s)
    assert s.state.cards[queen.id].controller == "p2" and zone_of(s, "Grizzly Bears") == "p1:exile"
    check(s)


def test_it_stays_while_the_queen_stays_tapped_and_yours(cards):
    s, queen, bears = animate(cards)
    assert zone_of(s, "Grizzly Bears") == "p1:battlefield" and s.state.cards[queen.id].tapped
    check(s)
