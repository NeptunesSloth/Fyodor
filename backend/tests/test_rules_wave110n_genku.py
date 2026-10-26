"""Wave 110N: Genku, Future Shaper (700.2 modal trigger, "that hasn't been chosen this turn": a mode once per turn)."""

# ruff: noqa: F403, F405
from __future__ import annotations

import pytest

from tests.wave110n_kit import *
from tests.wave110n_kit import open_repo_with

GENKU = "Genku, Future Shaper"
EXTRA = [real("Wall Squire", "{1}{G}", 2, "Creature — Human", "", ("2", "2"), "G"), real("Pit Squire", "{1}{G}", 2, "Creature — Human", "", ("2", "2"), "G")]


@pytest.fixture()
def cards(settings):
    yield from open_repo_with(settings, EXTRA)


test_full = full_test([GENKU])


def tokens(s):
    return sorted(c.name for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.is_token)


def lose(s, name):
    """One of Alice's own nontoken permanents leaves the battlefield (a Murder on it)."""
    mana(s, "p1", B=3)
    cast(s, "Murder", [card_named(s, name).id], pay=False)


def mode_decision(s):
    for _ in range(20):
        if s.state.rules.decision is not None or not s.state.zones.get("stack"):
            return s.state.rules.decision
        act(s, s.state.rules.priority, type="pass_priority")


def pick(s, token):
    d = mode_decision(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if token in o.label)])


def test_each_mode_is_made_once_per_turn(cards):
    s = build(cards, [GENKU, "Murder", "Grizzly Bears", "Llanowar Elves", "Wall Squire"])
    put(s, GENKU)
    for n in ("Grizzly Bears", "Llanowar Elves", "Wall Squire"):
        put(s, n)
    lose(s, "Grizzly Bears")
    pick(s, "Fox")
    answer(s)
    assert tokens(s) == ["Fox"]
    lose(s, "Llanowar Elves")
    d = mode_decision(s)
    assert d is not None and not any("Fox" in o.label for o in d.options) and len(d.options) == 2  # the Fox was chosen this turn
    pick(s, "Rat")
    answer(s)
    assert tokens(s) == ["Fox", "Rat"]
    check(s)


def test_with_every_mode_chosen_the_trigger_does_nothing_and_the_next_turn_starts_over(cards):
    s = build(cards, [GENKU, "Murder", "Grizzly Bears", "Llanowar Elves", "Wall Squire", "Pit Squire"])
    put(s, GENKU)
    for n in ("Grizzly Bears", "Llanowar Elves", "Wall Squire", "Pit Squire"):
        put(s, n)
    for n, token in (("Grizzly Bears", "Fox"), ("Llanowar Elves", "Moonfolk"), ("Wall Squire", "Rat")):
        lose(s, n)
        pick(s, token)
        answer(s)
    assert tokens(s) == ["Fox", "Moonfolk", "Rat"]
    lose(s, "Pit Squire")
    answer(s)
    assert tokens(s) == ["Fox", "Moonfolk", "Rat"]  # no mode left: nothing happens (603.3c)
    check(s)


def test_genku_itself_leaving_does_not_trigger(cards):
    s = build(cards, [GENKU, "Murder", "Grizzly Bears"])
    genku = put(s, GENKU)
    put(s, "Grizzly Bears")
    mana(s, "p1", B=3)
    cast(s, "Murder", [genku.id], pay=False)  # "another" permanent: Genku's own leaving is not a trigger
    answer(s)
    assert tokens(s) == []
    check(s)
