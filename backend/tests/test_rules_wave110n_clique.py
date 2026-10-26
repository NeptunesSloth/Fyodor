"""Wave 110N: Mistbind Clique (702.72 champion, 702.72c "championed" = exiled by the champion ability, 603.12 its trigger targets after the exile)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

CLIQUE, FAERIE = "Mistbind Clique", "Faerie Scout"
EXTRA = [real(FAERIE, "{U}", 1, "Creature — Faerie", "Flying", ("1", "1"), "U")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([CLIQUE])


def step(s, *ids):
    for _ in range(30):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=list(ids))


def setup(cards, faerie=True):
    s = build(cards, [CLIQUE, FAERIE, "Murder"], ["Island"], islands=5)
    if faerie:
        put(s, FAERIE)
    for c in [c for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][:3]:
        act(s, "p2", type="move", card_ids=[c.id], to={"player": "p2", "zone": "battlefield"})
    cast(s, CLIQUE)
    return s


def test_championing_a_faerie_taps_all_lands_of_the_target_player(cards):
    s = setup(cards)
    step(s, "pay")
    d = s.state.rules.decision
    if d is not None and "Exile" in (d.prompt or ""):
        step(s, card_named(s, FAERIE).id)
    step(s, "p2")  # the reflexive trigger's target
    answer(s)
    assert zone_of(s, CLIQUE) == "p1:battlefield" and zone_of(s, FAERIE) == "p1:exile"
    lands = [c for c in s.state.cards.values() if c.zone == "p2:battlefield" and c.name == "Island"]
    assert len(lands) == 3 and all(c.tapped for c in lands)
    check(s)


def test_not_championing_sacrifices_it_and_taps_nothing(cards):
    s = setup(cards)
    step(s, "decline")
    answer(s)
    assert zone_of(s, CLIQUE) == "p1:graveyard" and zone_of(s, FAERIE) == "p1:battlefield"
    assert not any(c.tapped for c in s.state.cards.values() if c.zone == "p2:battlefield")
    check(s)


def test_without_another_faerie_it_is_sacrificed(cards):
    s = setup(cards, faerie=False)
    answer(s)
    assert zone_of(s, CLIQUE) == "p1:graveyard"
    check(s)


def test_the_championed_faerie_returns_when_it_leaves(cards):
    s = setup(cards)
    step(s, "pay")
    d = s.state.rules.decision
    if d is not None and "Exile" in (d.prompt or ""):
        step(s, card_named(s, FAERIE).id)
    step(s, "p2")
    answer(s)
    mana(s, "p1", B=3)
    cast(s, "Murder", [card_named(s, CLIQUE).id], pay=False)
    answer(s)
    assert zone_of(s, CLIQUE) == "p1:graveyard" and zone_of(s, FAERIE) == "p1:battlefield"
    check(s)
